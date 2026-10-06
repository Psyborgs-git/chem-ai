"""CS-1001 unit tests — fallback decision logic (pure, no DB).

AT-1001-1  a local job that is feasible (even when "cloud would be
           faster") never authorizes cloud automatically.
"""

from __future__ import annotations

import uuid

import pytest

from studio.domain.runs.feasibility import (
    DECISION_EXPORT_PROPOSED,
    DECISION_LOCAL_FEASIBLE,
    FallbackDecision,
    GroupState,
    cloud_capability,
    decision_for,
    evaluate_spec,
    parse_job_spec,
)
from studio.errors import DomainError

GB = 1024**3


def _group(
    name: str = "compute",
    *,
    capacity: dict | None = None,
    reserve: dict | None = None,
    reserved: dict | None = None,
) -> GroupState:
    return GroupState(
        name=name,
        capacity=capacity
        or {"cpu_cores": 8, "memory_bytes": 16 * GB, "gpu_devices": 0, "storage_bytes": 100 * GB},
        reserve=reserve or {"memory_bytes": 4 * GB},
        reserved=reserved or {},
    )


# AT-1001-1 -----------------------------------------------------------


def test_feasible_job_cloud_preference_never_authorizes() -> None:
    """'Cloud is faster' never meets the bar: a job that fits locally
    evaluates feasible and the only legal decision is local_feasible —
    there is no authorized-cloud outcome in the vocabulary."""
    request = {
        "operation": "simulation",
        "sizes": {"modelBytes": 2 * GB, "dataBytes": GB},
        "envelope": {"cpu_cores": 4, "memory_bytes": 8 * GB, "wall_seconds": 600},
        # A caller may *prefer* cloud — it is not a feasibility input.
        "preferCloud": True,
        "cloudFaster": True,
    }
    spec = parse_job_spec(request, default_operation="simulation")
    evaluation = evaluate_spec(spec, [_group()])
    assert evaluation.verdict == "feasible"
    assert decision_for(evaluation) == DECISION_LOCAL_FEASIBLE
    # The decision type has no path that authorizes cloud work.
    decision = FallbackDecision(decision=DECISION_LOCAL_FEASIBLE, report_id=uuid.uuid4())
    assert decision.cloud_authorized is False
    assert decision.proposal_id is None


def test_infeasible_decision_is_proposal_not_submission() -> None:
    request = {
        "operation": "simulation",
        "envelope": {"cpu_cores": 64, "memory_bytes": 256 * GB, "wall_seconds": 600},
    }
    spec = parse_job_spec(request, default_operation="simulation")
    evaluation = evaluate_spec(spec, [_group()])
    assert evaluation.verdict == "infeasible"
    assert decision_for(evaluation) == DECISION_EXPORT_PROPOSED


def test_busy_capacity_is_not_infeasible() -> None:
    """A currently-reserved group is 'busy' — slower/waiting is not
    impossible, and busy capacity still counts as locally feasible."""
    big = {"memory_bytes": 12 * GB, "wall_seconds": 600}
    spec = parse_job_spec(
        {"operation": "simulation", "envelope": big},
        default_operation="simulation",
    )
    groups = [_group(reserved={"memory_bytes": 8 * GB, "concurrency": 0})]
    evaluation = evaluate_spec(spec, groups)
    assert evaluation.verdict == "feasible"
    approved = evaluation.configurations[0]
    assert approved.verdict == "busy"
    assert approved.busy_groups == ["compute"]


def test_unobserved_dimension_is_missing_not_assumed() -> None:
    """A dimension the group does not observe can never be assumed
    sufficient — it is reported missing and marks infeasibility."""
    spec = parse_job_spec(
        {
            "operation": "training",
            "envelope": {"gpu_devices": 1, "memory_bytes": 1 * GB, "wall_seconds": 60},
        },
        default_operation="training",
    )
    group = _group(capacity={"cpu_cores": 8, "memory_bytes": 16 * GB})  # no gpu key
    evaluation = evaluate_spec(spec, [group])
    assert evaluation.verdict == "infeasible"
    assert "gpu_devices" in evaluation.missing


