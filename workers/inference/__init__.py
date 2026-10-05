"""Local inference runtime (§10.2, model-runtime handshake).

A provider-neutral adapter over a pinned, licensed local model. The
handshake verifies the model's sha256, the chat template and — by
actually calling the server — structured-output behavior. Nothing is
assumed: an uninstalled runtime reports ``available=False`` and the
manual workflow stays usable (AT-0405-3).
"""

from workers.inference.runtime import (
    HandshakeReport,
    LlamaCppRuntime,
    ModelSpec,
    TurnBudget,
)

__all__ = ["HandshakeReport", "LlamaCppRuntime", "ModelSpec", "TurnBudget"]
