"""CS-1004 integration tests — AT-1004-2 synthetic end-to-end.

Drives the REAL code path: ApprovedBinding + TransferOrder through the
CS-1003 EgressBroker's permit gate into the ConfidentialExecutionAdapter
(attest -> key release -> submit), then job receipts, callbacks,
artifacts, cancellation, deletion and storage reconciliation. The
backend is the in-process ConfidentialDouble — synthetic approved data
only, no egress.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cloud_broker import (
    ApprovedBinding,
    EgressBroker,
    Recipient,
    TransferLimits,
    TransferOrder,
)
from cloud_broker.types import sha256_bytes
from cloud_providers import (
    ApprovalRef,
    ApprovedEnvironment,
    AttestationRefused,
    ConfidentialDouble,
    ConfidentialExecutionAdapter,
)
from cloud_providers import registry as providers_registry

pytestmark = pytest.mark.integration

PAYLOAD = b"synthetic-approved-payload-bytes"


def _spec(**over) -> ApprovedEnvironment:
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


def _recipient(spec: ApprovedEnvironment) -> Recipient:
    return Recipient(
        provider=spec.provider,
        account=spec.account,
        region=spec.region,
        environment=spec.environment,
    )


def _binding(payload: bytes = PAYLOAD, **over) -> ApprovedBinding:
    kw = {
        "manifest_digest": "manifest-synth-1",
        "payload_digest": sha256_bytes(payload),
        "payload_fields": ("smiles", "yield_pct"),
        "source_digests": ("synth-src-1",),
        "transformation_version": "transform-v1",
        "classification": "synthetic",
        "recipient": _recipient(_spec()),
        "runtime_digest": "runtime-v1",
        "permitted_job": "sft-smoke",
        "limits": TransferLimits(max_bytes=1_048_576, max_artifacts=8, wall_seconds=3600.0),
        "expiry": datetime.now(UTC) + timedelta(hours=1),
        "approver": "owner-1",
    }
    kw.update(over)
    return ApprovedBinding(**kw)


def _order(binding: ApprovedBinding | None = None, **over) -> TransferOrder:
    binding = binding or _binding()
    kw = {
        "approved": binding,
        "requested_digest": binding.digest(),
        "requested_recipient": binding.recipient,
        "requested_job": binding.permitted_job,
        "approval_digest": binding.digest(),
        "attempt_key": "attempt-synth-1",
    }
    kw.update(over)
    return TransferOrder(**kw)


@pytest.fixture()
def stack() -> tuple[EgressBroker, ConfidentialExecutionAdapter, ConfidentialDouble]:
    double = ConfidentialDouble()
    spec = _spec()
    adapter = ConfidentialExecutionAdapter(
        backend=double, environment=spec, approval=_approval(spec)
    )
    broker = EgressBroker(providers={adapter.name: adapter})
    yield broker, adapter, double
    providers_registry.clear()


def test_synthetic_end_to_end_records_job_receipts(stack) -> None:
    """AT-1004-2: approved synthetic payload -> attested submit ->
    receipts + artifacts + confidential/untrusted import."""
    broker, adapter, double = stack
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is not None

    # job receipt: broker attempt + lineage + the adapter's record
    last = broker.attempts[-1]
    assert last.outcome == "transferred"
    assert last.bytes_emitted == len(PAYLOAD)
    assert last.job_id == handle.job_id
    lineage = broker.lineage(handle.job_id)
    assert lineage is not None
    assert lineage.bytes_transferred == len(PAYLOAD)

    # the adapter attested + released an ephemeral key before submit
    assert len(double.released_keys) == 1
    assert adapter.key_releases[0].ephemeral
    assert adapter.key_releases[0].ttl_seconds <= 900

    # the confidential job spec the backend received
    spec = double.confidential_jobs[handle.job_id]
    assert spec.provenance == "synthetic"
    assert spec.payload_digest == sha256_bytes(PAYLOAD)

    # job finishes -> artifacts land as callback events on the lineage
    double.succeed(handle, artifacts=("model-artifact-1",))
    for cb in double.drain_callbacks(handle):
        broker.handle_callback(cb)
    lineage = broker.lineage(handle.job_id)
    assert lineage.state == "succeeded"
    assert "model-artifact-1" in lineage.artifact_ids

    # outputs import confidential + untrusted until validated
    double.push_output(handle, artifact_id="model-artifact-1", content=b"weights")
    outputs = adapter.import_outputs(handle)
    assert outputs.classification == "confidential"
    assert outputs.trusted is False and outputs.validated is False
    assert outputs.artifacts[0].sha256 == sha256_bytes(b"weights")

    # the provider-observable surface is recorded honestly
    observation = adapter.observation(handle.job_id)
    assert observation.payload_bytes == len(PAYLOAD)
    assert observation.provider == "confidential-double"


def test_cancellation_records_evidence(stack) -> None:
    """AT-1004-2: cancel mid-run -> cancelled status + reconcile shows
    what was already transferred."""
    broker, adapter, _double = stack
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is not None
    report = broker.cancel(handle.job_id)
    assert report.bytes_transferred == len(PAYLOAD)
    assert broker.lineage(handle.job_id).state == "cancelled"
    # adapter-side reconcile agrees the bytes exist and storage holds them
    confidential_report = adapter.reconcile(handle)
    assert confidential_report.state == "cancelled"
    assert confidential_report.retained_bytes == len(PAYLOAD)


def test_deletion_receipt_and_storage_probe(stack) -> None:
    """AT-1004-2: delete -> real receipt, then a storage probe verifies
    the provider actually released the bytes."""
    broker, adapter, _double = stack
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is not None
    receipt = broker.delete(handle.job_id)
    assert receipt.deleted is True
    assert receipt.receipt_ref
    probe = adapter.verify_storage_deleted(handle)
    assert probe.verified is True
    assert probe.retained_bytes == 0
    reconcile = adapter.reconcile(handle)
    assert reconcile.storage_deleted is True
    assert reconcile.unresolved == ()


def test_denied_attestation_path_records_failed_attempt(stack) -> None:
    """AT-1004-1 through the broker: bad attestation -> the gate emits
    nothing, the adapter refuses, the attempt is recorded 'failed'
    with zero bytes at the provider."""
    broker, adapter, double = stack
    double.attestation_mode = "tampered"
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is None
    assert broker.attempts[-1].outcome == "failed"
    assert broker.attempts[-1].bytes_emitted == 0
    assert double.received == {}
    assert double.released_keys == []
    # the refusal is preserved on the adapter for audit
    assert adapter.refusals
    assert not adapter.refusals[-1].ok


def test_broker_path_refuses_before_backend_submit(stack) -> None:
    """A recipient that is not the approved environment is refused by
    the adapter itself — even when attestation would pass."""
    broker, _adapter, double = stack
    other = Recipient(
        provider="confidential-double",
        account="not-the-approved-account",
        region="double-region",
        environment="double-enclave",
    )
    binding = _binding(recipient=other)
    order = _order(binding, requested_recipient=other)
    handle = broker.transfer(order, PAYLOAD)
    assert handle is None
    assert double.received == {}
    assert double.released_keys == []


def test_submit_raises_attestation_refused_typed(stack) -> None:
    _, adapter, double = stack
    double.attestation_mode = "missing"
    with pytest.raises(AttestationRefused) as exc:
        adapter.submit(recipient=_recipient(_spec()), job="sft-smoke", payload=PAYLOAD)
    assert "attestation_present" in exc.value.verdict.failures
