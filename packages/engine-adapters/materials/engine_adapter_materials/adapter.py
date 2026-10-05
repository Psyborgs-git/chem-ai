"""thermo execution adapter (CS-0702).

Runs inside the pinned worker image `chem-studio-materials:0.6.1-v1`
(thermo 0.6.1 / scipy / pandas). The host process validates and persists
the job payload; this side re-parses it, drift-checks it against the
persisted spec digest, verifies interaction-parameter coverage against
the *live* LLEUFIP table (thermo zero-fills missing pairs — the adapter
refuses instead), executes the grid scan, and classifies the result
honestly: finite, consistent output only — never exit-0 equals success.
"""

from __future__ import annotations

import importlib.metadata
import math
from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    DOES_NOT_ESTABLISH,
    METHOD_ID,
    METHOD_VERSION,
    SUPPORTS_ENDPOINTS,
    THERMO_VERSION,
    EngineFailure,
    MaterialsJobSpec,
    MaterialsOutcome,
)
from .validation import (
    build_job_payload,
    component_main_groups,
    gibbs_mixing_surface,
    miscibility_gaps,
)

# Grid resolution documented in the method record — the binodal bounds
# are reported at this resolution, never to finer implied precision.
_EDGE_EPS = 1e-6
_RAW_NOTE = "deterministic convex-hull screen; no engine stdout beyond this record"


def _dist_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


