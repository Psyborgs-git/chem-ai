"""CS-0903 engine tests — live AiZynthFinder inside the pinned container.

AT-0903-1  a supported benign target + configured engine produces a
           route outcome with every route labeled ``proposed`` and full
           model/stock provenance.
License    an undeclared or unverifiable model/stock asset is blocked
           ``LICENSE_UNAVAILABLE`` before the engine runs (U13).

The benchmark asserts only plumbing: a completed bounded search emits a
parseable route manifest with provenance fields populated. Route
quality or executability is never claimed — solved status reflects
stock-list membership only. Every test SKIPS explicitly when the
pinned image is absent — absence is reported, never faked.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from workers.chemistry.synthesis.runtime import (
    IMAGE,
    IsolatedSynthesis,
    available,
    capability,
)

from engine_adapter_aizynthfinder.contracts import EngineFailure, RouteJobSpec
from engine_adapter_aizynthfinder.validation import build_job_payload

pytestmark = pytest.mark.engine

FIXTURE = json.loads(Path("fixtures/synthetic/synthesis-aizynthfinder.json").read_text())

_SPEC_KEYS = {
    "schema_version",
    "method",
    "target",
    "policy_model",
    "templates",
    "stock",
    "filter_model",
    "search",
    "resources",
}


@pytest.fixture()
def engine() -> IsolatedSynthesis:
    if not available():
        pytest.skip(f"pinned worker image {IMAGE} not installed")
    return IsolatedSynthesis()


def _spec(raw: dict | None = None, **over: object) -> RouteJobSpec:
    src = raw if raw is not None else FIXTURE["spec"]
    base = {k: v for k, v in json.loads(json.dumps(src)).items() if k in _SPEC_KEYS}
    for key, value in over.items():
        base[key] = value
    return RouteJobSpec.model_validate(base)


def _payload(spec: RouteJobSpec) -> dict:
    return build_job_payload(spec)


# ------------------------------------------------------------- benchmark


def test_bounded_search_emits_labeled_proposed_routes(engine: IsolatedSynthesis) -> None:
    """AT-0903-1: benign small-molecule target + licensed assets ->
    route manifest labeled proposed with model/stock provenance."""
    spec = _spec(
        search={"time_limit_seconds": 60, "iteration_limit": 1000, "max_routes": 3},
        resources={"wall_seconds": 600, "memory_mebibytes": 8192, "ncores": 2},
    )
    outcome = engine.compute(spec, payload=_payload(spec))
    assert outcome.usable and outcome.status == "succeeded"
    assert outcome.classification == "reference_integration"
    assert outcome.label == "proposed"
    assert outcome.scientific_status == "not_validated"
    assert outcome.evidence_class == "proposed_route_hypothesis"
    assert outcome.execution_gate == "independent_plan_approval_required"
    prov = outcome.provenance
    assert prov["policy_model"]["name"] == "uspto_expansion"
    assert prov["policy_model"]["license"] == "cc-by-4.0"
    assert prov["stock"]["name"] == "zinc_stock"
    assert prov["stock"]["license"] == "mit"
    assert prov["stock"]["sha256"] == spec.stock.sha256
    assert outcome.engine_version == "4.4.1"
    assert outcome.input_digest == spec.digest()
    for route in outcome.routes:
        assert route.label == "proposed"
        assert isinstance(route.is_solved, bool)
        assert route.num_reactions >= 0
    assert "yield" in outcome.does_not_establish
    assert "scale_up_feasibility" in outcome.does_not_establish
    assert outcome.isolation.get("backend") == "container"


def test_capability_probe_reports_real_method_state(engine: IsolatedSynthesis) -> None:
    probe = capability()
    assert probe is not None
    assert probe["engine_version"] == "4.4.1"
    assert probe["state"] == "available_tested"
    method = probe["methods"]["aizynthfinder-mcts-route/v1"]
    assert method["state"] == "available_tested"
    assert method["domain"]
    assert method["limitations"]
    for name in ("uspto_expansion", "uspto_templates", "zinc_stock"):
        assert method["assets"][name]["sha256_verified"] is True
    assert method["assets"]["zinc_stock"]["license"] == "mit"


# ------------------------------------------------- gates in container


def test_unverifiable_stock_blocked_in_container(engine: IsolatedSynthesis) -> None:
    """A stock asset whose declared hash does not match the reviewed
    registry fails LICENSE_UNAVAILABLE — before the engine is invoked."""
    spec = _spec(stock=FIXTURE["license_examples"]["unlicensed_stock"])
    payload = dict(_payload(_spec()))
    payload["stock"] = dict(spec.stock.model_dump(mode="json"))
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=payload)
    assert exc.value.code == "LICENSE_UNAVAILABLE"


def test_payload_drift_rejected(engine: IsolatedSynthesis) -> None:
    spec = _spec()
    payload = _payload(spec)
    payload["search"]["max_routes"] = spec.search.max_routes + 1
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=payload)
    assert exc.value.code == "ENGINE_UNSUPPORTED_INPUT"


def test_cancellation_maps_to_run_cancelled(engine: IsolatedSynthesis) -> None:
    spec = _spec()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(EngineFailure) as exc:
        engine.compute(spec, payload=_payload(spec), cancel=cancel)
    assert exc.value.code == "RUN_CANCELLED"


# NOTE (honest coverage): the bounded search finishes within its
# declared limits on small targets; a live RUN_TIMEOUT requires a run
# that outlasts the minimum resource bound — asserted impossible to
# fake, so the mapping is exercised at the service boundary in
# test_synthesis.py (integration).
