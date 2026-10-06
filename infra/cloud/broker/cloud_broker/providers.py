"""Provider interface + registry (§20.2, §20.4).

``CloudProvider`` is the one provider-neutral contract the egress
broker speaks. No real provider is configured in this deployment —
``PROVIDERS`` is intentionally empty and every lookup reports
``not_configured`` honestly (a credential's existence is not approval
and a provider name is not a configured provider).

CS-1004 may register a real, owner-approved adapter here later; until
then the only working implementation is the in-process
:class:`~cloud_broker.double.ProviderDouble` used for synthetic
end-to-end exercise.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cloud_broker.types import (
    CallbackEvent,
    DeletionReceipt,
    JobHandle,
    JobStatus,
    Recipient,
)


class ProviderNotConfigured(Exception):
    """Raised when a transfer names a provider that is not configured.

    The status vocabulary is honest: ``not_configured`` — never
    'implemented' or 'available'."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"provider '{provider}' is not_configured")
        self.provider = provider
        self.status = "not_configured"


@runtime_checkable
class CloudProvider(Protocol):
    """The minimal outbound contract an approved adapter must honor.

    Every method is receipt-shaped: the provider returns evidence the
    broker records, not promises. A provider that cannot answer a
    question must say so rather than fabricate state.
    """

    name: str

    def submit(self, *, recipient: Recipient, job: str, payload: bytes) -> JobHandle:
        """Accept payload bytes for ``job`` at ``recipient``. Only ever
        reached through the egress gate with a valid permit."""
        ...

    def status(self, handle: JobHandle) -> JobStatus:
        """Current provider-side state; untrusted until reconciled."""
        ...

    def cancel(self, handle: JobHandle) -> JobStatus:
        """Best-effort cancellation; reports what was already
        transferred — never claims unseen (AT-1003-2)."""
        ...

    def delete(self, handle: JobHandle) -> DeletionReceipt:
        """Request deletion; returns the *actual* receipt plus any
        unresolved retention items (§20.5)."""
        ...

    def drain_callbacks(self, handle: JobHandle) -> list[CallbackEvent]:
        """Pull pending provider callbacks (poll-style delivery)."""
        ...


# Registered, reviewed provider adapters. Empty by design — production
# providers stay ``not_configured`` until an approved adapter exists.
PROVIDERS: dict[str, CloudProvider] = {}


def get_provider(name: str) -> CloudProvider:
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ProviderNotConfigured(name)
    return provider
