"""Network-denied container entrypoint; bounded JSON in/out.

Reads the validated job spec and the persisted job payload from
request.json, verifies they agree inside the adapter, executes the
bounded MCTS retrosynthesis search via AiZynthFinder 4.4.1, and writes
both the consumed input (input.job.json) and the raw outcome
(result.json) into the scratch dir so the host preserves them.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from engine_adapter_aizynthfinder import AiZynthAdapter, EngineFailure, RouteJobSpec


def run(request: dict[str, Any]) -> dict[str, Any]:
    spec = RouteJobSpec.model_validate(request["spec"])
    payload = request["input"]
    with open("input.job.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    outcome = AiZynthAdapter().compute(spec, payload=payload)
    result = outcome.model_dump(mode="json")
    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    return result


def capability() -> dict[str, Any]:
    return AiZynthAdapter().capability()


if __name__ == "__main__":
    if sys.argv[1:] == ["--capability"]:
        try:
            print(json.dumps(capability()))
        except Exception:
            print(json.dumps({"error": "ENGINE_UNAVAILABLE", "message": "probe failed"}))
            sys.exit(2)
        sys.exit(0)
    try:
        with open("request.json", "rb") as f:
            raw = f.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("request too large")
        print(json.dumps(run(json.loads(raw))))
    except EngineFailure as exc:
        print(json.dumps({"error": exc.code, "message": exc.message}))
        sys.exit(2)
    except MemoryError:
        print(
            json.dumps(
                {
                    "error": "ENGINE_UNAVAILABLE",
                    "message": "synthesis run exceeded its memory envelope",
                }
            )
        )
        sys.exit(2)
    except Exception:
        # Tracebacks may contain proprietary structures; never emit them.
        print(
            json.dumps(
                {
                    "error": "ENGINE_UNSUPPORTED_INPUT",
                    "message": "aizynthfinder could not process the declared job",
                }
            )
        )
        sys.exit(2)
