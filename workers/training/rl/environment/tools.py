"""Approved typed tools for the RL environment (CS-0901, §19.2).

Two execution classes only — both computational and replay-derived,
never physical (§19.1):

- ``ReplayTool``: a recorded outcome pinned in the evidence snapshot.
  A match returns the recorded payload *marked as replay* with
  provenance; a miss returns an explicit ``unavailable`` — never an
  invented oracle (AT-0901-3).
- ``ComputationalTool``: a pure deterministic check executed in
  process (no I/O, no network, no subprocess).

The catalog is closed: names absent from it are refused, and the
``FORBIDDEN_TOOLS`` verbs — physical experiment, export/egress,
hidden-label access, approval/promotion actions — are denied with
zero execution. Denied verbs are mapped to the capability they would
require; a policy principal can never hold any of them.
"""

from __future__ import annotations

from typing import Any, Protocol

from chem_studio_policy.capabilities import (
    CAP_APPROVE_EXPERIMENT,
    CAP_APPROVE_EXPORT,
    CAP_APPROVE_MODEL,
    CAP_READ_EVAL_LABELS,
    CAP_READ_PROJECT,
    CAP_REQUEST_COMPUTE,
)

from .contracts import EvidenceSnapshot, ReplayEntry


class ToolUnavailable(Exception):
    """Explicit unavailability — surfaced as status, never as data."""


class EnvTool(Protocol):
    """One approved environment tool."""

    name: str
    kind: str  # "replay" | "computational"
    compute_cost: float
    required_capability: str
    input_schema: dict[str, Any]

    def execute(
        self, arguments: dict[str, Any], snapshot: EvidenceSnapshot
    ) -> tuple[dict[str, Any], ReplayEntry | None]:
        """Return ``(result_payload, replay_entry_or_None)``.

        ``ToolUnavailable`` signals an explicit unavailable result;
        anything else raised becomes a typed tool error observation.
        """
        ...


# --- forbidden verbs ------------------------------------------------
# Each maps to the capability a caller would need. Agents lose
# approval capabilities and all non-service principals lose
# service-only capabilities, so no policy can ever hold one.

FORBIDDEN_TOOLS: dict[str, str] = {
    # physical experiment autonomy — the env is computational/replay
    # only; a lab action is always denied (§19.1, AT-0901-2)
    "run_physical_experiment": CAP_APPROVE_EXPERIMENT,
    "submit_lab_job": CAP_APPROVE_EXPERIMENT,
    "execute_lab_plan": CAP_APPROVE_EXPERIMENT,
    "schedule_experiment": CAP_APPROVE_EXPERIMENT,
    # export / egress — local-first vault; no unauthorized egress
    "export_data": CAP_APPROVE_EXPORT,
    "request_export": CAP_APPROVE_EXPORT,
    "export_artifact": CAP_APPROVE_EXPORT,
    "upload_vault": CAP_APPROVE_EXPORT,
    "sync_to_cloud": CAP_APPROVE_EXPORT,
    "fetch_external": CAP_APPROVE_EXPORT,
    # hidden evaluation labels — service-only capability
    "read_eval_labels": CAP_READ_EVAL_LABELS,
    "hidden_targets": CAP_READ_EVAL_LABELS,
    "evaluation_labels": CAP_READ_EVAL_LABELS,
    # approvals / promotion — never an agent capability
    "promote_model": CAP_APPROVE_MODEL,
    "approve_model_release": CAP_APPROVE_MODEL,
    "approve_experiment": CAP_APPROVE_EXPERIMENT,
    "approve_export": CAP_APPROVE_EXPORT,
}


# --- replay tools ---------------------------------------------------


class ReplayTool:
    """Recorded-outcome tool — matched on canonical (name, arguments)."""

    def __init__(
        self,
        name: str,
        *,
        compute_cost: float,
        required_capability: str,
        input_schema: dict[str, Any],
    ) -> None:
        self.name = name
        self.kind = "replay"
        self.compute_cost = compute_cost
        self.required_capability = required_capability
        self.input_schema = input_schema

    def execute(
        self, arguments: dict[str, Any], snapshot: EvidenceSnapshot
    ) -> tuple[dict[str, Any], ReplayEntry | None]:
        entry = snapshot.lookup(self.name, arguments)
        if entry is None:
            raise ToolUnavailable(f"no replay recorded for {self.name}")
        return dict(entry.result), entry


