import json

import pytest

from studio.domain.agent_workspace.tools import bounded_result, result_summary


def test_memory_tool_teaches_the_actual_persisted_reference_shape():
    import jsonschema
    import pytest

    from studio.domain.agent_workspace.tools import catalog

    schema = next(
        tool["input_schema"] for tool in catalog() if tool["name"] == "save_research_memory"
    )
    payload = {
        "title": "Continue",
        "body": "Open questions",
        "sourceRefs": [{"kind": "page", "id": "page-id", "revision": 2}],
    }
    jsonschema.validate(payload, schema)
    for refs in (
        [],
        [{"kind": "note", "id": "page-id"}],
        [{"sourceId": "source-id"}],
        [{"kind": "source", "id": "source-id", "body": "not a reference"}],
    ):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**payload, "sourceRefs": refs}, schema)


def test_large_retained_source_receipt_preserves_id_and_read_handle():
    source = {"id": "source-id", "checksum": "hash", "extractedText": "x" * 800000}
    receipt = result_summary("fetch_resource", source)
    encoded = json.loads(bounded_result(receipt))
    assert encoded["ok"] is True
    assert encoded["data"] == {
        "id": "source-id",
        "checksum": "hash",
        "textLength": 800000,
        "readTool": "read_resource",
    }
    assert len(source["extractedText"]) == 800000


def test_dataset_mutation_receipts_keep_validation_and_partition_counts():
    source = {
        "id": "dataset-id",
        "rowCount": 400,
        "rows": [{"text": "x" * 1000}] * 200,
        "splits": {str(i): "train" for i in range(400)},
        "partitions": {"train": 320, "development": 40, "final": 40},
        "report": {"accepted": 400},
    }
    for name in (
        "create_dataset",
        "import_retained_dataset",
        "freeze_dataset",
        "prepare_polymer_research_dataset",
        "merge_datasets",
    ):
        receipt = json.loads(bounded_result(result_summary(name, source)))
        assert receipt["ok"] is True
        assert receipt["data"]["partitions"] == source["partitions"]
        assert receipt["data"]["readTool"] == "read_dataset"
        assert "rows" not in receipt["data"]


def test_job_receipt_keeps_recent_events_and_real_metrics():
    job = {"id": "job-id", "events": [{"step": i} for i in range(200)], "result": {"mae": 0.1}}
    receipt = result_summary("await_training_job", job)
    assert receipt["eventCount"] == 200
    assert receipt["events"][0]["step"] == 180
    assert receipt["result"] == {"mae": 0.1}


def test_long_workflow_output_is_reserved_before_paid_inference():
    from types import SimpleNamespace

    from studio.domain.agent_workspace.runtime import _estimate_cost

    model = SimpleNamespace(input_price=2, output_price=10)
    standard = _estimate_cost(model, [], True)
    research = _estimate_cost(model, [], True, max_output_tokens=8192)
    assert abs((research - standard) - (8192 - 2048) * 10 / 1000000) < 1e-10


@pytest.mark.parametrize("remote", [False, True])
def test_priced_http_models_reserve_and_settle_cost_independently_of_url(remote):
    from types import SimpleNamespace

    from studio.domain.agent_workspace.runtime import _cost, _estimate_cost

    model = SimpleNamespace(input_price=2, output_price=10)
    reserve = _estimate_cost(model, [{"role": "user", "content": "Research"}], remote)
    assert reserve > 0
    assert _cost(
        {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}, model, remote, reserve
    ) == pytest.approx(0.0004)
    assert _cost({}, model, remote, reserve) == reserve


@pytest.mark.parametrize("prices", [(None, None), (2, None), (None, 10)])
def test_unpriced_loopback_http_model_cannot_enter_bounded_inference(prices):
    from types import SimpleNamespace

    from studio.domain.agent_workspace.runtime import _estimate_cost

    with pytest.raises(RuntimeError, match="explicit input and output token prices"):
        _estimate_cost(SimpleNamespace(input_price=prices[0], output_price=prices[1]), [], False)


def test_explicitly_free_http_and_direct_local_inference_remain_free():
    from types import SimpleNamespace

    from studio.domain.agent_workspace.runtime import _cost, _estimate_cost

    free = SimpleNamespace(input_price=0, output_price=0)
    usage = {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    assert _estimate_cost(free, [], False) == 0
    assert _cost(usage, free, False, 0) == 0
    assert _estimate_cost(None, [], False) == 0
    assert _cost(usage, None, False, 0) == 0


def test_large_rejection_reports_and_metadata_do_not_hide_mutated_resource_ids():
    source = {
        "id": "dataset-id",
        "report": {"rejected": 1000, "rejections": [{"error": "x" * 300}] * 1000},
    }
    receipt = result_summary("create_dataset", source)
    assert len(receipt["report"]["rejections"]) == 10
    assert receipt["report"]["rejected"] == 1000
    assert receipt["report"]["nextRejectionOffset"] == 10
    assert json.loads(bounded_result(receipt))["ok"]
    receipt["source"] = {"unexpectedLargeMetadata": "x" * 80000}
    fallback = json.loads(bounded_result(receipt))
    assert fallback["ok"]
    assert fallback["data"]["id"] == "dataset-id"
    assert fallback["data"]["receiptTruncated"]


def test_simulation_with_many_artifacts_preserves_physics_summary():
    result = {
        "id": "simulation-id",
        "state": "completed",
        "trainingEligible": False,
        "result": {"numericallyStable": True},
        "artifacts": [{"path": "long-retained-file-name-" * 5 + str(i)} for i in range(500)],
    }
    receipt = json.loads(bounded_result(result_summary("await_simulation_job", result)))
    assert receipt["ok"]
    assert receipt["data"]["result"]["numericallyStable"]
    assert receipt["data"]["artifactCount"] == 500
    assert len(receipt["data"]["artifacts"]) == 20
