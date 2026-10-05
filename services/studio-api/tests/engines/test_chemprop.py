"""Real Chemprop worker, synthetic fixtures only. Skip honestly if
image absent — never faked."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from workers.optimization.property_models.chemprop.runtime import IMAGE, IsolatedChemprop

from engine_adapter_chemprop import PredictSpec, TrainSpec

pytestmark = pytest.mark.engine


@pytest.fixture()
def engine() -> IsolatedChemprop:
    docker = shutil.which("docker")
    if (
        not docker
        or subprocess.run(  # noqa: S603 — fixed image inspection
            [docker, "image", "inspect", IMAGE], capture_output=True, timeout=15
        ).returncode
    ):
        pytest.skip("UNAVAILABLE: pinned network-denied Chemprop image not installed")
    return IsolatedChemprop()


def _spec() -> dict:
    raw = json.loads(Path("fixtures/synthetic/property-endpoint.json").read_text())
    scope = raw["scope"]
    return {
        "schema_version": "1",
        "scope": {"name": scope["target"], "unit": scope["unit"], "method": scope["method"]},
        "representation": "mpnn-dmpnn",
        "context": {"source": "fixture_only"},
        "rows": raw["smiles_rows"],
        "seed": 11,
        "max_epochs": 2,
        "ensemble_size": 2,
        "hidden_dim": 32,
        "depth": 2,
        "batch_size": 4,
    }


def test_at0604_train_predict_lineage(engine: IsolatedChemprop) -> None:
    """Train a small ensemble on caller-supplied rows, predict on
    caller-supplied rows; lineage is content-addressed."""
    spec = TrainSpec.model_validate(_spec())
    result, files, isolation = engine.train(spec)
    assert result.status == "trained"
    assert result.pretrained is False
    assert result.model_digest and len(result.model_files) == 3  # 2 members + manifest
    assert isolation["enforced"]["network_denied"]
    # Artifact bytes move explicitly through vault-scoped scratch.
    assert all(name in files for name in result.model_files)
    assert "manifest.json" in files

    raw = json.loads(Path("fixtures/synthetic/property-endpoint.json").read_text())
    pred_spec = PredictSpec.model_validate(
        {
            "schema_version": "1",
            "scope": _spec()["scope"],
            "representation": "mpnn-dmpnn",
            "rows": raw["smiles_predict"][:2],
            "model_digest": result.model_digest,
        }
    )
    pred_result, _ = engine.predict(pred_spec, files)
    assert pred_result.status == "predicted"
    assert {p.row_id for p in pred_result.predictions} == {"mol-p1", "mol-p2"}
    for p in pred_result.predictions:
        assert len(p.members) == 2
    # Reproducibility: same artifacts, same rows, same output.
    assert engine.predict(pred_spec, files)[0] == pred_result


def test_at0604_foreign_artifact_refused(engine: IsolatedChemprop) -> None:
    """A prediction claiming lineage it cannot prove is refused."""
    _, files, _ = engine.train(TrainSpec.model_validate(_spec()))
    raw = json.loads(Path("fixtures/synthetic/property-endpoint.json").read_text())
    spec = PredictSpec.model_validate(
        {
            "schema_version": "1",
            "scope": _spec()["scope"],
            "representation": "mpnn-dmpnn",
            "rows": raw["smiles_predict"][:1],
            "model_digest": "0" * 64,  # claims lineage to nothing real
        }
    )
    from engine_adapter_chemprop import EngineFailure

    with pytest.raises(EngineFailure):
        engine.predict(spec, files)