class ThermoAdapter:
    """Thin wrapper over thermo's UNIFAC-LLE activity model with a fixed
    input contract — the only call surface the worker exposes."""

    def capability(self) -> dict[str, Any]:
        """Report what this environment can actually run (§16.1 labels)."""
        thermo = _dist_version("thermo")
        if thermo is None:
            state = "not_installed"
        elif thermo != THERMO_VERSION:
            state = "installed_unverified"
        else:
            state = "available_tested"
        return {
            "adapter_version": ADAPTER_VERSION,
            "engine": "thermo",
            "engine_version": thermo,
            "state": state,
            "methods": {
                f"{METHOD_ID}/{METHOD_VERSION}": {
                    "state": state,
                    "endpoint": "equilibrium_miscibility",
                    "domain": (
                        "binary condensed-liquid mixtures expressible in the "
                        "UNIFAC-LLE subgroup table; ambient pressure; "
                        "temperature 278.15-333.15 K"
                    ),
                    "benchmark": (
                        "water+1-butanol phase split and water+ethanol "
                        "homogeneous at 298.15 K — documented LLE systems, "
                        "asserted qualitatively; gap bounds are an "
                        "implementation regression lock, not an experimental fit"
                    ),
                    "limitations": [
                        "equilibrium proxy only — does not establish storage, "
                        "emulsion or kinetic stability or any product "
                        "performance claim",
                        "group-contribution accuracy; no polymers, salts, "
                        "electrolytes, or near-critical systems",
                        "missing interaction-parameter coverage blocks the job",
                    ],
                }
            },
        }

    def compute(self, spec: MaterialsJobSpec, *, payload: dict[str, Any]) -> MaterialsOutcome:
        thermo_v = _dist_version("thermo")
        if thermo_v is None:
            raise EngineFailure("ENGINE_UNAVAILABLE", "thermo is not installed in this image")
        if thermo_v != THERMO_VERSION:
            raise EngineFailure(
                "ENGINE_UNAVAILABLE",
                f"thermo {thermo_v} differs from tested {THERMO_VERSION}",
            )

        # Rebuild the payload from the persisted spec and compare against
        # the bytes that were persisted/mounted — any drift means the
        # input artifact was not produced by this contract.
        expected = build_job_payload(spec)
        if _normalize(payload) != _normalize(expected):
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "persisted job payload does not match the job spec digest",
            )

        from thermo.unifac import LLEUFIP, LLEUFSG, UNIFAC

        # Coverage against the *live* parameter tables — the embedded
        # host-side tables are the same published data, but the container
        # is authoritative. An unknown subgroup or a missing interaction
        # pair is missing information, not a zero (§16.3).
        for comp in spec.components:
            for key in comp.unifac_groups:
                if int(key) not in LLEUFSG:
                    raise EngineFailure(
                        "ENGINE_UNSUPPORTED_INPUT",
                        f"subgroup id {key} is not in the shipped LLEUFSG table",
                    )
        mains_by_component = [component_main_groups(c.unifac_groups) for c in spec.components]
        mains = mains_by_component[0] | mains_by_component[1]
        missing = [
            f"{a}->{b}"
            for a in sorted(mains)
            for b in sorted(mains)
            if a != b and b not in LLEUFIP.get(a, {})
        ]
        if missing:
            raise EngineFailure(
                "MISSING_PARAMETERS",
                f"shipped LLEUFIP lacks interaction pair(s) {missing[:8]} — "
                "no substitute is assumed",
            )

        n = spec.grid_points
        xs = [_EDGE_EPS + (1 - 2 * _EDGE_EPS) * i / (n - 1) for i in range(n)]
        groups = [{int(k): v for k, v in c.unifac_groups.items()} for c in spec.components]
        gammas: list[tuple[float, float]] = []
        try:
            for x in xs:
                ge = UNIFAC.from_subgroups(
                    T=spec.conditions.temperature_k,
                    xs=[x, 1 - x],
                    chemgroups=groups,
                    subgroups=LLEUFSG,
                    interaction_data=LLEUFIP,
                    version=0,
                )
                g1, g2 = ge.gammas()
                gammas.append((float(g1), float(g2)))
        except EngineFailure:
            raise
        except Exception as e:
            raise EngineFailure(
                "ENGINE_FAILURE", f"thermo UNIFAC evaluation failed: {type(e).__name__}"
            ) from e

        surface = gibbs_mixing_surface(xs, gammas)
        if not all(map(lambda v: math.isfinite(v), surface)):
            raise EngineFailure(
                "ENGINE_MALFORMED_OUTPUT", "mixing surface contains non-finite values"
            )
        gaps = miscibility_gaps(xs, surface)
        phase_state = "phase_separated" if gaps else "homogeneous"

        nominal = spec.conditions.nominal_x1
        nominal_report: dict[str, Any] | None = None
        if nominal is not None:
            in_gap = any(lo <= nominal <= hi for lo, hi in gaps)
            nominal_report = {
                "x1": nominal,
                "inside_miscibility_gap": in_gap,
                "interpretation": "split predicted" if in_gap else "single liquid phase predicted",
            }

        proxy = {
            "endpoint_class": "equilibrium_phase_behavior",
            "basis": "mole_fraction_component_0",
            "phase_state": phase_state,
            "miscibility_gaps": [{"x_lo": lo, "x_hi": hi} for lo, hi in gaps],
            "nominal_composition": nominal_report,
            "temperature_k": spec.conditions.temperature_k,
            "components": [c.name for c in spec.components],
            "component_main_groups": [sorted(m) for m in mains_by_component],
        }
        model_context = {
            "model": "UNIFAC-LLE activity coefficients",
            "parameter_table": "LLEUFIP (Magnussen/Rasmussen/Fredenslund 1981 LLE regression)",
            "subgroup_table": "LLEUFSG",
            "thermo_version": thermo_v,
            "assumptions": [
                "isothermal-isobaric liquid mixture; vapor phase ignored",
                "temperature-independent a_mn interaction coefficients",
                "group additivity — components are exact subgroup decompositions",
                "equilibrium criterion only: phase split iff g_mix rises "
                "above its lower convex hull",
            ],
            "boundary_conditions": "closed binary at fixed overall composition; "
            "two coexisting liquid phases at most",
            "ensemble": "isothermal_isobaric_two_liquid",
            "sampling": {
                "kind": "uniform composition grid + lower convex hull",
                "grid_points": n,
                "grid_range": [xs[0], xs[-1]],
                "gap_bounds_resolution": (xs[-1] - xs[0]) / (n - 1),
            },
            "convergence": "deterministic — grid-resolution-limited, not an iterative solver",
            "calibration": "none — published parameter table as shipped; not fitted to task data",
        }
        return MaterialsOutcome(
            status="succeeded",
            usable=True,
            classification="reference_integration",
            phase_state=phase_state,
            equilibrium_proxy=proxy,
            supports_endpoints=SUPPORTS_ENDPOINTS,
            does_not_establish=DOES_NOT_ESTABLISH,
            model_context=model_context,
            engine_version=thermo_v,
            input_digest=spec.digest(),
            error=None,
            isolation={"note": _RAW_NOTE},
        )


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Structural equality for drift-checking: the persisted JSON object
    and the rebuilt payload must agree field-for-field."""
    return {
        "schema_name": payload.get("schema_name"),
        "schema_version": payload.get("schema_version"),
        "method": payload.get("method"),
        "method_version": payload.get("method_version"),
        "components": [
            {
                "name": c.get("name"),
                "unifac_groups": {
                    str(k): int(v) for k, v in (c.get("unifac_groups") or {}).items()
                },
            }
            for c in payload.get("components") or []
        ],
        "conditions": dict(payload.get("conditions") or {}),
        "grid_points": payload.get("grid_points"),
        "adapter_version": payload.get("adapter_version"),
    }
