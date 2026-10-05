"""Pinned QCEngine integration; imports no optional science dependencies in core."""

from .adapter import QCEngineAdapter
from .contracts import EngineFailure, QuantumJobSpec, QuantumOutcome

__all__ = ["EngineFailure", "QCEngineAdapter", "QuantumJobSpec", "QuantumOutcome"]
