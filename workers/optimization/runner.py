"""Network-denied container entrypoint; bounded JSON in/out, no pickle."""

from __future__ import annotations

import json
import sys
from typing import Any

from engine_adapter_baybe import BayBEAdapter, CampaignSpec, EngineFailure


def run(request: dict[str, Any]) -> dict[str, Any]:
    spec = CampaignSpec.model_validate(request["spec"])
    result = BayBEAdapter().recommend(
        spec, batch_size=request["batch_size"], request_index=request["request_index"],
        observations=request["observations"],
        reserved=request["reserved"],
        pending=request["pending"],
    )
    return result.model_dump(mode="json")


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
        # Tracebacks/inputs can contain proprietary recipes and must stay private.
        print(
            json.dumps(
                {
                    "error": "ENGINE_UNSUPPORTED_INPUT",
                    "message": "BayBE could not process the declared campaign",
                }
            )
        )
        sys.exit(2)
