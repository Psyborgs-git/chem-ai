"""Confidential-execution provider adapter (CS-1004).

The confidential adapter that sits between the CS-1003 egress broker
and an owner-approved confidential cloud backend. With no owner
approval bound (U08/U09/U11 open), the surface reports
``not_configured`` and stays inert — the honest state, never faked
live.
"""

from cloud_providers.adapter import (
    AttestationRefused,
    ConfidentialDenied,
    ConfidentialExecutionAdapter,
    ImportRefused,
    ProvenanceRefused,
)
from cloud_providers.attestation import verify_attestation
from cloud_providers.backend import ConfidentialBackend
from cloud_providers.double import ConfidentialDouble
from cloud_providers.registry import (
    APPROVAL_CAPABILITY,
    CONFIDENTIAL_ADAPTERS,
    ApprovalRequired,
    clear,
    confidential_capability,
    register,
    resolve,
)
from cloud_providers.types import (
    ApprovalRef,
    ApprovedEnvironment,
    AttestationCheck,
    AttestationDocument,
    AttestationVerdict,
    ConfidentialJobSpec,
    ConfidentialReconcile,
    ImportedArtifact,
    ImportedOutputs,
    KeyReleaseRequest,
    KeyReleaseTicket,
    ProviderObservation,
    StorageVerification,
)

__all__ = [
    "APPROVAL_CAPABILITY",
    "CONFIDENTIAL_ADAPTERS",
    "ApprovalRef",
    "ApprovalRequired",
    "ApprovedEnvironment",
    "AttestationCheck",
    "AttestationDocument",
    "AttestationRefused",
    "AttestationVerdict",
    "ConfidentialBackend",
    "ConfidentialDenied",
    "ConfidentialDouble",
    "ConfidentialExecutionAdapter",
    "ConfidentialJobSpec",
    "ConfidentialReconcile",
    "ImportRefused",
    "ImportedArtifact",
    "ImportedOutputs",
    "KeyReleaseRequest",
    "KeyReleaseTicket",
    "ProvenanceRefused",
    "ProviderObservation",
    "StorageVerification",
    "clear",
    "confidential_capability",
    "register",
    "resolve",
    "verify_attestation",
]
