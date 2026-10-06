"""In-process confidential provider double for synthetic tests.

Implements ``ConfidentialBackend`` honestly: it mints real attestation
documents (from its own environment identity — tests set them matching
or mismatching the approved spec), releases ephemeral key material only
when asked post-attestation, and executes jobs through ``ProviderDouble``
so the broker lineage/callback path is exercised for real.

``kind = "synthetic"`` — a double can never report live capability.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Literal

from cloud_broker.double import ProviderDouble
from cloud_broker.types import (
    CallbackEvent,
    DeletionReceipt,
    JobHandle,
    JobStatus,
    Recipient,
    sha256_bytes,
)
from cloud_providers.types import (
    AttestationDocument,
    ConfidentialJobSpec,
    ImportedArtifact,
    KeyReleaseRequest,
    KeyReleaseTicket,
)

AttestationMode = Literal["present", "missing", "tampered", "expired"]


class _ConfidentialJobRunner(ProviderDouble):
    """Job lifecycle under the confidential provider's own name —
    broker cancel/delete resolve providers via handle.provider."""

    name = "confidential-double"


class ConfidentialDouble:
    """Honest synthetic confidential backend.

    Test hooks (all honest — the double reports exactly what happened):

    - ``attestation_mode``: "present" (default) | "missing" | "tampered" |
      "expired" — which document arm the environment returns.
    - ``doc_overrides``: field values merged into the minted document —
      set e.g. ``measurement`` wrong to exercise the mismatch arm.
    - ``released_keys``: every ticket minted (assert non-empty/empty).
    - ``received``: job_id -> payload bytes actually accepted.
    - ``confidential_jobs``: job_id -> the ConfidentialJobSpec received.
    """

    name = "confidential-double"
    kind: Literal["synthetic"] = "synthetic"
    endpoints = ("in-process://confidential-double",)

    # The double's own environment identity — tests align (or break) the
    # ApprovedEnvironment spec against these values.
    DEFAULT_ENVIRONMENT: ClassVar[dict[str, Any]] = {
        "provider": "confidential-double",
        "account": "double-account",
        "region": "double-region",
        "environment": "double-enclave",
        "measurement": "double-measurement-0001",
        "firmware": "tdx-1.5",
        "gpu_confidential": True,
        "image_digest": "sha256:double-image",
        "model_digest": "sha256:double-model",
        "network": "deny_outbound",
        "operator_access": "deny",
        "telemetry_enabled": False,
        "content_logging_enabled": False,
        "ephemeral_credentials": True,
        "private_artifacts": True,
    }

    def __init__(
        self,
        *,
        attestation_mode: AttestationMode = "present",
        doc_overrides: dict[str, Any] | None = None,
        doc_ttl_seconds: int = 3600,
        auto_progress: bool = True,
    ) -> None:
        self.attestation_mode: AttestationMode = attestation_mode
        self.doc_overrides = dict(doc_overrides or {})
        self.doc_ttl_seconds = doc_ttl_seconds
        self.released_keys: list[KeyReleaseTicket] = []
        self.received: dict[str, bytes] = {}
        self.confidential_jobs: dict[str, ConfidentialJobSpec] = {}
        self.outputs: dict[str, list[ImportedArtifact]] = {}
        self.fail_submit: Exception | None = None
        self._inner = _ConfidentialJobRunner(auto_progress=auto_progress)
        self._keys = itertools.count(1)

    # -- attestation + key release -------------------------------------------

    def attestation_document(self) -> AttestationDocument | None:
        if self.attestation_mode == "missing":
            return None
        now = datetime.now(UTC)
        env = dict(self.DEFAULT_ENVIRONMENT)
        env.update(self.doc_overrides)
        expiry = (
            now - timedelta(seconds=1)
            if self.attestation_mode == "expired"
            else now + timedelta(seconds=self.doc_ttl_seconds)
        )
        fields = {
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
            "telemetry_enabled": env["telemetry_enabled"],
            "content_logging_enabled": env["content_logging_enabled"],
            "ephemeral_credentials": env["ephemeral_credentials"],
            "private_artifacts": env["private_artifacts"],
            "issued_at": now,
            "expiry": expiry,
        }
        unsigned = AttestationDocument(signature="", **fields)
        signature = (
            "forged-not-the-doc-digest"
            if self.attestation_mode == "tampered"
            else unsigned.doc_digest()
        )
        return AttestationDocument(signature=signature, **fields)

    def release_key(self, request: KeyReleaseRequest) -> KeyReleaseTicket:
        material = f"double-key-material-{next(self._keys)}".encode()
        ticket = KeyReleaseTicket(
            key_id=f"double-key-{next(self._keys)}",
            job_ref=request.job_ref,
            ttl_seconds=request.ttl_seconds,
            issued_at=datetime.now(UTC),
            ephemeral=True,
            key_material=material,
        )
        self.released_keys.append(ticket)
        return ticket

    # -- job lifecycle --------------------------------------------------------

    def submit_confidential(
        self,
        *,
        job: ConfidentialJobSpec,
        payload: bytes,
        key: KeyReleaseTicket,
    ) -> JobHandle:
        if self.fail_submit is not None:
            raise self.fail_submit
        if job.payload_digest != sha256_bytes(payload):
            raise RuntimeError("payload digest mismatch — payload changed after approval")
        env = dict(self.DEFAULT_ENVIRONMENT)
        env.update(self.doc_overrides)
        recipient = Recipient(
            provider=env["provider"],
            account=env["account"],
            region=env["region"],
            environment=env["environment"],
        )
        handle = self._inner.submit(recipient=recipient, job=job.job, payload=payload)
        self.received[handle.job_id] = payload
        self.confidential_jobs[handle.job_id] = job
        return handle

    def status(self, handle: JobHandle) -> JobStatus:
        return self._inner.status(handle)

    def cancel(self, handle: JobHandle) -> JobStatus:
        return self._inner.cancel(handle)

    def delete(self, handle: JobHandle) -> DeletionReceipt:
        receipt = self._inner.delete(handle)
        if receipt.deleted:
            self.received.pop(handle.job_id, None)
            self.outputs.pop(handle.job_id, None)
        return receipt

    def drain_callbacks(self, handle: JobHandle) -> list[CallbackEvent]:
        return self._inner.drain_callbacks(handle)

    def succeed(self, handle: JobHandle, artifacts: tuple[str, ...] = ()) -> None:
        self._inner.succeed(handle, artifacts=artifacts)

    def inject_callback(
        self,
        handle: JobHandle,
        event: str,
        *,
        seq: int | None = None,
        callback_id: str | None = None,
        artifacts: tuple[str, ...] = (),
    ) -> None:
        self._inner.inject_callback(
            handle, event, seq=seq, callback_id=callback_id, artifacts=artifacts
        )

    # -- outputs + storage probe ----------------------------------------------

    def push_output(
        self,
        handle: JobHandle,
        *,
        artifact_id: str,
        content: bytes,
        media: str = "application/octet-stream",
        private: bool = True,
        access_ttl_seconds: int = 300,
    ) -> ImportedArtifact:
        """Register a job output artifact for import."""
        artifact = ImportedArtifact(
            artifact_id=artifact_id,
            media=media,
            byte_size=len(content),
            sha256=sha256_bytes(content),
            private=private,
            access_ttl_seconds=access_ttl_seconds,
            content=content,
        )
        self.outputs.setdefault(handle.job_id, []).append(artifact)
        return artifact

    def import_outputs(self, handle: JobHandle) -> list[ImportedArtifact]:
        return list(self.outputs.get(handle.job_id, []))

    def retained_bytes(self, handle: JobHandle) -> int:
        payload = len(self.received.get(handle.job_id, b""))
        artifacts = sum(a.byte_size for a in self.outputs.get(handle.job_id, []))
        return payload + artifacts
