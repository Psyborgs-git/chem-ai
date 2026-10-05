"""Pinned BayBE integration; imports no optional science dependencies in core."""

from .adapter import BayBEAdapter
from .contracts import CampaignSpec, EngineFailure

__all__ = ["BayBEAdapter", "CampaignSpec", "EngineFailure"]
