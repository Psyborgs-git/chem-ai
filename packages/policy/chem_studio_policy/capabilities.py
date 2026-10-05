"""Capability model for Chemistry Studio (handoff §21.1).

Pure functions only — the backend owns authorization authority; this
package contains the shared vocabulary and checks with no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

# The §21.1 capability vocabulary — complete list, no others exist.
CAP_READ_PROJECT = "read_project"
CAP_EDIT_TASK = "edit_task"
CAP_MANAGE_SOURCES = "manage_sources"
CAP_PROPOSE_CANDIDATE = "propose_candidate"
CAP_REQUEST_COMPUTE = "request_compute"
CAP_REVIEW_SCIENCE = "review_science"
CAP_APPROVE_EXPERIMENT = "approve_experiment"
CAP_REVIEW_MEASUREMENT = "review_measurement"
CAP_MANAGE_MODELS = "manage_models"
CAP_APPROVE_MODEL = "approve_model"
CAP_REVIEW_EXPORT = "review_export"
CAP_APPROVE_EXPORT = "approve_export"
CAP_ADMINISTER_WORKSPACE = "administer_workspace"
CAP_READ_EVAL_LABELS = "read_eval_labels"

ALL_CAPABILITIES: frozenset[str] = frozenset(
    {
        CAP_READ_PROJECT,
        CAP_EDIT_TASK,
        CAP_MANAGE_SOURCES,
        CAP_PROPOSE_CANDIDATE,
        CAP_REQUEST_COMPUTE,
        CAP_REVIEW_SCIENCE,
        CAP_APPROVE_EXPERIMENT,
        CAP_REVIEW_MEASUREMENT,
        CAP_MANAGE_MODELS,
        CAP_APPROVE_MODEL,
        CAP_REVIEW_EXPORT,
        CAP_APPROVE_EXPORT,
        CAP_ADMINISTER_WORKSPACE,
        CAP_READ_EVAL_LABELS,
    }
)

# Proposed roles → capability sets (§21.1). Role names are convenience
# only; authorization always checks capabilities.
ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "owner": ALL_CAPABILITIES,
    "researcher": frozenset(
        {
            CAP_READ_PROJECT,
            CAP_EDIT_TASK,
            CAP_MANAGE_SOURCES,
            CAP_PROPOSE_CANDIDATE,
            CAP_REQUEST_COMPUTE,
        }
    ),
    "scientific_reviewer": frozenset(
        {
            CAP_READ_PROJECT,
            CAP_REVIEW_SCIENCE,
            CAP_APPROVE_EXPERIMENT,
            CAP_REVIEW_MEASUREMENT,
            CAP_REVIEW_EXPORT,
        }
    ),
    "lab_operator": frozenset({CAP_READ_PROJECT, CAP_REVIEW_MEASUREMENT}),
    "data_steward": frozenset(
        {
            CAP_READ_PROJECT,
            CAP_MANAGE_SOURCES,
            CAP_REVIEW_MEASUREMENT,
            CAP_REVIEW_EXPORT,
        }
    ),
    "viewer": frozenset({CAP_READ_PROJECT}),
    # The agent principal never inherits approval privileges (§21.1).
    "agent": frozenset(
        {
            CAP_READ_PROJECT,
            CAP_EDIT_TASK,
            CAP_PROPOSE_CANDIDATE,
            CAP_REQUEST_COMPUTE,
        }
    ),
}

# Capabilities that are always gated to human approval classes — an
# agent-kind principal is denied even if directly granted these.
APPROVAL_CAPABILITIES: frozenset[str] = frozenset(
    {
        CAP_APPROVE_EXPERIMENT,
        CAP_APPROVE_MODEL,
        CAP_APPROVE_EXPORT,
    }
)

# Capabilities only a 'service'-kind principal may hold (§18.1,
# AT-0803-2): hidden evaluation labels are reachable solely through
# the evaluation service principal — users and agents lose the grant
# at context load even if a row exists.
SERVICE_ONLY_CAPABILITIES: frozenset[str] = frozenset(
    {
        CAP_READ_EVAL_LABELS,
    }
)


@dataclass(frozen=True)
class Grant:
    """One active capability grant (optionally narrowed to a scope ref)."""

    capability: str
    scope_ref: str | None = None


def capabilities_for_role(role: str) -> frozenset[str]:
    return ROLE_CAPABILITIES.get(role, frozenset())


def has_capability(grants: frozenset[Grant], capability: str, scope_ref: str | None = None) -> bool:
    """True iff an active grant covers `capability` at `scope_ref`.

    A grant with `scope_ref=None` is workspace-wide. A scoped grant
    covers only the matching scope.
    """
    if capability not in ALL_CAPABILITIES:
        return False
    for g in grants:
        if g.capability != capability:
            continue
        if g.scope_ref is None or g.scope_ref == scope_ref:
            return True
    return False


def effective_grants(principal_kind: str, grants: frozenset[Grant]) -> frozenset[Grant]:
    """Apply principal-kind ceilings: agents lose approval capabilities;
    non-service principals lose service-only capabilities."""
    if principal_kind == "agent":
        grants = frozenset(g for g in grants if g.capability not in APPROVAL_CAPABILITIES)
    if principal_kind != "service":
        grants = frozenset(g for g in grants if g.capability not in SERVICE_ONLY_CAPABILITIES)
    return grants
