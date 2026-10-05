"""Network-denied Chemprop container entrypoint (CS-0604).

Reads a bounded JSON request, runs the pinned adapter, prints exactly
one JSON result line. Model artifacts are files in the run scratch —
never pickled blobs crossing the request boundary:

- ``train``:   request {operation, spec}; writes model_NN.pt +
  manifest.json into scratch; prints ``TrainResult``.
- ``predict``: request {operation, spec}; reads the model files the
  runtime placed in scratch; prints ``PredictResult``.

Failures are ``{"error": code, "message": msg}`` on exit 2 — engine
tracebacks and input SMILES never leave the container.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from engine_adapter_chemprop import ChempropAdapter, EngineFailure, PredictSpec, TrainSpec


def run(request: dict[str, Any]) -> dict[str, Any]:
    adapter = ChempropAdapter()
    operation = request.get("operation")
    if operation == "train":
        spec = TrainSpec.model_validate(request["spec"])
        result, files = adapter.train(spec)
        for name, content in files.items():
            with open(name, "wb") as f:
                f.write(content)
        return result.model_dump(mode="json")
    if operation == "predict":
        pred_spec = PredictSpec.model_validate(request["spec"])
        model_files: dict[str, bytes] = {}
        for name in sorted(os.listdir(".")):
            if name == "request.json" or not os.path.isfile(name):
                continue
            with open(name, "rb") as f:
                model_files[name] = f.read()
        return adapter.predict(pred_spec, model_files).model_dump(mode="json")
    raise EngineFailure("ENGINE_UNSUPPORTED_INPUT", "unknown operation")


if __name__ == "__main__":
    try:
        with open("request.json", "rb") as f:
            raw = f.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("request too large")
        print(json.dumps(run(json.loads(raw))))
    except EngineFailure as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}))
        sys.exit(2)
    except Exception:
        print(
            json.dumps(
                {
                    "error": "ENGINE_UNSUPPORTED_INPUT",
                    "message": "Chemprop could not process the declared request",
                }
            )
        )
        sys.exit(2)
