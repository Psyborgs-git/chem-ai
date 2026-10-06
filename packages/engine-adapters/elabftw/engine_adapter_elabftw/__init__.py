"""Optional explicit eLabFTW bridge (CS-0506); off by default, no live call ever made."""

from .adapter import ElabftwAdapter
from .contracts import (
    ADAPTER_VERSION,
    ElnBadResponse,
    ElnConfig,
    ElnDisabled,
    ElnEntityRecord,
    ElnError,
    ElnInvalidInput,
    ElnLink,
    ElnNotConfigured,
    ElnUnreachable,
    ExportResult,
    ImportVerdict,
    LocalExportRecord,
)
from .mapping import entity_to_record, load_fixture, to_export_payload
from .transport import FixtureElnTransport, HttpElnTransport

__all__ = [
    "ADAPTER_VERSION",
    "ElabftwAdapter",
    "ElnBadResponse",
    "ElnConfig",
    "ElnDisabled",
    "ElnEntityRecord",
    "ElnError",
    "ElnInvalidInput",
    "ElnLink",
    "ElnNotConfigured",
    "ElnUnreachable",
    "ExportResult",
    "FixtureElnTransport",
    "HttpElnTransport",
    "ImportVerdict",
    "LocalExportRecord",
    "entity_to_record",
    "load_fixture",
    "to_export_payload",
]
