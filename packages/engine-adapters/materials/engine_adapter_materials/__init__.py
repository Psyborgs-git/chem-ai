"""Pinned thermo integration; imports no optional science dependencies in core."""

from .adapter import ThermoAdapter
from .contracts import EngineFailure, MaterialsJobSpec, MaterialsOutcome

__all__ = ["EngineFailure", "MaterialsJobSpec", "MaterialsOutcome", "ThermoAdapter"]