def test_minor_alternative_can_rescue_feasibility() -> None:
    """Supported local alternatives within the approved task are tried:
    a smaller-batch variant that fits keeps the job local."""
    spec = parse_job_spec(
        {
            "operation": "training",
            "envelope": {"memory_bytes": 30 * GB, "wall_seconds": 600},
            "alternatives": [
                {
                    "name": "half-batch",
                    "kind": "batch_reduction",
                    "qualityImpact": "minor",
                    "envelope": {"memory_bytes": 8 * GB, "wall_seconds": 1200},
                }
            ],
        },
        default_operation="training",
    )
    evaluation = evaluate_spec(spec, [_group()])
    assert evaluation.verdict == "feasible"
    alt = evaluation.configurations[1]
    assert alt.verdict == "fits"
    assert alt.fits_group == "compute"


def test_material_quality_change_cannot_rescue_alone() -> None:
    """A fitting configuration whose quality impact is material is
    excluded pending human approval — it cannot establish feasibility."""
    spec = parse_job_spec(
        {
            "operation": "training",
            "envelope": {"memory_bytes": 30 * GB, "wall_seconds": 600},
            "alternatives": [
                {
                    "name": "fp8-degraded",
                    "kind": "precision",
                    "qualityImpact": "material_needs_approval",
                    "envelope": {"memory_bytes": 4 * GB, "wall_seconds": 600},
                }
            ],
        },
        default_operation="training",
    )
    evaluation = evaluate_spec(spec, [_group()])
    assert evaluation.verdict == "infeasible"
    alt = evaluation.configurations[1]
    assert alt.verdict == "excluded"
    assert alt.requires_quality_approval is True
    assert any(r.get("verdict") == "requires_quality_approval" for r in evaluation.reasons)


def test_upper_bound_used_for_fit() -> None:
    """Feasibility uses the declared upper bound — the conservative
    edge of the estimate, not the optimistic one."""
    spec = parse_job_spec(
        {
            "operation": "simulation",
            "envelope": {"memory_bytes": 4 * GB, "wall_seconds": 60},
            "estimates": {"memory_bytes": {"low": 2 * GB, "high": 20 * GB}},
        },
        default_operation="simulation",
    )
    evaluation = evaluate_spec(spec, [_group()])
    assert evaluation.verdict == "infeasible"


def test_incompatible_alternative_is_excluded() -> None:
    spec = parse_job_spec(
        {
            "operation": "simulation",
            "envelope": {"memory_bytes": 30 * GB, "wall_seconds": 60},
            "alternatives": [
                {
                    "name": "cuda-only",
                    "kind": "offload",
                    "compatible": False,
                    "envelope": {"gpu_devices": 1, "wall_seconds": 60},
                }
            ],
        },
        default_operation="simulation",
    )
    evaluation = evaluate_spec(spec, [_group()])
    assert evaluation.verdict == "infeasible"
    assert evaluation.configurations[1].verdict == "excluded"


def test_no_groups_is_infeasible() -> None:
    spec = parse_job_spec(
        {"operation": "simulation", "envelope": {"memory_bytes": 1 * GB}},
        default_operation="simulation",
    )
    evaluation = evaluate_spec(spec, [])
    assert evaluation.verdict == "infeasible"


# spec validation ------------------------------------------------------


def test_spec_validation_bounds() -> None:
    with pytest.raises(DomainError):
        parse_job_spec({"envelope": {"memory_bytes": -1}}, default_operation="x")
    with pytest.raises(DomainError):
        parse_job_spec(
            {"estimates": {"memory_bytes": {"low": 5, "high": 2}}},
            default_operation="x",
        )
    with pytest.raises(DomainError):
        parse_job_spec({"alternatives": [{"name": "a", "scale": 1.5}]}, default_operation="x")
    with pytest.raises(DomainError):
        parse_job_spec({"sizes": {"modelBytes": "big"}}, default_operation="x")


def test_cloud_capability_is_honest_not_configured() -> None:
    cap = cloud_capability()
    assert cap["status"] == "not_configured"
    assert cap["provider"] is None and cap["account"] is None and cap["budget"] is None
    assert cap["egress"] == "deny"
