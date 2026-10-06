"""The confidential-execution backend protocol.

A real provider implements this surface (attestation evidence, key
release, confidential submit/cancel/delete, output import, storage
probe). The adapter speaks ``CloudProvider`` upward to the broker and
this protocol downward to the provider — every byte of an approved
payload still traverses the CS-1003 egress broker.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from cloud_broker.types import (
    CallbackEvent,
    DeletionReceipt,
    JobHandle,
    JobStatus,
)
from cloud_providers.types import (
    AttestationDocument,
    ConfidentialJobSpec,
    ImportedArtifact,
    KeyReleaseRequest,
    KeyReleaseTicket,
)


@runtime_checkable
class ConfidentialBackend(Protocol):
    """Provider-side machinery for confidential execution.

    ``kind`` is honest labelling: ``"synthetic"`` for in-process doubles
    used by tests, ``"live"`` for a real owner-approved provider. A
    synthetic backend can never report live capability.
    """

    name: str
    kind: Literal["synthetic", "live"]

    def attestation_document(self) -> AttestationDocument | None:
        """Fetch current attestation evidence for the environment."""
        ...

    def release_key(self, request: KeyReleaseRequest) -> KeyReleaseTicket:
        """Release ephemeral job key material to the verified environment."""
        ...

    def submit_confidential(
        self,
        *,
        job: ConfidentialJobSpec,
        payload: bytes,
        key: KeyReleaseTicket,
    ) -> JobHandle:
        """Submit an approved payload into the confidential environment."""
        ...

    def status(self, handle: JobHandle) -> JobStatus: ...

    def cancel(self, handle: JobHandle) -> JobStatus: ...

    def delete(self, handle: JobHandle) -> DeletionReceipt: ...

    def drain_callbacks(self, handle: JobHandle) -> list[CallbackEvent]: ...

    def import_outputs(self, handle: JobHandle) -> list[ImportedArtifact]:
        """Return the job's output artifacts for import."""
        ...

    def retained_bytes(self, handle: JobHandle) -> int:
        """Bytes the provider still holds for the job (post-delete probe)."""
        ...
