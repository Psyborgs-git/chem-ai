"""Cloud egress broker package (CS-1003, handoff §20.2, §20.5).

The broker is the ONLY outbound path for export payloads. It binds an
attempt to the exact approved manifest (digest equality), enforces the
deny-by-default policy at the bytes boundary, and records honest
attempt/callback/reconcile/deletion lineage. No production provider is
configured — the in-process ``ProviderDouble`` exercises the real flow;
live providers stay ``not_configured``.
"""

from cloud_broker.broker import EgressBroker, TransferDenied, ValidationReport
from cloud_broker.double import ProviderDouble
from cloud_broker.gate import EgressDenied, EgressGate
from cloud_broker.providers import CloudProvider, ProviderNotConfigured, get_provider
from cloud_broker.types import (
    ApprovedBinding,
    AttemptRecord,
    CallbackEvent,
    DeletionReceipt,
    JobHandle,
    JobLineage,
    JobStatus,
    Permit,
    Recipient,
    ReconcileReport,
    TransferLimits,
    TransferOrder,
)

__all__ = [
    "ApprovedBinding",
    "AttemptRecord",
    "CallbackEvent",
    "CloudProvider",
    "DeletionReceipt",
    "EgressBroker",
    "EgressDenied",
    "EgressGate",
    "JobHandle",
    "JobLineage",
    "JobStatus",
    "Permit",
    "ProviderDouble",
    "ProviderNotConfigured",
    "Recipient",
    "ReconcileReport",
    "TransferDenied",
    "TransferLimits",
    "TransferOrder",
    "ValidationReport",
    "get_provider",
]