# --- computational tools --------------------------------------------


def _check_formulation(arguments: dict[str, Any]) -> dict[str, Any]:
    """Deterministic formulation validity check — pure stdlib.

    Cheap by design: this is the call a spamming policy tries to farm.
    Validity is reported honestly; it never substitutes for evidence
    or task completion.
    """
    formulation = arguments.get("formulation") or {}
    components = formulation.get("components") or []
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    total = 0.0
    for index, comp in enumerate(components):
        name = str(comp.get("name") or "")
        if not name:
            findings.append({"severity": "blocking", "detail": f"component {index} has no name"})
        elif name in seen:
            findings.append({"severity": "blocking", "detail": f"duplicate component '{name}'"})
        seen.add(name)
        try:
            fraction = float(comp.get("fraction"))
        except (TypeError, ValueError):
            findings.append(
                {"severity": "blocking", "detail": f"component '{name}' fraction missing/invalid"}
            )
            continue
        if fraction <= 0 or fraction > 1:
            findings.append(
                {
                    "severity": "blocking",
                    "detail": f"component '{name}' fraction {fraction} outside (0,1]",
                }
            )
        total += fraction
    if not components:
        findings.append({"severity": "blocking", "detail": "formulation has no components"})
    elif abs(total - 1.0) > 1e-6:
        findings.append(
            {
                "severity": "blocking",
                "detail": f"component fractions sum to {total:.6f}, expected 1.0",
            }
        )
    return {
        "valid": not any(f["severity"] == "blocking" for f in findings),
        "findings": findings,
        "evidence_class": "descriptor",
    }


class ComputationalTool:
    def __init__(
        self,
        name: str,
        *,
        compute_cost: float,
        required_capability: str,
        input_schema: dict[str, Any],
        check: Any,
    ) -> None:
        self.name = name
        self.kind = "computational"
        self.compute_cost = compute_cost
        self.required_capability = required_capability
        self.input_schema = input_schema
        self._check = check

    def execute(
        self, arguments: dict[str, Any], snapshot: EvidenceSnapshot
    ) -> tuple[dict[str, Any], ReplayEntry | None]:
        return self._check(arguments), None


_OBJECT = {"type": "object", "additionalProperties": True}


def default_catalog() -> list[EnvTool]:
    """The closed approved tool set. Names deliberately mirror the
    production agent catalog where the action semantics match — the
    replay variants return the *recorded* outcome of the same call."""
    return [
        ReplayTool(
            name="search_evidence",
            compute_cost=0.5,
            required_capability=CAP_READ_PROJECT,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        ReplayTool(
            name="read_candidate_revision",
            compute_cost=0.5,
            required_capability=CAP_READ_PROJECT,
            input_schema={
                "type": "object",
                "properties": {"candidate_revision_id": {"type": "string"}},
                "required": ["candidate_revision_id"],
                "additionalProperties": False,
            },
        ),
        ReplayTool(
            name="get_evidence_record",
            compute_cost=0.5,
            required_capability=CAP_READ_PROJECT,
            input_schema={
                "type": "object",
                "properties": {"evidence_id": {"type": "string"}},
                "required": ["evidence_id"],
                "additionalProperties": False,
            },
        ),
        ReplayTool(
            name="summarize_task_evidence",
            compute_cost=0.5,
            required_capability=CAP_READ_PROJECT,
            input_schema={
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
                "additionalProperties": False,
            },
        ),
        ReplayTool(
            name="request_calculation",
            compute_cost=4.0,
            required_capability=CAP_REQUEST_COMPUTE,
            input_schema={
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "request": _OBJECT,
                    "task_id": {"type": "string"},
                },
                "required": ["kind", "request"],
                "additionalProperties": False,
            },
        ),
        ComputationalTool(
            name="validate_formulation",
            compute_cost=0.1,
            required_capability=CAP_REQUEST_COMPUTE,
            input_schema={
                "type": "object",
                "properties": {"formulation": _OBJECT},
                "required": ["formulation"],
                "additionalProperties": False,
            },
            check=_check_formulation,
        ),
    ]
