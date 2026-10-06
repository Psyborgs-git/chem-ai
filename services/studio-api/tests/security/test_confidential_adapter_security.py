"""CS-1004 security tests — the confidential adapter fails closed.

AT-1004-1: attestation missing/wrong for the approved environment ->
key release refuses and no payload or key material ever reaches the
backend (both arms exercised).

AT-1004-3: with no owner approval supplied the whole surface reports
``not_configured`` and stays inert — never falsely implemented-live.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

import cloud_providers
from cloud_broker.providers import ProviderNotConfigured
from cloud_providers import (
    ApprovalRef,
    ApprovalRequired,
    ApprovedEnvironment,
    AttestationRefused,
    ConfidentialDouble,
    ConfidentialExecutionAdapter,
    KeyReleaseRequest,
    ProvenanceRefused,
    confidential_capability,
    register,
    resolve,
)
from cloud_providers import registry as providers_registry

pytestmark = pytest.mark.security


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


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    providers_registry.clear()
    yield
    providers_registry.clear()


# -- AT-1004-1: attestation gate fails closed -----------------------------------


@pytest.mark.parametrize(
    "mode,overrides",
    [
        ("missing", None),
        ("tampered", None),
        ("expired", None),
        ("present", {"measurement": "forged-measurement"}),
        ("present", {"account": "attacker-account"}),
        ("present", {"gpu_confidential": None}),
        ("present", {"telemetry_enabled": True}),
    ],
)
def test_bad_attestation_releases_no_key_and_no_payload(mode, overrides) -> None:
    """Every attestation failure arm refuses before key release — the
    backend never sees the payload and never mints a ticket."""
    double = ConfidentialDouble(attestation_mode=mode, doc_overrides=overrides)
    spec = _spec()
    adapter = ConfidentialExecutionAdapter(
        backend=double, environment=spec, approval=_approval(spec)
    )
    verdict = adapter.attest()
    assert not verdict.ok
    with pytest.raises(AttestationRefused):
        adapter.release_key(KeyReleaseRequest("job-1", 300))
    assert double.released_keys == []
    assert double.received == {}
    # the refusal is auditable on the adapter
    assert adapter.refusals


def test_good_attestation_releases_exactly_one_key() -> None:
    """The verified arm: key material is minted once, is ephemeral, and
    the payload only then reaches the confidential backend."""
    double = ConfidentialDouble()
    spec = _spec()
    adapter = ConfidentialExecutionAdapter(
        backend=double, environment=spec, approval=_approval(spec)
    )
    handle = adapter.submit_confidential(
        job="sft-smoke", payload=b"synthetic", provenance="synthetic"
    )
    assert len(double.released_keys) == 1
    assert double.released_keys[0].ephemeral
    assert double.received[handle.job_id] == b"synthetic"


def test_release_key_cannot_be_bypassed_or_forged() -> None:
    """release_key always attests internally — a caller cannot mint a
    verdict object or skip verification; the request itself re-checks
    the environment at release time."""
    double = ConfidentialDouble(attestation_mode="missing")
    spec = _spec()
    adapter = ConfidentialExecutionAdapter(
        backend=double, environment=spec, approval=_approval(spec)
    )
    # no prior attest() call at all — release_key verifies inline
    with pytest.raises(AttestationRefused):
        adapter.release_key(KeyReleaseRequest("job-1", 300))
    assert double.released_keys == []
    assert adapter.refusals

    # and a submit through the real path refuses identically — submit()
    # never trusts a passed-in verdict; it verifies fresh each time.
    from cloud_broker import Recipient

    recipient = Recipient(
        provider=spec.provider,
        account=spec.account,
        region=spec.region,
        environment=spec.environment,
    )
    with pytest.raises(AttestationRefused):
        adapter.submit(recipient=recipient, job="j", payload=b"x")
    assert double.received == {}


def test_real_provenance_never_reaches_synthetic_only_environment() -> None:
    double = ConfidentialDouble()
    spec = _spec()
    adapter = ConfidentialExecutionAdapter(
        backend=double, environment=spec, approval=_approval(spec)
    )
    with pytest.raises(ProvenanceRefused):
        adapter.submit_confidential(job="sft", payload=b"real", provenance="approved_real")
    assert double.received == {}
    assert double.released_keys == []


# -- AT-1004-3: no approval -> not_configured, surface inert ---------------------


def test_capability_reports_not_configured_without_approval() -> None:
    capability = confidential_capability()
    assert capability["status"] == "not_configured"
    assert capability["live"] is False
    assert capability["providers"] == []
    assert capability["egress"] == "deny"


def test_resolve_without_registration_is_not_configured() -> None:
    with pytest.raises(ProviderNotConfigured) as exc:
        resolve("aws-confidential")
    assert exc.value.status == "not_configured"


@pytest.mark.parametrize(
    "approval",
    [
        None,
        "expired",
        "wrong_capability",
        "wrong_subject",
    ],
)
def test_register_without_valid_approval_stays_inert(approval) -> None:
    spec = _spec()
    ref: ApprovalRef | None
    if approval is None:
        ref = None
    elif approval == "expired":
        ref = _approval(spec, expiry=datetime.now(UTC) - timedelta(seconds=1))
    elif approval == "wrong_capability":
        # an agent-style capability (not approve_export) cannot bind a
        # provider — approvals are owner-only
        ref = _approval(spec, capability="execute")
    else:
        ref = _approval(spec, bound="cloud_provider:other/acct/region/env")
    with pytest.raises(ApprovalRequired):
        register(spec=spec, approval=ref, backend=ConfidentialDouble())
    capability = confidential_capability()
    assert capability["status"] == "not_configured"
    assert capability["live"] is False


def test_registered_double_never_reports_live() -> None:
    spec = _spec()
    register(
        spec=spec,
        approval=_approval(spec),
        backend=ConfidentialDouble(),
    )
    capability = confidential_capability()
    assert capability["status"] == "not_configured"
    assert capability["live"] is False
    # honestly inventoried as synthetic, not silently 'configured'
    assert capability["synthetic_adapters"] == ["confidential-double"]


# -- structural: the adapter package has no network surface ---------------------


def test_package_has_no_network_surface() -> None:
    """The adapter only ever moves bytes through the broker's provider
    seam — no socket/http/subprocess calls live in the package."""
    import cloud_providers.adapter as adapter_mod
    import cloud_providers.attestation as attestation_mod
    import cloud_providers.backend as backend_mod
    import cloud_providers.double as double_mod
    import cloud_providers.registry as registry_mod
    import cloud_providers.types as types_mod

    banned = (
        "import socket",
        "import requests",
        "import urllib",
        "import httpx",
        "import subprocess",
        "import boto3",
        "import google.cloud",
        "import azure",
        "socket.",
        "requests.",
        "urllib.request",
        "httpx.",
        "subprocess.",
    )
    for mod in (
        adapter_mod,
        attestation_mod,
        backend_mod,
        double_mod,
        registry_mod,
        types_mod,
    ):
        source = inspect.getsource(mod)
        for needle in banned:
            assert needle not in source, f"{mod.__name__} contains {needle}"


def test_public_surface_exports_no_network_helpers() -> None:
    """The package exports types + the adapter — no transport helpers."""
    assert not hasattr(cloud_providers, "requests")
    assert not hasattr(cloud_providers, "socket")
    assert not hasattr(cloud_providers, "urlopen")
