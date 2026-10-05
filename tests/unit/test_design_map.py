"""Design-map conformance (AT-0205-3).

No Figma design was supplied — the map must contain no fabricated
node IDs and no parity claims, and every implemented component must
point at a real file.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = json.loads((ROOT / "docs" / "design" / "design-map.json").read_text())

REQUIRED_SCREENS = {
    "project-home",
    "project-detail",
    "task-wizard",
    "task-overview",
    "research-session",
    "candidate-editor",
    "candidate-comparison",
    "reference-product-detail",
    "material-detail",
    "evidence-viewer",
    "import-review",
    "experiment-plan-review",
    "execution-capture",
    "measurement-review",
    "run-detail",
    "compute-settings",
    "dataset-builder",
    "training-run-detail",
    "evaluation-report",
    "model-registry",
    "export-review",
    "workspace-settings",
    "task-closeout",
}

REQUIRED_COMPONENT_PREFIXES = {"atom.", "molecule.", "state."}
PARITY_TERMS = ("pixel-perfect", "pixel perfect", "pixel-parity", "figma.com")


def test_required_screens_all_present() -> None:
    present = {s["screen_id"] for s in MAP["screens"]}
    assert REQUIRED_SCREENS <= present, REQUIRED_SCREENS - present


def test_no_fabricated_figma_references() -> None:
    assert MAP["figma_file"] is None
    assert MAP["design_status"] == "logical-specification-only"
    for entry in MAP["screens"] + MAP["components"]:
        assert entry["figma_node_id"] is None, entry


def test_no_parity_language_anywhere() -> None:
    raw = json.dumps(MAP).lower()
    for term in PARITY_TERMS:
        assert term not in raw, f"parity/fabrication term present: {term}"


def test_implemented_components_point_at_real_files() -> None:
    for c in MAP["components"]:
        if c["status"] != "implemented":
            continue
        code = c["code_path"].split("#", 1)[0]
        assert (ROOT / code).is_file(), f"missing code for {c['component_id']}"
        if c["test_path"] is not None:
            test = c["test_path"].split("#", 1)[0]
            assert (ROOT / test).is_file(), f"missing test for {c['component_id']}"


def test_component_ids_use_stable_vocabulary() -> None:
    for c in MAP["components"]:
        assert any(c["component_id"].startswith(p) for p in REQUIRED_COMPONENT_PREFIXES), c[
            "component_id"
        ]
