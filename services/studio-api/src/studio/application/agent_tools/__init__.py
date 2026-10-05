"""Typed agent tools (§10.2/§10.3).

Every tool has a JSON Schema input and a typed output; handlers call
the same domain services as the UI. There are deliberately no tools
for approval, export, promotion, or closure — the catalog itself is
the boundary, and capability checks inside the services are the
backstop (AT-0405-2).
"""

from studio.application.agent_tools.registry import (
    AgentTool,
    ToolDispatcher,
    ToolRegistry,
    default_registry,
)
from studio.application.agent_tools.turn import AgentTurnRunner, TurnOutcome

__all__ = [
    "AgentTool",
    "AgentTurnRunner",
    "ToolDispatcher",
    "ToolRegistry",
    "TurnOutcome",
    "default_registry",
]
