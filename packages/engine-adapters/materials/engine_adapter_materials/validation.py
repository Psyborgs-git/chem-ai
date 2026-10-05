"""Parameter/domain validation and the persisted job payload (§16.3).

Pure Python — no thermo import — so the host process can validate the
declared job and persist the canonical payload without science deps
(E05). Two tables of *published* chemical data are embedded here:

* ``LLE_SUBGROUPS``: the UNIFAC-LLE subgroup ids and their main-group
  membership (Magnussen/Rasmussen/Fredenslund 1981 table, as shipped by
  thermo 0.6.1 as ``LLEUFSG``).
* ``LLE_INTERACTION_PAIRS``: the directional main-group pairs covered
  by the shipped ``LLEUFIP`` interaction table.

The coverage check matters because thermo *silently zero-fills* a
missing interaction pair — a guess by omission, which §16.3 forbids.
The host rejects under-parameterized requests before execution; the
container re-checks against the live table and fails closed on drift.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    DOES_NOT_ESTABLISH,
    METHOD_ID,
    METHOD_VERSION,
    SCHEMA_VERSION,
    EngineFailure,
    MaterialsJobSpec,
)

# subgroup_id -> (subgroup name, main_group_id); mirrors thermo LLEUFSG.
LLE_SUBGROUPS: dict[int, tuple[str, int]] = {
    1: ("CH3", 1),
    2: ("CH2", 1),
    3: ("CH", 1),
    4: ("C", 1),
    5: ("CH2=CH", 2),
    6: ("CH=CH", 2),
    7: ("CH2=C", 2),
    8: ("CH=C", 2),
    9: ("ACH", 3),
    10: ("AC", 3),
    11: ("ACCH3", 4),
    12: ("ACCH2", 4),
    13: ("ACCH", 4),
    14: ("OH", 5),
    15: ("P1", 6),
    16: ("P2", 7),
    17: ("H2O", 8),
    18: ("ACOH", 9),
    19: ("CH3CO", 10),
    20: ("CH2CO", 10),
    21: ("CHO", 11),
    22: ("Furfural", 12),
    23: ("COOH", 13),
    24: ("HCOOH", 13),
    25: ("CH3COO", 14),
    26: ("CH2COO", 14),
    27: ("CH3O", 15),
    28: ("CH2O", 15),
    29: ("CHO", 15),
    30: ("FCH2O", 15),
    31: ("CH2CL", 16),
    32: ("CHCL", 16),
    33: ("CCL", 16),
    34: ("CH2CL2", 17),
    35: ("CHCL2", 17),
    36: ("CCL2", 17),
    37: ("CHCL3", 18),
    38: ("CCL3", 18),
    39: ("CCL4", 19),
    40: ("ACCL", 20),
    41: ("CH3CN", 21),
    42: ("CH2CN", 21),
    43: ("ACNH2", 22),
    44: ("CH3NO2", 23),
    45: ("CH2NO2", 23),
    46: ("CHNO2", 23),
    47: ("ACNO2", 24),
    48: ("DOH", 25),
    49: ("(HOCH2CH2)2O", 26),
    50: ("C5H5N", 27),
    51: ("C5H4N", 27),
    52: ("C5H3N", 27),
    53: ("CCl2=CHCl", 28),
    54: ("HCONHCH3", 29),
    55: ("DMF", 30),
    56: ("(CH2)4SO2", 31),
    57: ("DMSO", 32),
}

# main_group -> covered partner main groups (directional); mirrors the
# LLEUFIP key structure. Missing = the parameter was never regressed —
# never zero-filled.
LLE_INTERACTION_PAIRS: dict[int, frozenset[int]] = {
    1: frozenset(
        {
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
        }
    ),
    2: frozenset({1, 3, 4, 5, 6, 7, 8, 10, 11, 13, 14, 15, 16, 17, 18, 19, 21, 23, 29, 30, 31, 32}),
    3: frozenset(
        {
            1,
            2,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            29,
            30,
            31,
            32,
        }
    ),
    4: frozenset(
        {
            1,
            2,
            3,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            31,
            32,
        }
    ),
    5: frozenset(
        {
            1,
            2,
            3,
            4,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
        }
    ),
    6: frozenset({1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 23}),
    7: frozenset({1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 23}),
    8: frozenset(
        {
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            27,
            28,
            29,
            30,
            31,
        }
    ),
    9: frozenset({1, 3, 4, 5, 6, 7, 8, 10, 14, 19, 22, 24, 25, 27}),
    10: frozenset(
        {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 28}
    ),
    11: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 13, 14, 16}),
    12: frozenset({1, 3, 4, 5, 6, 7, 8, 10, 11, 13, 14, 17, 18, 19, 25, 27, 28, 30}),
    13: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20, 22, 23, 25, 28}),
    14: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 17, 18, 19, 20, 21, 25}),
    15: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 14, 16, 17, 18, 19, 23}),
    16: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 13, 15, 17, 18, 19}),
    17: frozenset({1, 2, 5, 6, 7, 8, 10, 12, 13, 14, 15, 16, 19}),
    18: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 13, 14, 15, 16, 19, 21, 22, 27}),
    19: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 23, 24}),
    20: frozenset({1, 3, 4, 5, 8, 10, 13, 14, 19, 21, 23, 25, 27}),
    21: frozenset({1, 2, 3, 4, 5, 8, 10, 14, 18, 19, 20, 27}),
    22: frozenset({1, 3, 4, 5, 8, 9, 10, 13, 18, 19, 24, 25, 27}),
    23: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 19, 20, 25}),
    24: frozenset({1, 3, 4, 5, 8, 9, 10, 19, 22, 25}),
    25: frozenset({1, 3, 4, 5, 8, 9, 10, 12, 13, 14, 20, 22, 23, 24}),
    26: frozenset({1, 3, 4, 5}),
    27: frozenset({1, 3, 4, 5, 8, 9, 12, 18, 20, 21, 22}),
    28: frozenset({1, 5, 8, 10, 12, 13}),
    29: frozenset({1, 2, 3, 8}),
    30: frozenset({1, 2, 3, 8, 12}),
    31: frozenset({1, 2, 3, 4, 8}),
    32: frozenset({1, 2, 3, 4}),
}


def component_main_groups(groups: dict[str, int]) -> frozenset[int]:
    """Main-group set of one component's subgroup decomposition.
    Unknown subgroup ids are unsupported input — never skipped."""
    mains: set[int] = set()
    for key in groups:
        sid = int(key)
        entry = LLE_SUBGROUPS.get(sid)
        if entry is None:
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                f"subgroup id {sid} is not in the UNIFAC-LLE subgroup table — "
                "the component cannot be expressed in this method's domain",
            )
        mains.add(entry[1])
    return frozenset(mains)


def check_parameter_coverage(spec: MaterialsJobSpec) -> None:
    """Required-parameter check (AT-0702-1): every directional
    main-group pair the evaluation needs must exist in the shipped
    interaction table. Missing pairs -> MISSING_PARAMETERS — the
    capability is blocked, never silently zero-filled."""
    mains: set[int] = set()
    for comp in spec.components:
        mains |= set(component_main_groups(comp.unifac_groups))
    missing: list[str] = []
    for a in sorted(mains):
        for b in sorted(mains):
            if a == b:
                continue
            if b not in LLE_INTERACTION_PAIRS.get(a, frozenset()):
                missing.append(f"{a}->{b}")
    if missing:
        raise EngineFailure(
            "MISSING_PARAMETERS",
            "UNIFAC-LLE interaction parameters are not regressed for "
            f"main-group pair(s) {missing[:8]} — no substitute is assumed",
        )


def build_job_payload(spec: MaterialsJobSpec) -> dict[str, Any]:
    """The canonical persisted input — the exact bytes stored in the
    vault before execution and consumed inside the isolated worker."""
    check_parameter_coverage(spec)
    return {
        "schema_name": SCHEMA_VERSION,
        "schema_version": 1,
        "method": METHOD_ID,
        "method_version": METHOD_VERSION,
        "components": [
            {
                "name": c.name,
                "unifac_groups": {
                    str(k): v for k, v in sorted(((int(k), v) for k, v in c.unifac_groups.items()))
                },
            }
            for c in spec.components
        ],
        "conditions": {
            "temperature_k": spec.conditions.temperature_k,
            "nominal_x1": spec.conditions.nominal_x1,
        },
        "grid_points": spec.grid_points,
        "adapter_version": ADAPTER_VERSION,
    }


# ------------------------------------------------------------------
# Convex-hull stability criterion (deterministic, grid-bounded)
# ------------------------------------------------------------------


def gibbs_mixing_surface(xs: list[float], gammas: list[tuple[float, float]]) -> list[float]:
    """g_mix/RT = sum_i x_i ln(x_i * gamma_i) over the grid — the scalar
    field the convex-hull criterion is applied to."""
    surface: list[float] = []
    for x, (g1, g2) in zip(xs, gammas, strict=True):
        if g1 <= 0 or g2 <= 0 or not (math.isfinite(g1) and math.isfinite(g2)):
            raise EngineFailure(
                "ENGINE_MALFORMED_OUTPUT",
                "engine produced a non-positive or non-finite activity coefficient",
            )
        surface.append(x * math.log(x * g1) + (1 - x) * math.log((1 - x) * g2))
    return surface


def lower_convex_hull(xs: list[float], ys: list[float]) -> list[tuple[float, float]]:
    """Lower convex envelope of sampled (x, y) points — the equilibrium
    free-energy surface. Where the true surface rises above a hull
    chord, the homogeneous phase is unstable and the system splits."""
    hull: list[tuple[float, float]] = []
    for x, y in zip(xs, ys, strict=True):
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
            if cross <= 0:
                hull.pop()
            else:
                break
        hull.append((x, y))
    return hull


def miscibility_gaps(
    xs: list[float],
    surface: list[float],
    *,
    hull_tolerance: float = 1e-4,
    min_gap_width: float = 0.01,
) -> list[tuple[float, float]]:
    """Composition intervals where the mixing surface sits above its
    lower convex hull — grid-resolution-limited binodal bounds.

    Coordinates are mole fraction of component 0, matching the request
    convention."""
    hull = lower_convex_hull(xs, surface)
    gaps: list[tuple[float, float]] = []
    for (xa, ya), (xb, yb) in itertools.pairwise(hull):
        if xb - xa < min_gap_width:
            continue
        # A hull edge is a miscibility gap iff the sampled surface
        # between the contact points rises above the chord — every
        # interior grid point is checked, not just a midpoint probe.
        interior = [i for i, x in enumerate(xs) if xa < x < xb]
        exceeds = False
        for i in interior:
            chord = ya + (yb - ya) * (xs[i] - xa) / (xb - xa)
            if surface[i] - chord > hull_tolerance:
                exceeds = True
                break
        if exceeds:
            gaps.append((xa, xb))
    return gaps


# ------------------------------------------------------------------
# Endpoint scope (AT-0702-2) — structural proxy/product separation
# ------------------------------------------------------------------


def evaluate_endpoint(outcome_supports: tuple[str, ...], endpoint: str) -> dict[str, Any]:
    """Decide whether an equilibrium-proxy outcome *establishes* an
    endpoint. Product-performance endpoints are never established by
    equilibrium phase behavior — the verdict is a typed record, not a
    warning string."""
    if endpoint in DOES_NOT_ESTABLISH or endpoint not in outcome_supports:
        return {
            "endpoint": endpoint,
            "established": False,
            "verdict": "not_established",
            "basis": "proxy_scope_gap",
            "detail": (
                "a computed equilibrium miscibility result does not establish "
                f"'{endpoint}'; kinetic/product-performance endpoints require "
                "their own measured evidence"
            ),
        }
    return {
        "endpoint": endpoint,
        "established": True,
        "verdict": "within_proxy_scope",
        "basis": "method_supports_endpoint",
        "detail": (
            f"'{endpoint}' is the method's declared endpoint; the result is "
            "still a computed equilibrium proxy, not lab evidence"
        ),
    }
