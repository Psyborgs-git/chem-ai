"""Model-under-test backends (CS-0803).

The evaluation harness is real; the *executor* is pluggable. When no
local runtime is installed the default backend reports honest
unavailability — the run is refused with ENGINE_UNAVAILABLE rather
than scoring fabricated outputs (fixture-only ≠ validation).
"""

from __future__ import annotations

from typing import Any, Protocol

from .contracts import EvalArmOutput, EvalBudget, EvalTaskDef


class EvaluationBackend(Protocol):
    """Runs the model under test for one arm on one example.

    Implementations must honour the frozen budget and only use the
    tool names pinned by the suite; what the model may do is bounded
    by the tool catalog, not by backend convention.
    """

    def capability(self) -> dict[str, Any] | None:
        """Honest engine capability — ``None`` when unavailable."""
        ...

    def run_example(
        self,
        *,
        arm: str,
        task: EvalTaskDef,
        allowed_tools: list[str],
        budget: EvalBudget,
    ) -> EvalArmOutput:
        """Produce the arm's response for ``task``."""
        ...


class UnavailableBackend:
    """Default honest state — no local eval runtime is installed in the
    core profile (the llama.cpp serving runtime is U08/U13-gated)."""

    def capability(self) -> dict[str, Any] | None:
        try:
            from workers.inference.runtime import LlamaCppRuntime
        except Exception:
            return None
        runtime = LlamaCppRuntime()
        if not runtime.running():
            return None
        return {"engine": "llama.cpp", "available": True, "base_url": runtime.base_url}

    def run_example(
        self,
        *,
        arm: str,
        task: EvalTaskDef,
        allowed_tools: list[str],
        budget: EvalBudget,
    ) -> EvalArmOutput:
        return EvalArmOutput(text="", error="engine_unavailable")


class ScriptedBackend:
    """Deterministic backend for tests/dev fixtures: replies come from
    a pinned script keyed by (arm, example_id). Still exercises the
    real harness — matching, scoring, denominators, gates."""

    def __init__(self, outputs: dict[tuple[str, str], str | EvalArmOutput]) -> None:
        self._outputs = dict(outputs)
        self.calls: list[tuple[str, str]] = []

    def capability(self) -> dict[str, Any] | None:
        return {"engine": "scripted", "available": True, "dataStatus": "fixture_only"}

    def run_example(
        self,
        *,
        arm: str,
        task: EvalTaskDef,
        allowed_tools: list[str],
        budget: EvalBudget,
    ) -> EvalArmOutput:
        self.calls.append((arm, task.example_id))
        out = self._outputs.get((arm, task.example_id))
        if out is None:
            return EvalArmOutput(text="", error="no_scripted_output")
        if isinstance(out, str):
            return EvalArmOutput(text=out)
        return out


def default_backend() -> EvaluationBackend:
    return UnavailableBackend()
