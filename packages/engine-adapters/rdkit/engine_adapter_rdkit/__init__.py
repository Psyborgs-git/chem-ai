"""RDKit engine adapter (§13.1, §13.2) — structure parsing,
sanitization and descriptors with typed outputs and the exact engine
version recorded. A valid structure is a *structural* check — never
synthesis feasibility, safety, or lab proof (§12.1)."""

from engine_adapter_rdkit.adapter import (
    ADAPTER_VERSION,
    EngineError,
    EngineInfo,
    RDKitAdapter,
    StructuralResult,
)

__all__ = [
    "ADAPTER_VERSION",
    "EngineError",
    "EngineInfo",
    "RDKitAdapter",
    "StructuralResult",
]
