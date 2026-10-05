"""Real BayBE worker, synthetic fixtures only. Skip honestly if image absent."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from engine_adapter_baybe import CampaignSpec
from engine_adapter_baybe.validation import point
from workers.optimization.campaign import Campaign
from workers.optimization.runtime import IMAGE, IsolatedBayBE

pytestmark = pytest.mark.engine


@pytest.fixture()
def engine() -> IsolatedBayBE:
    docker = shutil.which("docker")
    if (
        not docker
        or subprocess.run(  # noqa: S603 — fixed image inspection
            [docker, "image", "inspect", IMAGE], capture_output=True, timeout=15
        ).returncode
    ):
        pytest.skip("UNAVAILABLE: pinned network-denied BayBE image not installed")
    return IsolatedBayBE()


@pytest.mark.parametrize("continuous", [False, True])
def test_at0603_1_live_mixture_independent_checks(engine: IsolatedBayBE, continuous: bool) -> None:
    raw = json.loads(Path("fixtures/synthetic/optimization-campaign.json").read_text())["spec"]
    if continuous:
        raw["parameters"] = [
            {"name": p["name"], "kind": "continuous", "unit": p["unit"], "bounds": [0, 100]}
            for p in raw["parameters"]
        ]
    campaign = Campaign(CampaignSpec.model_validate(raw))
    result = campaign.recommend(engine, 2)
    assert len(result.suggestions) == 2
    assert result.isolation["enforced"]["network_denied"]
    assert all(point(campaign.spec, p) for p in result.suggestions)
    replay = Campaign(campaign.spec)
    assert replay.recommend(engine, 2).suggestions == result.suggestions


def test_at0603_3_live_pending_cancelled_and_warm_gp(engine: IsolatedBayBE) -> None:
    raw = json.loads(Path("fixtures/synthetic/optimization-campaign.json").read_text())["spec"]
    campaign = Campaign(CampaignSpec.model_validate(raw))
    campaign.recommend(engine, 2)
    e1, e2 = campaign.state.experiments
    campaign.transition(
        e1.id,
        "observed",
        outcome="0",
        measurement_id="fixture-measurement-1",
        snapshot_id="fixture-snapshot",
        source_hash="fixture-hash-1",
    )
    campaign.transition(e2.id, "cancelled", reason="fixture-only cancellation")
    result = campaign.recommend(engine, 1)
    assert result.suggestions and all(
        p not in [e1.parameters, e2.parameters] for p in result.suggestions
    )
    e3 = campaign.state.experiments[-1]
    campaign.transition(
        e3.id,
        "observed",
        outcome="1",
        measurement_id="fixture-measurement-2",
        snapshot_id="fixture-snapshot",
        source_hash="fixture-hash-2",
    )
    warm = campaign.recommend(engine, 1)
    assert len(warm.suggestions) == 1
    assert warm.recommender == "BotorchRecommender"
    assert warm.acquisition == "qLogNoisyExpectedImprovement"
    final = campaign.recommend(engine, 1)
    assert final.status == "exhausted" and not final.suggestions
    assert campaign.state.experiments[1].outcome is None


@pytest.mark.parametrize("mode", ["maximize", "minimize", "match"])
def test_supported_target_and_categorical_mapping(engine: IsolatedBayBE, mode: str) -> None:
    raw = json.loads(Path("fixtures/synthetic/optimization-campaign.json").read_text())["spec"]
    raw["parameters"] = [
        {
            "name": "grade",
            "kind": "categorical",
            "unit": "identity",
            "categories": ["fixture-A", "fixture-B", "fixture-C", "fixture-D"],
        }
    ]
    raw["constraints"] = []
    raw.pop("mixture")
    raw["target"]["mode"] = mode
    if mode == "match":
        raw["target"]["match_bounds"] = [0, 2]
    campaign = Campaign(CampaignSpec.model_validate(raw))
    campaign.recommend(engine, 3)
    for i, e in enumerate(campaign.state.experiments[:2]):
        campaign.transition(
            e.id,
            "observed",
            outcome=str(i),
            measurement_id=f"fixture-{i}",
            snapshot_id="fixture",
            source_hash=f"fixture-{i}",
        )
    pending = campaign.state.experiments[-1]
    result = campaign.recommend(engine, 1)
    assert result.recommender == "BotorchRecommender"
    assert result.suggestions[0] != pending.parameters
    assert point(campaign.spec, result.suggestions[0])
