from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from studio.domain.agent_workspace import textile_examples


def test_teaching_traces_pair_actual_runs_and_evaluate_native_calls_without_large_results(
    monkeypatch,
):
    workflow = SimpleNamespace(id=uuid.uuid4(), thread_id=uuid.uuid4())
    refs = [{"sourceId": "source-a"}]
    dataset = SimpleNamespace(
        source={"kind": "external_computed", "sourceRefs": refs},
        rows=[
            {
                "id": str(i),
                "polymerId": str(i),
                "target": i / 10,
                "property": "density",
                "unit": "g/cm3",
                "smiles": "*CC*",
            }
            for i in range(100)
        ],
    )
    captured = {}

    class Workflows:
        def __init__(self, *_):
            pass

        def get(self, *_args, **_kwargs):
            return workflow

        def require_resource(self, _row, _kind, identifier):
            assert identifier in {"property-data", "source-a", "source-b"}

        def authorize_tool(self, _row, _name, args):
            assert args["id"] in {"source-a", "source-b"}
            return args

        def add_resource(self, *_):
            pass

    class Learning:
        def __init__(self, *_):
            pass

        def _owned(self, *_):
            return dataset

        def authorize_dataset_training(self, *_):
            pass

        def import_dataset(self, payload):
            captured.update(payload)
            return {"id": "compiled"}

    monkeypatch.setattr(textile_examples, "WorkflowService", Workflows)
    monkeypatch.setattr(textile_examples, "LearningWorkspaceService", Learning)

    def event(run, kind, content, identifier):
        return SimpleNamespace(
            run_id=run,
            kind=kind,
            content=json.dumps(content, separators=(",", ":")),
            id=identifier,
            refs={"toolCallId": "reused-call"},
        )

    events = [
        event(
            "run-a",
            "tool_call",
            {"id": "reused-call", "name": "read_resource", "arguments": {"id": "source-a"}},
            "call-a",
        ),
        event("run-a", "tool_result", {"ok": True, "data": {"short": "A"}}, "result-a"),
        event(
            "run-b",
            "tool_call",
            {"id": "reused-call", "name": "read_resource", "arguments": {"id": "source-b"}},
            "call-b",
        ),
        event(
            "run-b",
            "tool_result",
            {"ok": True, "data": {"large": "LONG-RESULT-MARKER" * 300}},
            "result-b",
        ),
        event(
            "run-c",
            "tool_call",
            {"id": "reused-call", "name": "read_resource", "arguments": {"id": "source-a"}},
            "call-c",
        ),
        event("run-c", "tool_result", {"ok": False, "error": "failed"}, "result-c"),
    ]
    db = SimpleNamespace(scalars=lambda *_: events)
    ctx = SimpleNamespace(principal_id=uuid.uuid4(), workspace_id=uuid.uuid4())
    textile_examples.prepare_examples(
        db, ctx, None, {"workflowId": str(workflow.id), "datasetIds": ["property-data"]}
    )
    rows = [json.loads(line) for line in captured["content"].splitlines()]
    assert captured["dataKind"] == "synthetic"
    calls = [row for row in rows if row.get("evaluation", {}).get("expectedToolCalls")]
    assert len(calls) == 8
    assert {row["evaluation"]["expectedToolCalls"][0]["arguments"]["id"] for row in calls} == {
        "source-a",
        "source-b",
    }
    assert all(len(row["messages"]) == 2 for row in calls)
    traces = [row for row in rows if row.get("messages") and len(row["messages"]) == 4]
    assert len(traces) == 4
    assert all(row["metadata"]["toolEventId"] == "result-a" for row in traces)
    assert "LONG-RESULT-MARKER" not in captured["content"]
    assert "result-c" not in captured["content"]
    assert len(rows) <= 400


def test_tool_holdouts_are_stratified_without_splitting_event_variants():
    from studio.domain.learning.workspace_runtime.data import split_rows

    rows = [{"id": f"record-{i}", "documentId": f"polymer-{i}"} for i in range(30)]
    for i in range(5):
        for variant in range(4):
            rows.append(
                {
                    "id": f"tool-{i}-{variant}",
                    "documentId": f"tool-event-{i}",
                    "evaluation": {"expectedToolCalls": [{"name": "read_resource"}]},
                }
            )
    splits = split_rows(rows)
    for partition in ("train", "development", "final"):
        assert any(splits[row["id"]] == partition and row.get("evaluation") for row in rows)
    for i in range(5):
        assert len({splits[f"tool-{i}-{v}"] for v in range(4)}) == 1
