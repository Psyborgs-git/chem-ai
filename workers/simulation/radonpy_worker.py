"""Real RadonPy/GAFF2/LAMMPS MD in an isolated native CPU process.

No API/session credentials or arbitrary commands are consumed. Shortened EQ21
runs are explicitly computational pilots and cannot become training labels.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import os
import random
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, cast


def _mpi_environment() -> dict[str, str]:
    env = dict(os.environ)
    # Bound CPU discovery to the two cores allocated to this serial-MPI worker.
    # MPICH's hwloc macOS backend can otherwise loop during topology discovery.
    env.update(
        {
            "HWLOC_COMPONENTS": "synthetic,stop",
            "HWLOC_SYNTHETIC": "package:1 core:2 pu:1",
            "OMP_NUM_THREADS": "2",
            "OMP_PROC_BIND": "false",
            "MPLBACKEND": "Agg",
        }
    )
    return env


def solver_binary() -> Path:
    configured = os.environ.get("STUDIO_LAMMPS_EXEC")
    if configured:
        return Path(configured).expanduser().resolve()
    import lammps  # type: ignore[import-not-found]

    return Path(lammps.__file__).resolve().parent / ("lmp.exe" if os.name == "nt" else "lmp")


def capability() -> dict[str, Any]:
    try:
        versions = {
            name: importlib.metadata.version(name)
            for name in ("radonpy-pypi", "lammps", "rdkit", "mpich")
        }
        from radonpy.ff.gaff2 import GAFF2  # type: ignore[import-not-found]

        del GAFF2
        probe = subprocess.run(  # noqa: S603 — configured native binary
            [str(solver_binary()), "-h"],
            env=_mpi_environment(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        available = probe.returncode == 0 and "Large-scale Atomic/Molecular" in probe.stdout
        return {
            "available": available,
            "backend": "radonpy_lammps",
            "execution": "native_cpu",
            "versions": versions,
            "openmp": "OPENMP" in probe.stdout,
            "reason": None if available else "Native LAMMPS capability probe failed",
        }
    except Exception as exc:
        return {
            "available": False,
            "backend": "radonpy_lammps",
            "execution": "native_cpu",
            "reason": f"Simulation runtime unavailable ({type(exc).__name__})",
        }


def _write(path: Path, value: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


def _retain_engine_output(
    directory: Path,
    input_file: str,
    *,
    returncode: int | None,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
    timed_out: bool = False,
) -> None:
    """Keep exact per-attempt process diagnostics independently of MD logs."""
    name = f"{Path(input_file).stem}-process-{uuid.uuid4().hex}"
    files = {}
    for kind, value in (("stdout", stdout), ("stderr", stderr)):
        text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        path = directory / f"{name}.{kind}.txt"
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
        path.chmod(0o600)
        files[kind] = path.name
    metadata = directory / f"{name}.json"
    _write(
        metadata,
        {"inputFile": input_file, "returncode": returncode, "timedOut": timed_out, **files},
    )
    metadata.chmod(0o600)


def _check_engine_result(
    directory: Path, input_file: str, completed: subprocess.CompletedProcess[str]
) -> subprocess.CompletedProcess[str]:
    _retain_engine_output(
        directory,
        input_file,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if completed.returncode:
        raise RuntimeError(
            f"LAMMPS exited with code {completed.returncode}; retained engine logs contain details"
        )
    return completed


def event(directory: Path, phase: str, **values: Any) -> None:
    value = {"phase": phase, "at": time.time(), **values}
    with (directory / "events.jsonl").open("a") as handle:
        handle.write(json.dumps(value, allow_nan=False) + "\n")
    print(json.dumps(value), flush=True)


def _json_safe(value: Any) -> Any:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _read_thermo(path: Path) -> list[dict[str, float]]:
    rows, columns = [], []
    for line in path.read_text(errors="replace").splitlines():
        values = line.split()
        if values and values[0] == "Step" and "Temp" in values:
            columns = values
            continue
        if columns and len(values) == len(columns):
            try:
                row = {key: float(value) for key, value in zip(columns, values, strict=True)}
                rows.append(row)
            except ValueError:
                pass
    return rows


def _seed_run(
    directory: Path, config: dict[str, Any], seed: int, deadline: float, root: Path
) -> dict[str, Any]:
    import numpy as np
    from radonpy.core import poly, utils  # type: ignore[import-not-found]
    from radonpy.ff.gaff2 import GAFF2
    from radonpy.sim import lammps as radon_lammps  # type: ignore[import-not-found]
    from radonpy.sim.preset import eq  # type: ignore[import-not-found]
    from rdkit import Chem
    from rdkit.Chem import AllChem

    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    random.seed(seed)
    np.random.seed(seed)
    checkpoint_file = directory / "stage-checkpoint.json"
    checkpoint = (
        json.loads(checkpoint_file.read_text()) if checkpoint_file.exists() else {"stage": 0}
    )
    stage = int(checkpoint["stage"])
    if stage == 3 and (directory / "seed-result.json").is_file():
        return cast(dict[str, Any], json.loads((directory / "seed-result.json").read_text()))
    if stage > 0:
        cell = utils.JSONToMol(str(directory / f"stage-{stage}.json"))
        event(
            root, "resuming_seed", seed=seed, stage=stage, resumeMode="completed_stage_checkpoint"
        )
    else:
        event(root, "building_cell", seed=seed)
        monomer = utils.mol_from_smiles(config["repeatSmiles"], coord=False)
        terminal = utils.mol_from_smiles(
            config.get("headCapSmiles", config.get("endCapSmiles", "*C")), coord=False
        )
        tail_terminal = utils.mol_from_smiles(
            config.get("tailCapSmiles", config.get("endCapSmiles", "*OC")), coord=False
        )
        geometry: Any = AllChem
        for molecule in (monomer, terminal, tail_terminal):
            parameters = geometry.ETKDGv3()
            parameters.randomSeed = seed
            if geometry.EmbedMolecule(molecule, parameters) != 0:
                raise ValueError("RDKit could not embed the repeat unit or end cap")
        chain = poly.polymerize_rw(monomer, config["repeats"], retry=3, retry_step=30, opt="rdkit")
        chain = poly.terminate_rw(chain, terminal, tail_terminal, retry_step=30, opt="rdkit")
        atoms = chain.GetNumAtoms() * config["chains"]
        if atoms > config["maxAtoms"]:
            raise ValueError(
                f"Hydrogen-complete cell requires {atoms} atoms, "
                f"above its {config['maxAtoms']} atom limit"
            )
        ff = GAFF2()
        if not ff.ff_assign(chain, charge="gasteiger"):
            raise ValueError(
                "GAFF2 force-field assignment did not cover the complete capped polymer"
            )
        charges = [atom.GetDoubleProp("AtomicCharge") for atom in chain.GetAtoms()]
        if (
            not all(math.isfinite(value) for value in charges)
            or abs(sum(charges) - Chem.GetFormalCharge(chain)) > 1e-3
        ):
            raise ValueError(
                "Gasteiger charges are missing, nonfinite "
                "or do not sum to the chain's formal charge"
            )
        if not all(atom.HasProp("ff_type") for atom in chain.GetAtoms()):
            raise ValueError("The polymer has unassigned GAFF2 atom types")
        cell = poly.amorphous_cell(chain, config["chains"], density=0.03, retry=3, retry_step=30)
        if not isinstance(cell, Chem.Mol):
            raise ValueError("Amorphous polymer cell packing failed")
        utils.MolToJSON(cell, str(directory / "initial-cell.json"))
        _write(
            directory / "forcefield-report.json",
            {
                "assigned": True,
                "forceField": "GAFF2",
                "chargeMethod": "Gasteiger",
                "chainAtoms": chain.GetNumAtoms(),
                "atoms": cell.GetNumAtoms(),
                "chargeSumPerChain": sum(charges),
                "allAtomTypesAssigned": True,
                "zeroChargeFallback": False,
                "cappedChainSmiles": Chem.MolToSmiles(Chem.RemoveHs(chain)),
            },
        )

    preset = eq.EQ21step(
        cell, work_dir=str(directory), save_dir=str(directory), solver_path=str(solver_binary())
    )
    engine = radon_lammps.LAMMPS(
        work_dir=str(directory), solver_path=str(solver_binary()), check_lammps_package=False
    )

    # Replace only this isolated instance's upstream shell launcher with argv execution.
    def execute(
        input_file: str | None = None, output_file: str | None = None, **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        args = [
            str(solver_binary()),
            "-sf",
            "omp",
            "-pk",
            "omp",
            "2",
            "-in",
            input_file or engine.input_file,
            "-screen",
            output_file or engine.output_file,
        ]
        remaining = deadline - time.monotonic()
        if remaining < 1:
            raise TimeoutError("Simulation wall-clock budget exhausted")
        try:
            completed = subprocess.run(  # noqa: S603 — fixed native engine and generated input
                args,
                cwd=directory,
                env=_mpi_environment(),
                capture_output=True,
                text=True,
                timeout=remaining,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            _retain_engine_output(
                directory,
                input_file or engine.input_file,
                returncode=None,
                stdout=exc.stdout,
                stderr=exc.stderr,
                timed_out=True,
            )
            raise
        return _check_engine_result(directory, input_file or engine.input_file, completed)

    engine.exec = execute
    for index in range(stage + 1, 4):
        event(root, "running_stage", seed=seed, stage=index)
        preset.mol = cell
        if index == 1:
            utils.MolToPDBFile(cell, str(directory / preset.pdb_file))
            md = preset.packing(f_density=0.8, max_temp=config["maxTemperatureK"])
            for workflow in md.wf:
                if hasattr(workflow, "step"):
                    workflow.step = max(20, int(workflow.step * config["protocolScale"]))
            input_file, last_data, last_str = preset.in_file1, preset.last_data1, preset.last_str1
        elif index == 2:
            # The exact seven triplets from the RadonPy EQ21 preset, uniformly scaled.
            original = [
                [50000, 50000, 50000],
                [50000, 100000, 50000],
                [50000, 100000, 50000],
                [50000, 100000, 5000],
                [5000, 10000, 5000],
                [5000, 10000, 5000],
                [5000, 10000, 800000],
            ]
            steps = [[max(20, int(n * config["protocolScale"])) for n in row] for row in original]
            md = preset.eq21step(
                temp=300,
                max_temp=600,
                press=1,
                max_press=50000,
                step_list=steps,
                set_init_velocity=True,
            )
            input_file, last_data, last_str = preset.in_file2, preset.last_data2, preset.last_str2
        else:
            md = preset.sampling(temp=300, press=1, step=config["samplingSteps"])
            input_file, last_data, last_str = preset.in_file, preset.last_data, preset.last_str
        md.thermo_freq, md.dump_freq, md.rst_freq = (
            (1000 if config["protocolScale"] == 1 else 100),
            1000,
            1000,
        )
        md.rst1_file, md.rst2_file = f"stage-{index}-1.rst", f"stage-{index}-2.rst"
        # Always regenerate this stage's initial data from its verified molecule checkpoint.
        engine.make_dat(cell, file_name=md.dat_file)
        before = directory / last_str
        if before.exists():
            # Keep previous partial attempt, avoiding upstream acceptance of stale output.
            before.rename(before.with_name(before.name + f".attempt-{int(time.time())}"))
        cell = engine.run(
            md,
            mol=cell,
            input_file=input_file,
            last_data=last_data,
            last_str=last_str,
            mpi=0,
            omp=2,
            gpu=0,
            intel="off",
            opt="off",
        )
        if not isinstance(cell, Chem.Mol):
            raise RuntimeError("LAMMPS did not return a complete molecular state")
        utils.MolToJSON(cell, str(directory / f"stage-{index}.json"))
        _write(
            checkpoint_file,
            {"stage": index, "seed": seed, "resumeMode": "completed_stage_checkpoint"},
        )
        event(root, "stage_completed", seed=seed, stage=index)
    rows = _read_thermo(directory / preset.log_file)
    stable = (
        bool(rows)
        and all(math.isfinite(v) for row in rows for v in row.values())
        and not any("ERROR" in path.read_text(errors="replace") for path in directory.glob("*.log"))
    )
    tail = rows[len(rows) // 2 :]
    diagnostic = {
        key: float(np.mean([row[key] for row in tail]))
        for key in ("Temp", "Press", "Density", "TotEng")
        if tail and all(key in row for row in tail)
    }
    checks: dict[str, Any] = {"radonpyConvergencePassed": False, "analysisError": None}
    try:
        analysis = preset.analyze()
        # Upstream's log parser discards an entire thermo block if LAMMPS prints
        # a WARNING inside it. Supply the same numeric rows, retaining raw logs.
        import pandas as pd

        analysis.dfs = [pd.DataFrame(rows).set_index("Step")]
        width = (
            2000
            if config["protocolScale"] == 1
            else max(2, min(20, config["samplingSteps"] // 5000))
        )
        initial = 2000 if config["protocolScale"] == 1 else width * 2
        properties = analysis.get_all_prop(
            temp=300, press=1, width=width, init=initial, f_width=width, do_traj=False, save=True
        )
        checks["radonpyConvergencePassed"] = bool(
            analysis.check_eq(width=width, init=initial, f_width=width)
        )
        checks["analysisWindowSamples"] = width
        checks["discardedSamples"] = initial
        _write(directory / "radonpy-properties.json", _json_safe(properties))
        _write(directory / "radonpy-convergence.json", _json_safe(analysis.conv_df.to_dict()))
    except Exception as exc:
        checks["analysisError"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    # An abbreviated pilot cannot satisfy the full preset's 5 ns sampling qualification.
    equilibrated = bool(
        stable
        and checks["radonpyConvergencePassed"]
        and config["protocolScale"] == 1
        and config["samplingSteps"] >= 5_000_000
    )
    result = {
        "seed": seed,
        "atoms": cell.GetNumAtoms(),
        "numericallyStable": stable,
        "equilibrated": equilibrated,
        "trainingEligible": equilibrated,
        "diagnostics": diagnostic,
        "convergence": checks,
        "trajectoryState": "amorphous_atomistic",
        "resumeMode": "completed_stage_checkpoint",
    }
    _write(directory / "seed-result.json", result)
    return result


def run(directory: Path) -> dict[str, Any]:
    request = json.loads((directory / "request.json").read_text())
    config = request["config"]
    status = capability()
    if not status["available"]:
        raise RuntimeError(status["reason"])
    started = time.monotonic()
    deadline = started + float(request.get("remainingSeconds", config["maxWallSeconds"]))
    results = []
    for seed in config["seeds"]:
        result = _seed_run(directory / f"seed-{seed}", config, seed, deadline, directory)
        results.append(result)
        _write(directory / "partial-result.json", {"seeds": results, "trainingEligible": False})
    eligible = all(row["trainingEligible"] for row in results)
    result = {
        "ok": True,
        "backend": "radonpy_lammps",
        "versions": status["versions"],
        "seeds": results,
        "protocol": config["protocol"],
        "protocolScale": config["protocolScale"],
        "temperatureK": 300,
        "pressureAtm": 1,
        "forceField": "GAFF2",
        "chargeMethod": "Gasteiger",
        "inputDigest": config["inputDigest"],
        "numericallyStable": all(row["numericallyStable"] for row in results),
        "equilibrated": eligible,
        "trainingEligible": eligible,
        "scientificStatus": "computed_not_experimental"
        if eligible
        else "unconverged_pilot_not_training_labels",
        "elapsedSeconds": time.monotonic() - started,
        "limitations": [
            "Amorphous short polymer cells do not predict yarn/fabric hand, "
            "drape or silk equivalence",
            "Gasteiger charges are a pilot approximation, not RESP charges",
            "No tensile, crystallinity, processing or experimental "
            "textile validation is established",
        ],
    }
    _write(directory / "result.json", result)
    event(
        directory, "completed", numericallyStable=result["numericallyStable"], equilibrated=eligible
    )
    return result


def main() -> None:
    directory = Path(sys.argv[1]).resolve()
    # A backend crash cannot leave an unbounded orphan simulation. Direct CLI
    # smoke runs have no lease file; API-dispatched jobs renew it every second.
    lease = directory / "lease.json"
    if lease.exists():

        def watch() -> None:
            while True:
                try:
                    if time.time() > float(json.loads(lease.read_text())["expiresAt"]):
                        os.killpg(os.getpgrp(), signal.SIGTERM)
                        return
                except (OSError, ValueError, KeyError):
                    pass
                time.sleep(1)

        threading.Thread(target=watch, daemon=True).start()
    try:
        import fcntl

        lock = (directory / "worker.lock").open("w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        request = json.loads((directory / "request.json").read_text())

        def expired(_signum: int, _frame: Any) -> None:
            raise TimeoutError("Simulation wall-clock budget exhausted")

        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(
            signal.ITIMER_REAL,
            float(request.get("remainingSeconds", request["config"]["maxWallSeconds"])),
        )
        run(directory)
    except Exception as exc:
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            "trainingEligible": False,
        }
        _write(directory / "result.json", result)
        event(directory, "failed", error=result["error"])
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
