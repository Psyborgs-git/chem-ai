"""CS-1004 unit tests — the confidential-execution adapter's gates.

Pure in-process: the backend is the ConfidentialDouble, so attestation
refusals, key releases, and submitted payloads are asserted on the
double's own honest records.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from cloud_broker import Recipient
from cloud_providers import (
    ApprovalRef,
    ApprovalRequired,
    ApprovedEnvironment,
    AttestationRefused,
    ConfidentialDenied,
    ConfidentialDouble,
    ConfidentialExecutionAdapter,
    ImportRefused,
    KeyReleaseRequest,
    ProvenanceRefused,
    confidential_capability,
    register,
    resolve,
    verify_attestation,
)
from cloud_providers import registry as providers_registry


def _spec(**over) -> ApprovedEnvironment:
    """An ApprovedEnvironment matching the double's default identity."""
    env = ConfidentialDouble.DEFAULT_ENVIRONMENT
    kw = {
        "provider": env["provider"],
        "account": env["account"],
        "region": env["region"],
        "environment": env["environment"],
        "measurement": env["measurement"],
        "firmware": env["firmware"],
        "gpu_confidential": env["gpu_confidential"],
        "image_digest": env["image_digest"],
        "model_digest": env["model_digest"],
        "network": env["network"],
        "operator_access": env["operator_access"],
        "telemetry_disabled": True,
        "content_logging_disabled": True,
        "ephemeral_credentials": True,
        "private_artifacts": True,
        "max_access_ttl_seconds": 900,
        "deletion_required": True,
        "synthetic_only": True,
        "expiry": datetime.now(UTC) + timedelta(hours=1),
    }
    kw.update(over)
    return ApprovedEnvironment(**kw)


def _approval(spec: ApprovedEnvironment, **over) -> ApprovalRef:
    kw = {
        "digest": "approval-digest-1",
        "approver": "owner-1",
        "capability": "approve_export",
        "bound": (
            f"cloud_provider:{spec.provider}/{spec.account}/{spec.region}/{spec.environment}"
        ),
        "expiry": datetime.now(UTC) + timedelta(hours=1),
    }
    kw.update(over)
    return ApprovalRef(**kw)


def _adapter(
    backend: ConfidentialDouble | None = None,
    spec: ApprovedEnvironment | None = None,
    **spec_over,
) -> tuple[ConfidentialExecutionAdapter, ConfidentialDouble]:
    backend = backend or ConfidentialDouble()
    spec = spec or _spec(**spec_over)
    return (
        ConfidentialExecutionAdapter(backend=backend, environment=spec, approval=_approval(spec)),
        backend,
    )


def _recipient(spec: ApprovedEnvironment | None = None) -> Recipient:
    spec = spec or _spec()
    return Recipient(
        provider=spec.provider,
        account=spec.account,
        region=spec.region,
        environment=spec.environment,
    )


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    providers_registry.clear()
    yield
    providers_registry.clear()


# -- attestation: the fail-closed matrix (AT-1004-1) ---------------------------


def test_attestation_verifies_matching_document() -> None:
    double = ConfidentialDouble()
    verdict = verify_attestation(double.attestation_document(), _spec())
    assert verdict.ok
    assert verdict.status == "verified"
    assert all(c.ok for c in verdict.checks)


def test_missing_attestation_refuses() -> None:
    double = ConfidentialDouble(attestation_mode="missing")
    verdict = verify_attestation(double.attestation_document(), _spec())
    assert not verdict.ok
    assert "attestation_present" in verdict.failures


@pytest.mark.parametrize(
    "override",
    [
        {"measurement": "evil-measurement"},
        {"account": "attacker-account"},
        {"region": "unapproved-region"},
        {"environment": "different-enclave"},
        {"image_digest": "sha256:unpinned-image"},
        {"network": "unrestricted"},
        {"operator_access": "always-on"},
        {"gpu_confidential": None},
        {"gpu_confidential": False},
    ],
)
def test_mismatched_attestation_fields_refuse(override) -> None:
    double = ConfidentialDouble(doc_overrides=override)
    verdict = verify_attestation(double.attestation_document(), _spec())
    assert not verdict.ok
    assert verdict.failures


