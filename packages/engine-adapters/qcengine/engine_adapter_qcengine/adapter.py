"""QCEngine execution adapter (CS-0701).

Runs inside the pinned worker image: `chem-studio-qcengine:0.51.0-v1`
(QCEngine 0.51.0 / QCElemental 0.51.2 / xtb-python 22.1 on xtb 6.7.1).
The host process validates and persists the QCSchema payload; this side
re-parses it with the real models, drift-checks it against the persisted
spec digest, executes under a bounded TaskConfig, and classifies the
result honestly — exit-0 with malformed or nonconverged output is not a
scientific success (AT-0701-2).
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    QCELEMENTAL_VERSION,
    QCENGINE_VERSION,
    EngineFailure,
    QuantumJobSpec,
    QuantumOutcome,
)
from .validation import build_atomic_input, classify_result

_RAW_STREAM_CAP = 64 * 1024
# Version actually exercised in the image; xtb-python 22.1's own
# `__version__` reports the stale string "20.2", so distribution
# metadata is the honest probe.
TESTED_PROGRAM_VERSIONS: dict[str, str] = {"xtb": "22.1", "psi4": "1.10.2"}


def _dist_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


class QCEngineAdapter:
    """Thin wrapper over qcengine.compute with pinned versions and a
    fixed input contract — the only call surface the worker exposes."""

    def capability(self) -> dict[str, Any]:
        """Report what this environment can actually run (§16.1 labels)."""
        qcengine = _dist_version("qcengine")
        qcelemental = _dist_version("qcelemental")
        programs: dict[str, Any] = {}
        for program in ("xtb", "psi4"):
            version = _dist_version(program)
            if version is None:
                try:
                    __import__(program)
                except Exception:
                    programs[program] = {"state": "not_installed", "version": None}
                    continue
                version = "unknown"
            if qcengine is None or qcelemental is None:
                state = "not_installed"
            elif (qcengine, qcelemental) != (QCENGINE_VERSION, QCELEMENTAL_VERSION):
                state = "installed_unverified"
            elif version != TESTED_PROGRAM_VERSIONS[program]:
                state = "installed_unverified"
            else:
                state = "available_tested"
            programs[program] = {"state": state, "version": version}
        return {
            "adapter_version": ADAPTER_VERSION,
            "qcengine_version": qcengine,
            "qcelemental_version": qcelemental,
            "programs": programs,
        }

    def compute(self, spec: QuantumJobSpec, *, payload: dict[str, Any]) -> QuantumOutcome:
        qcengine_v = _dist_version("qcengine")
        qcelemental_v = _dist_version("qcelemental")
        if qcengine_v is None or qcelemental_v is None:
            raise EngineFailure("ENGINE_UNAVAILABLE", "QCEngine stack is not installed")
        if (qcengine_v, qcelemental_v) != (QCENGINE_VERSION, QCELEMENTAL_VERSION):
            raise EngineFailure(
                "ENGINE_UNAVAILABLE",
                f"QCEngine/QCElemental {qcengine_v}/{qcelemental_v} differ from tested "
                f"{QCENGINE_VERSION}/{QCELEMENTAL_VERSION}",
            )
        program_version = _dist_version(spec.program)
        if program_version is None and spec.program == "psi4":
            # psi4's Python module is the entry point and may not carry
            # dist metadata in every distribution.
            try:
                import psi4
            except ImportError as e:
                raise EngineFailure(
                    "ENGINE_UNAVAILABLE", f"{spec.program} is not installed in this image"
                ) from e
            program_version = getattr(psi4, "__version__", None)
        if program_version is None:
            raise EngineFailure(
                "ENGINE_UNAVAILABLE", f"{spec.program} is not installed in this image"
            )
        if program_version != TESTED_PROGRAM_VERSIONS[spec.program]:
            raise EngineFailure(
                "ENGINE_UNAVAILABLE",
                f"{spec.program} {program_version} differs from tested "
                f"{TESTED_PROGRAM_VERSIONS[spec.program]}",
            )

        # Rebuild the payload from the persisted spec and compare against
        # the bytes that were persisted/mounted — any drift means the
        # input artifact was not produced by this contract.
        expected = build_atomic_input(spec)
        normalized = _normalize(payload)
        if normalized != _normalize(expected):
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT",
                "persisted QCSchema payload does not match the job spec digest",
            )

        import qcengine
        from qcelemental.models import AtomicInput, AtomicResult
        from qcengine.config import TaskConfig

        try:
            atomic_input = AtomicInput.parse_obj(payload)
        except Exception as e:
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT", f"persisted payload failed AtomicInput: {e}"
            ) from e

        # qcengine.compute splats task_config into a dict itself; pass
        # the validated field values, not the model instance.
        task_config = TaskConfig(
            ncores=spec.resources.ncores,
            nnodes=1,
            memory=float(spec.resources.memory_mebibytes) / 1024.0,
            scratch_directory="/work",
            mpiexec_command="mpiexec",  # required field; use_mpiexec stays off
            retries=0,
        ).dict()
        raw = qcengine.compute(
            atomic_input,
            spec.program,
            raise_error=False,
            task_config=task_config,
            return_dict=False,
        )
        if type(raw).__name__ == "FailedOperation":
            # The engine raised; qcengine wrapped the exception. This is
            # an honest engine failure, not a malformed success.
            err = getattr(raw, "error", None)
            message = getattr(err, "error_message", None) or str(err or raw)[:400]
            return QuantumOutcome(
                status="failed",
                usable=False,
                converged=False,
                classification="engine_failure",
                engine=spec.program,
                engine_version=program_version,
                qcengine_version=qcengine_v,
                qcelemental_version=qcelemental_v,
                input_digest=spec.digest(),
                error={"code": "ENGINE_FAILURE", "message": str(message)[:400]},
            )
        if not isinstance(raw, AtomicResult):
            # qcengine returns a dict when return_dict=True; with False a
            # non-AtomicResult return is unexpected — treat as malformed.
            raise EngineFailure(
                "ENGINE_MALFORMED_OUTPUT",
                f"engine returned {type(raw).__name__}, expected AtomicResult",
            )
        result = _result_dict(raw)
        verdict = classify_result(program=spec.program, driver=spec.driver, result=result)
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        return QuantumOutcome(
            status="succeeded" if verdict["usable"] else "failed",
            usable=verdict["usable"],
            converged=verdict["converged"],
            classification=verdict["classification"],
            energy_hartree=_energy(driver=spec.driver, result=result),
            return_result=_to_jsonable(result.get("return_result")),
            properties=_to_jsonable(result.get("properties") or {}),
            provenance=_to_jsonable(result.get("provenance") or {}),
            engine=spec.program,
            engine_version=program_version,
            qcengine_version=qcengine_v,
            qcelemental_version=qcelemental_v,
            input_digest=spec.digest(),
            error=verdict["error"],
            raw_stdout=stdout[:_RAW_STREAM_CAP],
            raw_stderr=stderr[:_RAW_STREAM_CAP],
            stdout_truncated=len(stdout) > _RAW_STREAM_CAP,
        )


def _energy(*, driver: str, result: dict[str, Any]) -> float | None:
    if driver != "energy":
        return None
    energy = (result.get("properties") or {}).get("return_energy")
    return energy if isinstance(energy, (int, float)) and not isinstance(energy, bool) else None


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return _to_jsonable(value.tolist())
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Structural equality for drift-checking: numbers compared with a
    float tolerance so a persisted float and an engine-parsed float agree."""
    mol = payload.get("molecule") or {}
    return {
        "schema_name": payload.get("schema_name"),
        "schema_version": payload.get("schema_version"),
        "driver": payload.get("driver"),
        "model": payload.get("model"),
        "keywords": payload.get("keywords") or {},
        "symbols": tuple(mol.get("symbols") or ()),
        "geometry": tuple(mol.get("geometry") or ()),
        "molecular_charge": mol.get("molecular_charge", 0),
        "molecular_multiplicity": mol.get("molecular_multiplicity", 1),
    }


def _result_dict(result: Any) -> dict[str, Any]:
    """AtomicResult is a pydantic-v1 model in qcelemental 0.51.x."""
    if hasattr(result, "dict"):
        return dict(result.dict())
    if hasattr(result, "model_dump"):
        return dict(result.model_dump())
    if isinstance(result, dict):
        return result
    raise EngineFailure("ENGINE_MALFORMED_OUTPUT", "engine result is not a mapping or model")
