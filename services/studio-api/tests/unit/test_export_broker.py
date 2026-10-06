"""CS-1003 unit tests — the egress broker's binding + boundary rules.

Pure in-process: the provider is the double, so every assertion about
'what left the machine' reads the double's received byte count.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cloud_broker import (
    ApprovedBinding,
    EgressBroker,
    ProviderDouble,
    Recipient,
    TransferLimits,
    TransferOrder,
)
from cloud_broker.types import sha256_bytes

PAYLOAD = b"minimal-transformed-payload-bytes"


def _recipient(**over: str) -> Recipient:
    kw = {
        "provider": "provider-double",
        "account": "acct-1",
        "region": "local",
        "environment": "double",
    }
    kw.update(over)
    return Recipient(**kw)


def _binding(payload: bytes = PAYLOAD, **over) -> ApprovedBinding:
    kw = {
        "manifest_digest": "manifest-1",
        "payload_digest": sha256_bytes(payload),
        "payload_fields": ("smiles", "yield_pct"),
        "source_digests": ("src-1",),
        "transformation_version": "transform-v1",
        "classification": "confidential",
        "recipient": _recipient(),
        "runtime_digest": "runtime-v1",
        "permitted_job": "sft-training",
        "limits": TransferLimits(max_bytes=1_048_576, max_artifacts=8, wall_seconds=3600.0),
        "expiry": datetime.now(UTC) + timedelta(hours=1),
        "approver": "owner-1",
    }
    kw.update(over)
    return ApprovedBinding(**kw)


def _order(
    binding: ApprovedBinding | None = None,
    *,
    recipient: Recipient | None = None,
    job: str | None = None,
    approval_digest: str | None = None,
    requested_digest: str | None = None,
    attempt_key: str = "attempt-k1",
) -> TransferOrder:
    binding = binding or _binding()
    return TransferOrder(
        approved=binding,
        requested_digest=requested_digest if requested_digest is not None else binding.digest(),
        requested_recipient=recipient or binding.recipient,
        requested_job=job if job is not None else binding.permitted_job,
        approval_digest=approval_digest if approval_digest is not None else binding.digest(),
        attempt_key=attempt_key,
    )


@pytest.fixture()
def stack() -> tuple[EgressBroker, ProviderDouble]:
    double = ProviderDouble()
    return EgressBroker(providers={double.name: double}), double


def test_dry_run_validates_everything_no_bytes(stack) -> None:
    broker, double = stack
    report = broker.dry_run(_order(), PAYLOAD)
    assert report.ok
    assert all(ok for _, ok, _ in report.checks)
    assert double.received_bytes == 0
    assert broker.attempts[-1].outcome == "validated"


def test_dry_run_reports_each_failed_check(stack) -> None:
    broker, _ = stack
    order = _order(recipient=_recipient(account="acct-other"))
    report = broker.dry_run(order, b"wrong-bytes")
    assert not report.ok
    failed = {name for name, ok, _ in report.checks if not ok}
    assert "recipient_matches" in failed
    assert "payload_digest_matches" in failed
    # approval digest is still right — the binding itself is intact
    assert "approval_digest_matches_binding" not in failed


def test_transfer_happy_path_records_lineage(stack) -> None:
    broker, double = stack
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is not None
    assert double.received_bytes == len(PAYLOAD)
    last = broker.attempts[-1]
    assert last.outcome == "transferred"
    assert last.bytes_emitted == len(PAYLOAD)
    assert last.job_id == handle.job_id
    lineage = broker.lineage(handle.job_id)
    assert lineage is not None and lineage.bytes_transferred == len(PAYLOAD)
    assert lineage.exposed is True


def test_mismatched_payload_emits_zero_bytes(stack) -> None:
    """AT-1003-1 (payload differs): denial happens before the boundary."""
    broker, double = stack
    assert broker.transfer(_order(), b"tampered-payload") is None
    assert double.received_bytes == 0
    last = broker.attempts[-1]
    assert last.outcome == "denied" and last.bytes_emitted == 0


def test_mismatched_recipient_emits_zero_bytes(stack) -> None:
    """AT-1003-1 (recipient differs): another account denies egress."""
    broker, double = stack
    order = _order(recipient=_recipient(account="acct-attacker"))
    assert broker.transfer(order, PAYLOAD) is None
    assert double.received_bytes == 0
    assert broker.attempts[-1].outcome == "denied"


def test_mismatched_job_emits_zero_bytes(stack) -> None:
    broker, double = stack
    assert broker.transfer(_order(job="other-job"), PAYLOAD) is None
    assert double.received_bytes == 0


def test_stale_approval_digest_denies(stack) -> None:
    """Approval bound to a *different* manifest digest never authorizes."""
    broker, double = stack
    assert broker.transfer(_order(approval_digest="different-digest"), PAYLOAD) is None
    assert double.received_bytes == 0


def test_expired_binding_denies(stack) -> None:
    broker, double = stack
    binding = _binding(expiry=datetime.now(UTC) - timedelta(seconds=1))
    assert broker.transfer(_order(binding), PAYLOAD) is None
    assert double.received_bytes == 0


def test_over_limit_payload_denies(stack) -> None:
    broker, double = stack
    binding = _binding(limits=TransferLimits(max_bytes=4, max_artifacts=8, wall_seconds=60))
    assert broker.transfer(_order(binding), PAYLOAD) is None
    assert double.received_bytes == 0


def test_revoked_binding_blocks_later_attempts(stack) -> None:
    """§20.5 'before transfer': revoke then attempt → zero bytes."""
    broker, double = stack
    order = _order()
    broker.revoke_binding(order.approval_digest)
    assert broker.transfer(order, PAYLOAD) is None
    assert double.received_bytes == 0
    assert broker.attempts[-1].outcome == "denied"


def test_retry_needs_fresh_attempt_within_same_binding(stack) -> None:
    """Retries share manifest/recipient/expiry — each gets its own
    permit; a spent permit cannot emit twice."""
    broker, double = stack
    order = _order(attempt_key="attempt-k1")
    assert broker.transfer(order, PAYLOAD) is not None
    # A *new* attempt under the same approved binding retries cleanly.
    retry = _order(attempt_key="attempt-k2")
    assert broker.transfer(retry, PAYLOAD) is not None
    assert double.received_bytes == 2 * len(PAYLOAD)


def test_provider_failure_recorded_not_hidden(stack) -> None:
    broker, double = stack
    double.fail_submit = RuntimeError("provider exploded")
    assert broker.transfer(_order(), PAYLOAD) is None
    last = broker.attempts[-1]
    assert last.outcome == "failed"
    assert "provider exploded" in last.reason


def test_unknown_provider_reports_not_configured(stack) -> None:
    """Production providers stay not_configured — the attempt is
    honestly recorded as failed, never a silent fallthrough."""
    broker, _ = stack
    binding = _binding(recipient=_recipient(provider="real-cloud"))
    order = _order(binding, recipient=_recipient(provider="real-cloud"))
    assert broker.transfer(order, PAYLOAD) is None
    last = broker.attempts[-1]
    assert last.outcome == "failed"
    assert "not_configured" in last.reason
    assert last.bytes_emitted == 0


def test_cancel_mid_run_records_exposure(stack) -> None:
    """AT-1003-2: revoked during execution — reconcile states honestly
    what was already transferred."""
    broker, _double = stack
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is not None
    report = broker.cancel(handle.job_id)
    assert report.bytes_transferred == len(PAYLOAD)
    assert report.exposed is True
    assert broker.lineage(handle.job_id).state == "cancelled"


def test_reconcile_lists_unresolved_retention(stack) -> None:
    broker, _double = stack
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is not None
    report = broker.reconcile(handle.job_id)
    assert report.bytes_transferred == len(PAYLOAD)
    assert any("retains" in item for item in report.unresolved_retention)


def test_delete_returns_actual_receipt(stack) -> None:
    broker, _double = stack
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is not None
    receipt = broker.delete(handle.job_id)
    assert receipt.deleted is True
    assert receipt.receipt_ref
    assert broker.lineage(handle.job_id).state == "deleted"


def test_repeated_callback_converges_one_lineage(stack) -> None:
    """AT-1003-3: duplicate + reordered callbacks → one consistent
    lineage, deduped artifacts, no state regression."""
    broker, double = stack
    handle = broker.transfer(_order(), PAYLOAD)
    assert handle is not None
    job = handle.job_id
    double.inject_callback(
        handle, "succeeded", seq=5, callback_id="cb-s", artifacts=("artifact-a",)
    )
    for cb in double.drain_callbacks(handle):
        broker.handle_callback(cb)
    # replay the same callback id + a crossed older-state event
    double.inject_callback(
        handle, "succeeded", seq=5, callback_id="cb-s", artifacts=("artifact-a",)
    )
    double.inject_callback(handle, "running", seq=3, callback_id="cb-r")
    double.inject_callback(
        handle, "succeeded", seq=6, callback_id="cb-s2", artifacts=("artifact-a", "artifact-b")
    )
    changed = [broker.handle_callback(cb) for cb in double.drain_callbacks(handle)]
    lineage = broker.lineage(job)
    assert lineage is not None
    assert lineage.state == "succeeded"  # never regressed to running
    assert lineage.artifact_ids == ["artifact-a", "artifact-b"]
    # the exact replay (same id) changed nothing
    assert changed[0] is False
    assert len({a.attempt_key for a in broker.attempts if a.outcome == "transferred"}) == 1


def test_callback_for_unknown_job_is_dropped(stack) -> None:
    broker, _ = stack
    from cloud_broker.types import CallbackEvent

    assert (
        broker.handle_callback(
            CallbackEvent(callback_id="x", job_id="nobody", event="succeeded", seq=1)
        )
        is False
    )


def test_gate_denies_unpermitted_bytes_directly(stack) -> None:
    """Bytes boundary (AT-1003-1): calling the gate with a permit whose
    digest does not match the payload emits nothing — even if a caller
    bypassed the broker's service-layer validation entirely."""
    from cloud_broker.gate import EgressDenied, EgressGate
    from cloud_broker.types import Permit

    _, double = stack
    gate = EgressGate()
    binding = _binding()
    forged = Permit(
        permit_id="forged-1",
        attempt_key="k",
        payload_digest=binding.payload_digest,
        recipient=binding.recipient,
        permitted_job=binding.permitted_job,
        limits=binding.limits,
        expiry=binding.expiry,
    )
    with pytest.raises(EgressDenied):
        gate.emit(forged, double, b"not-the-approved-payload")
    assert double.received_bytes == 0


def test_gate_permit_is_single_use(stack) -> None:
    """A spent permit cannot emit twice — retries need a fresh permit
    inside the same manifest/recipient/expiry/budget bound (§20.2)."""
    from cloud_broker.gate import EgressDenied, EgressGate
    from cloud_broker.types import Permit

    _, double = stack
    gate = EgressGate()
    binding = _binding()
    permit = Permit(
        permit_id="p-1",
        attempt_key="k",
        payload_digest=binding.payload_digest,
        recipient=binding.recipient,
        permitted_job=binding.permitted_job,
        limits=binding.limits,
        expiry=binding.expiry,
    )
    gate.emit(permit, double, PAYLOAD)
    with pytest.raises(EgressDenied):
        gate.emit(permit, double, PAYLOAD)
    assert double.received_bytes == len(PAYLOAD)
