"""CS-0603 fixture-only software tests; no scientific performance claim."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from engine_adapter_baybe import CampaignSpec
from engine_adapter_baybe.contracts import Recommendation
from engine_adapter_baybe.validation import point, same_point, validate_batch
from pydantic import ValidationError
from workers.optimization.campaign import Campaign, ReplayState


def spec_raw() -> dict[str, Any]:
    return json.loads(Path("fixtures/synthetic/optimization-campaign.json").read_text())["spec"]


class FixtureAdapter:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self.requests: list[dict[str, Any]] = []

    def recommend(self, spec: CampaignSpec, **kwargs: Any) -> Recommendation:
        self.requests.append(kwargs)
        return Recommendation(
            status="suggested",
            suggestions=self.rows,
            rejected={},
            seed=spec.seed,
            recommender="fixture-only",
        )


@pytest.mark.parametrize(
    "unsupported",
    [
        "hybrid",
        "cardinality",
        "interpoint",
        "batch",
        "extra_constraint",
        "extra_target",
        "active_solids",
    ],
)
def test_at0603_2_fail_closed(unsupported: str) -> None:
    raw = spec_raw()
    if unsupported == "hybrid":
        raw["parameters"][0] = {
            "name": "a",
            "kind": "continuous",
            "unit": "percent_m/m",
            "bounds": [0, 100],
        }
    elif unsupported == "extra_target":
        raw["target"]["weight"] = 1
    elif unsupported == "active_solids":
        raw["mixture"]["basis"] = "active_solids"
    else:
        raw["constraints"][0][
            "kind"
            if unsupported == "cardinality"
            else "scope"
            if unsupported in {"interpoint", "batch"}
            else "ignored"
        ] = unsupported
    with pytest.raises(ValidationError):
        CampaignSpec.model_validate(raw)


@pytest.mark.parametrize(
    "bad",
    [
        {"a": "50", "b": "25"},
        {"a": "100", "b": "0"},
        {"a": "NaN", "b": "100"},
        {"a": "-1", "b": "101"},
        {"a": "49", "b": "51"},
        {"a": "0"},
        {"a": "0", "b": "100", "hidden": "7"},
        {"a": True, "b": "100"},
    ],
)
def test_independent_domain_validation(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        point(CampaignSpec.model_validate(spec_raw()), bad)


def test_at0603_1_synthetic_mixture_and_dedupe() -> None:
    spec = CampaignSpec.model_validate(spec_raw())
    accepted, rejected = validate_batch(
        spec,
        [
            {"a": "0", "b": "100"},
            {"a": "25.0", "b": "75.0"},
            {"a": "25", "b": "75"},
            {"a": "50", "b": "25"},
        ],
        [{"a": "0", "b": "100"}],
    )
    assert accepted == [{"a": "25.0", "b": "75.0"}]
    assert rejected == {"invalid": 1, "duplicate": 2}


def test_at0603_3_pending_cancelled_failed_not_zero() -> None:
    spec = CampaignSpec.model_validate(spec_raw())
    campaign = Campaign(spec)
    adapter = FixtureAdapter([{"a": "0", "b": "100"}, {"a": "25", "b": "75"}])
    campaign.recommend(adapter, 2)
    first, second = campaign.state.experiments
    campaign.transition(first.id, "cancelled", reason="fixture cancellation")
    campaign.transition(second.id, "failed", reason="fixture instrument failure")
    replacement = FixtureAdapter([{"a": "50", "b": "50"}])
    campaign.recommend(replacement, 1)
    assert replacement.requests[0]["observations"] == []
    assert replacement.requests[0]["pending"] == []
    assert len(replacement.requests[0]["reserved"]) == 2
    pending = FixtureAdapter([{"a": "75", "b": "25"}])
    campaign.recommend(pending, 1)
    assert pending.requests[0]["pending"] == [{"a": "50", "b": "50"}]
    assert all(e.outcome is None for e in campaign.state.experiments)
    with pytest.raises(ValueError, match="independent"):
        campaign.recommend(FixtureAdapter([first.parameters]), 1)


def test_observation_requires_provenance_and_real_zero_is_valid() -> None:
    campaign = Campaign(CampaignSpec.model_validate(spec_raw()))
    campaign.recommend(FixtureAdapter([{"a": "0", "b": "100"}]), 1)
    eid = campaign.state.experiments[0].id
    with pytest.raises(ValueError, match="provenance"):
        campaign.transition(eid, "observed", outcome="0")
    campaign.transition(
        eid,
        "observed",
        outcome="0",
        measurement_id="reviewed",
        snapshot_id="frozen",
        source_hash="hash",
    )
    restored = Campaign(
        campaign.spec, ReplayState.model_validate_json(campaign.state.model_dump_json())
    )
    assert restored.state == campaign.state
    assert restored.state.experiments[0].outcome == "0"
    adapter = FixtureAdapter([{"a": "25", "b": "75"}])
    restored.recommend(adapter, 1)
    assert adapter.requests[0]["observations"] == [
        {"a": "0", "b": "100", campaign.spec.target.name: "0"}
    ]
    with pytest.raises(ValueError, match="immutable"):
        restored.transition(eid, "cancelled", reason="cannot erase observation")


def test_safe_replay_version_digest_and_boundaries() -> None:
    campaign = Campaign(CampaignSpec.model_validate(spec_raw()))
    raw = campaign.state.model_dump(mode="json")
    raw["engine_version"] = "future"
    with pytest.raises(ValidationError):
        ReplayState.model_validate(raw)
    raw = campaign.state.model_dump(mode="json")
    raw["spec_digest"] = "changed"
    with pytest.raises(ValueError, match="definition changed"):
        Campaign(campaign.spec, ReplayState.model_validate(raw))
    for size in [0, 17, True]:
        with pytest.raises(ValueError, match="bounded"):
            campaign.recommend(FixtureAdapter([]), size)


def test_continuous_identity_uses_distance_not_rounding_bucket() -> None:
    raw = spec_raw()
    raw["parameters"] = [
        {"name": p["name"], "kind": "continuous", "unit": p["unit"], "bounds": [0, 100]}
        for p in raw["parameters"]
    ]
    spec = CampaignSpec.model_validate(raw)
    assert same_point(
        spec, {"a": "50.0000004", "b": "49.9999996"}, {"a": "50.0000006", "b": "49.9999994"}
    )
    assert not same_point(spec, {"a": "50.01", "b": "49.99"}, {"a": "50", "b": "50"})
    assert Decimal(point(spec, {"a": "50", "b": "50"})["a"]) == 50
