"""Attestation verification — the fail-closed gate of CS-1004.

Every approved-environment assertion is checked independently and
reported; a single failure refuses the environment (AT-1004-1). Missing
evidence, missing coverage reports, forged signatures, and expired
windows all refuse — nothing defaults to pass.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_providers.types import (
    ApprovedEnvironment,
    AttestationCheck,
    AttestationDocument,
    AttestationVerdict,
)

# Small positive skew tolerated between the document's issue time and
# the verifier's clock; anything larger refuses.
_MAX_CLOCK_SKEW = timedelta(seconds=300)


def verify_attestation(
    doc: AttestationDocument | None,
    spec: ApprovedEnvironment,
    *,
    now: datetime | None = None,
) -> AttestationVerdict:
    """Verify a provider attestation document against the approved spec.

    All-or-nothing: collects every named check, refuses on any failure.
    """
    now = now or datetime.now(UTC)
    checks: list[AttestationCheck] = []
    env_digest = spec.digest()

    if doc is None:
        checks.append(
            AttestationCheck(
                "attestation_present",
                False,
                "no attestation document supplied for the environment",
            )
        )
        return AttestationVerdict("refused", tuple(checks), env_digest, None)

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append(AttestationCheck(name, ok, detail))

    check(
        "attestation_signature_valid",
        doc.signature == doc.doc_digest(),
        "document signature matches the canonical document digest"
        if doc.signature == doc.doc_digest()
        else "document signature does not match its content — tampered or forged",
    )
    check(
        "attestation_not_expired",
        doc.expiry > now,
        f"document expires {doc.expiry.isoformat()}"
        if doc.expiry > now
        else f"document expired at {doc.expiry.isoformat()}",
    )
    check(
        "attestation_issue_time_sane",
        doc.issued_at <= now + _MAX_CLOCK_SKEW,
        f"document issued {doc.issued_at.isoformat()}"
        if doc.issued_at <= now + _MAX_CLOCK_SKEW
        else f"document issued in the future ({doc.issued_at.isoformat()})",
    )
    check(
        "approval_not_expired",
        spec.expiry > now,
        f"approval expires {spec.expiry.isoformat()}"
        if spec.expiry > now
        else f"approval expired at {spec.expiry.isoformat()}",
    )
    check("provider_matches", doc.provider == spec.provider, doc.provider)
    check("account_matches", doc.account == spec.account, doc.account)
    check("region_matches", doc.region == spec.region, doc.region)
    check(
        "environment_matches",
        doc.environment == spec.environment,
        doc.environment,
    )
    check(
        "measurement_matches",
        doc.measurement == spec.measurement,
        doc.measurement,
    )
    check(
        "firmware_matches",
        spec.firmware is None or doc.firmware == spec.firmware,
        str(doc.firmware),
    )
    check(
        "gpu_coverage_confirmed",
        (not spec.gpu_confidential) or doc.gpu_confidential is True,
        "approved GPU coverage reported present"
        if doc.gpu_confidential is True
        else "approved GPU coverage not reported — absent coverage fails closed",
    )
    check(
        "image_digest_matches",
        doc.image_digest == spec.image_digest,
        doc.image_digest,
    )
    check(
        "model_digest_matches",
        spec.model_digest is None or doc.model_digest == spec.model_digest,
        str(doc.model_digest),
    )
    check(
        "network_isolation_matches",
        doc.network == spec.network,
        doc.network,
    )
    check(
        "operator_access_within_policy",
        doc.operator_access == spec.operator_access,
        doc.operator_access,
    )
    check(
        "telemetry_disabled",
        (not spec.telemetry_disabled) or doc.telemetry_enabled is False,
        "provider reports telemetry disabled"
        if doc.telemetry_enabled is False
        else "provider reports telemetry enabled",
    )
    check(
        "content_logging_disabled",
        (not spec.content_logging_disabled) or doc.content_logging_enabled is False,
        "provider reports content logging disabled"
        if doc.content_logging_enabled is False
        else "provider reports content logging enabled",
    )
    check(
        "ephemeral_credentials_supported",
        (not spec.ephemeral_credentials) or doc.ephemeral_credentials is True,
        "ephemeral credentials supported"
        if doc.ephemeral_credentials is True
        else "ephemeral credentials not reported",
    )
    check(
        "private_artifacts_supported",
        (not spec.private_artifacts) or doc.private_artifacts is True,
        "private artifacts supported"
        if doc.private_artifacts is True
        else "private artifacts not reported",
    )

    ok = all(c.ok for c in checks)
    return AttestationVerdict(
        "verified" if ok else "refused",
        tuple(checks),
        env_digest,
        doc.doc_digest(),
    )