def test_telemetry_or_logging_enabled_refuses() -> None:
    for flag in ("telemetry_enabled", "content_logging_enabled"):
        double = ConfidentialDouble(doc_overrides={flag: True})
        verdict = verify_attestation(double.attestation_document(), _spec())
        assert not verdict.ok


def test_tampered_signature_refuses() -> None:
    double = ConfidentialDouble(attestation_mode="tampered")
    verdict = verify_attestation(double.attestation_document(), _spec())
    assert not verdict.ok
    assert "attestation_signature_valid" in verdict.failures


def test_expired_document_refuses() -> None:
    double = ConfidentialDouble(attestation_mode="expired")
    verdict = verify_attestation(double.attestation_document(), _spec())
    assert not verdict.ok
    assert "attestation_not_expired" in verdict.failures


def test_expired_approval_window_refuses() -> None:
    double = ConfidentialDouble()
    spec = _spec(expiry=datetime.now(UTC) - timedelta(seconds=1))
    verdict = verify_attestation(double.attestation_document(), spec)
    assert not verdict.ok
    assert "approval_not_expired" in verdict.failures


# -- key release: both arms of AT-1004-1 ---------------------------------------


def test_key_release_on_verified_attestation() -> None:
    adapter, double = _adapter()
    verdict = adapter.attest()
    assert verdict.ok
    ticket = adapter.release_key(KeyReleaseRequest("job-1", 300))
    assert ticket.ephemeral
    assert ticket.ttl_seconds == 300
    assert double.released_keys == [ticket]


def test_key_release_fails_closed_on_bad_attestation() -> None:
    """AT-1004-1: wrong attestation for the approved environment -> no
    key material is ever minted or released."""
    adapter, double = _adapter(backend=ConfidentialDouble(doc_overrides={"measurement": "forged"}))
    verdict = adapter.attest()
    assert not verdict.ok
    with pytest.raises(AttestationRefused):
        adapter.release_key(KeyReleaseRequest("job-1", 300))
    assert double.released_keys == []
    assert double.received == {}


def test_key_release_ttl_capped_by_approval() -> None:
    adapter, _ = _adapter()
    with pytest.raises(ConfidentialDenied):
        adapter.release_key(KeyReleaseRequest("job-1", 10_000))


# -- submit path ---------------------------------------------------------------


def test_submit_attests_then_dispatches() -> None:
    adapter, double = _adapter()
    handle = adapter.submit(recipient=_recipient(), job="sft-smoke", payload=b"synthetic")
    assert handle.job_id
    assert double.received[handle.job_id] == b"synthetic"
    assert len(double.released_keys) == 1
    spec = double.confidential_jobs[handle.job_id]
    assert spec.provenance == "synthetic"
    assert spec.runtime_digest == _spec().measurement


def test_submit_with_bad_attestation_emits_zero_bytes() -> None:
    adapter, double = _adapter(backend=ConfidentialDouble(attestation_mode="missing"))
    with pytest.raises(AttestationRefused):
        adapter.submit(recipient=_recipient(), job="sft-smoke", payload=b"data")
    assert double.received == {}
    assert double.released_keys == []


def test_submit_to_wrong_recipient_refuses() -> None:
    adapter, double = _adapter()
    stranger = Recipient(
        provider="confidential-double",
        account="other-account",
        region="double-region",
        environment="double-enclave",
    )
    with pytest.raises(ConfidentialDenied):
        adapter.submit(recipient=stranger, job="j", payload=b"x")
    assert double.received == {}


def test_real_provenance_refused_on_synthetic_only_environment() -> None:
    """This deployment is synthetic-only: a real-provenance payload is
    refused honestly until an owner approves a live binding."""
    adapter, double = _adapter()
    with pytest.raises(ProvenanceRefused):
        adapter.submit_confidential(job="sft", payload=b"real-data", provenance="approved_real")
    assert double.received == {}


def test_submit_confidential_synthetic_works_directly() -> None:
    adapter, double = _adapter()
    handle = adapter.submit_confidential(
        job="sft-smoke",
        payload=b"synthetic-payload",
        provenance="synthetic",
        manifest_digest="manifest-9",
    )
    assert double.confidential_jobs[handle.job_id].manifest_digest == "manifest-9"


# -- output import --------------------------------------------------------------


