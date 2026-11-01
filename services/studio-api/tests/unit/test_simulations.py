from __future__ import annotations

import json
from pathlib import Path

import pytest
from workers.simulation.radonpy_worker import _read_thermo

from studio.domain.simulations.service import PET_REPEAT, validate_payload
from studio.errors import DomainError


def test_repeat_orientation_and_distinct_polyester_endcaps_are_preserved():
    config = validate_payload({"repeatSmiles": PET_REPEAT})
    assert config["repeatSmiles"] == PET_REPEAT
    assert config["headCapSmiles"] == "*C"
    assert config["tailCapSmiles"] == "*OC"
    assert config["forceField"] == "GAFF2"
    assert config["chargeMethod"] == "Gasteiger"
    assert config["seeds"] == [1729, 1733]


@pytest.mark.parametrize(
    "payload",
    [
        {"repeatSmiles": "CCO"},
        {"repeatSmiles": "*CC.*OC"},
        {"repeatSmiles": "*C(*)C*"},
        {"repeatSmiles": "*[Na]*"},
        {"repeatSmiles": "*C[NH2+]C*"},
        {"repeatSmiles": PET_REPEAT, "seeds": [1, 1]},
        {"repeatSmiles": PET_REPEAT, "seeds": [True, 2]},
        {"repeatSmiles": PET_REPEAT, "maxAtoms": 2001},
        {"repeatSmiles": PET_REPEAT, "repeats": 64, "chains": 32},
        {"repeatSmiles": PET_REPEAT, "temperatureK": 600},
        {"repeatSmiles": PET_REPEAT, "maxWallSeconds": 14401},
        {"repeatSmiles": PET_REPEAT, "protocolScale": float("nan")},
        {"repeatSmiles": PET_REPEAT, "tailCapSmiles": "CC"},
    ],
)
def test_invalid_or_unbounded_polymer_requests_fail_before_execution(payload):
    with pytest.raises(DomainError):
        validate_payload(payload)


def test_thermo_diagnostics_keep_actual_rows_across_lammps_warnings(tmp_path: Path):
    log = tmp_path / "eq3.log"
    log.write_text(
        "Step Time Temp Press Density TotEng\n0 0 300 1 .9 15\n"
        "WARNING: Neighbor rebuild\n100 100 301 2 .91 14\nLoop time of 1\n"
    )
    assert _read_thermo(log) == [
        {"Step": 0.0, "Time": 0.0, "Temp": 300.0, "Press": 1.0, "Density": 0.9, "TotEng": 15.0},
        {
            "Step": 100.0,
            "Time": 100.0,
            "Temp": 301.0,
            "Press": 2.0,
            "Density": 0.91,
            "TotEng": 14.0,
        },
    ]


def test_worker_failure_records_failure_without_fake_trajectory_or_labels(tmp_path: Path):
    import os
    import subprocess
    import sys

    (tmp_path / "request.json").write_text(json.dumps({"config": {"maxWallSeconds": 30}}))
    env = {**os.environ, "STUDIO_LAMMPS_EXEC": str(tmp_path / "does-not-exist")}
    result = subprocess.run(  # noqa: S603 — fixed worker
        [sys.executable, "-m", "workers.simulation.radonpy_worker", str(tmp_path)],
        capture_output=True,
        timeout=20,
        check=False,
        env=env,
    )
    assert result.returncode != 0
    recorded = json.loads((tmp_path / "result.json").read_text())
    assert recorded["ok"] is False
    assert recorded["trainingEligible"] is False
    assert not list(tmp_path.glob("*.xtc"))


def test_native_engine_failure_retains_unique_stage_streams_before_raising(tmp_path: Path):
    import subprocess

    from workers.simulation.radonpy_worker import _check_engine_result

    failed = subprocess.CompletedProcess(
        ["lmp", "-in", "eq3.in"], 15, "native stdout\n", "MPI shutdown detail\n"
    )
    for _ in range(2):
        with pytest.raises(RuntimeError, match="code 15"):
            _check_engine_result(tmp_path, "eq3.in", failed)
    metadata = list(tmp_path.glob("eq3-process-*.json"))
    assert len(metadata) == 2
    for path in metadata:
        record = json.loads(path.read_text())
        assert record["returncode"] == 15 and record["timedOut"] is False
        assert (tmp_path / record["stdout"]).read_text() == "native stdout\n"
        assert (tmp_path / record["stderr"]).read_text() == "MPI shutdown detail\n"
    assert not (tmp_path / "stage-checkpoint.json").exists()
    assert not (tmp_path / "result.json").exists()
    succeeded = subprocess.CompletedProcess(["lmp", "-in", "eq3.in"], 0, "done\n", "")
    assert _check_engine_result(tmp_path, "eq3.in", succeeded) is succeeded
    assert len(list(tmp_path.glob("eq3-process-*.json"))) == 3


def test_successful_resume_clears_old_result_error_but_preserves_failure_history():
    from studio.domain.simulations.dispatcher import _final_result

    previous = {
        "ok": False,
        "error": "Native finalization exit 15",
        "elapsedSeconds": 831.765,
        "failureHistory": [{"attempt": 1, "exitCode": 15, "archive": "attempt-history/original"}],
    }
    new = {"ok": True, "numericallyStable": True, "equilibrated": False, "trainingEligible": False}
    completed = _final_result(previous, new, 1090.0, succeeded=True)
    assert completed["ok"] is True and "error" not in completed
    assert completed["failureHistory"] == previous["failureHistory"]
    assert completed["elapsedSeconds"] == 1090.0
    assert completed["trainingEligible"] is False
    assert previous["error"] == "Native finalization exit 15"
    failed = _final_result(
        previous, {"ok": False, "error": "New native failure"}, 900.0, succeeded=False
    )
    assert failed["error"] == "New native failure"
    assert failed["failureHistory"] == previous["failureHistory"]