def test_import_outputs_marks_confidential_and_untrusted() -> None:
    adapter, double = _adapter()
    handle = adapter.submit(recipient=_recipient(), job="sft-smoke", payload=b"payload")
    double.push_output(handle, artifact_id="out-1", content=b"checkpoint-bytes")
    outputs = adapter.import_outputs(handle)
    assert outputs.classification == "confidential"
    assert outputs.trusted is False
    assert outputs.validated is False
    assert [a.artifact_id for a in outputs.artifacts] == ["out-1"]


def test_import_refuses_non_private_artifact() -> None:
    adapter, double = _adapter()
    handle = adapter.submit(recipient=_recipient(), job="sft-smoke", payload=b"payload")
    double.push_output(handle, artifact_id="leaky", content=b"x", private=False)
    with pytest.raises(ImportRefused):
        adapter.import_outputs(handle)


def test_import_refuses_artifact_ttl_over_limit() -> None:
    adapter, double = _adapter()
    handle = adapter.submit(recipient=_recipient(), job="sft-smoke", payload=b"payload")
    double.push_output(
        handle,
        artifact_id="long-lived",
        content=b"x",
        access_ttl_seconds=99_999,
    )
    with pytest.raises(ImportRefused):
        adapter.import_outputs(handle)


# -- observation + reconcile ----------------------------------------------------


def test_observation_records_provider_visible_surface() -> None:
    adapter, double = _adapter()
    handle = adapter.submit(recipient=_recipient(), job="sft-smoke", payload=b"payload-1234")
    double.push_output(handle, artifact_id="a1", content=b"abc")
    observation = adapter.observation(handle.job_id)
    assert observation.payload_bytes == len(b"payload-1234")
    assert observation.submitted_at is not None
    assert observation.provider == "confidential-double"
    assert "in-process://confidential-double" in observation.endpoints


def test_reconcile_reports_retention_honestly() -> None:
    adapter, _double = _adapter()
    handle = adapter.submit(recipient=_recipient(), job="sft-smoke", payload=b"payload")
    report = adapter.reconcile(handle)
    assert report.retained_bytes == len(b"payload")
    assert report.storage_deleted is False
    assert any("retains" in u for u in report.unresolved)
    adapter.delete(handle)
    report = adapter.reconcile(handle)
    assert report.storage_deleted is True
    assert report.retained_bytes == 0


# -- registry + capability (AT-1004-3) ------------------------------------------


def test_empty_registry_reports_not_configured() -> None:
    capability = confidential_capability()
    assert capability["status"] == "not_configured"
    assert capability["live"] is False
    assert capability["egress"] == "deny"
    with pytest.raises(Exception) as exc:
        resolve("confidential-double")
    assert getattr(exc.value, "status", None) == "not_configured"


def test_register_requires_approval() -> None:
    with pytest.raises(ApprovalRequired):
        register(spec=_spec(), approval=None, backend=ConfidentialDouble())
    assert confidential_capability()["status"] == "not_configured"


def test_register_rejects_wrong_capability() -> None:
    spec = _spec()
    bad = _approval(spec, capability="execute")
    with pytest.raises(ApprovalRequired):
        register(spec=spec, approval=bad, backend=ConfidentialDouble())


def test_register_rejects_expired_approval() -> None:
    spec = _spec()
    stale = _approval(spec, expiry=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(ApprovalRequired):
        register(spec=spec, approval=stale, backend=ConfidentialDouble())


def test_register_rejects_approval_for_different_subject() -> None:
    spec = _spec()
    wrong = _approval(spec, bound="cloud_provider:aws/other/us-x/other-env")
    with pytest.raises(ApprovalRequired):
        register(spec=spec, approval=wrong, backend=ConfidentialDouble())


def test_synthetic_adapter_inventoried_but_never_live() -> None:
    """A registered double stays honestly 'synthetic' — the live status
    stays not_configured (AT-1004-3)."""
    spec = _spec()
    adapter = register(
        spec=spec,
        approval=_approval(spec),
        backend=ConfidentialDouble(),
    )
    capability = confidential_capability()
    assert capability["status"] == "not_configured"
    assert capability["live"] is False
    assert capability["synthetic_adapters"] == [adapter.name]
    assert resolve("confidential-double") is adapter
