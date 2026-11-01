"""Deterministic task checks; these never certify unsupported materials claims."""

from __future__ import annotations

import json
import math
import re
from typing import Any


def visible_answer(text: str) -> str:
    """Remove only an empty model protocol prefix, never a reasoning body."""
    return re.sub(r"^\s*(?:<think>\s*</think>\s*)+", "", text)


def json_answer(text: str) -> Any:
    text = visible_answer(text)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(cleaned)


def answer_checks(text: str, row: dict[str, Any]) -> dict[str, Any]:
    contract = row.get("evaluation") or {}
    if not isinstance(contract, dict):
        return {}
    checks: dict[str, Any] = {}
    try:
        answer = json_answer(text)
    except ValueError:
        answer = None
    required = contract.get("requiredFields", [])
    if required or contract.get("jsonRequired"):
        try:
            raw_json = json.loads(text.strip())
        except ValueError:
            raw_json = None
        checks["strictJsonOnly"] = isinstance(raw_json, dict) and all(
            key in raw_json for key in required
        )
        checks["structuredJson"] = isinstance(answer, dict) and all(
            key in answer for key in required
        )
        try:
            expected_json = json_answer(str(row.get("response", row.get("expected", ""))))
        except ValueError:
            expected_json = None
        if isinstance(expected_json, dict):
            # Formatting-independent reference comparison also checks declared
            # origin and claim flags; field presence alone cannot establish them.
            checks["jsonReferenceMatch"] = isinstance(answer, dict) and json.dumps(
                answer, sort_keys=True
            ) == json.dumps(expected_json, sort_keys=True)
    citations = contract.get("allowedCitations")
    if isinstance(citations, list):
        actual = answer.get("citations", []) if isinstance(answer, dict) else []
        actual = (
            [
                str(value.get("sourceId", value.get("id", "")))
                if isinstance(value, dict)
                else str(value)
                for value in actual
            ]
            if isinstance(actual, list)
            else []
        )
        allowed = set(map(str, citations))
        needed = set(map(str, contract.get("requiredCitations", [])))
        checks["citationIdsSupported"] = (
            bool(actual) and all(value in allowed for value in actual) and needed.issubset(actual)
        )
        checks["unsupportedCitationCount"] = sum(value not in allowed for value in actual)
    for index, target in enumerate(contract.get("numericTargets", [])):
        value = answer
        try:
            for key in str(target["field"]).split("."):
                value = value[key]
            unit = None
            if isinstance(value, dict):
                unit, value = value.get("unit"), value.get("value")
            correct = math.isclose(
                float(value),
                float(target["value"]),
                rel_tol=float(target.get("relativeTolerance", 0.01)),
                abs_tol=float(target.get("absoluteTolerance", 1e-6)),
            )
            correct = correct and (not target.get("unit") or unit == target["unit"])
        except (KeyError, TypeError, ValueError):
            correct = False
        checks[f"numericWithUnit{index}"] = correct
    expected_tools = contract.get("expectedToolCalls")
    if isinstance(expected_tools, list):
        calls = []
        for block in re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, flags=re.DOTALL):
            try:
                calls.append(json.loads(block))
            except ValueError:
                continue
        if not calls and isinstance(answer, dict) and answer.get("name", answer.get("tool")):
            calls = [
                {
                    "name": answer.get("name", answer.get("tool")),
                    "arguments": answer.get("arguments", {}),
                }
            ]
        checks["toolCallsCorrect"] = calls == expected_tools
    forbidden = contract.get("forbiddenClaims", [])
    if forbidden:
        checks["forbiddenClaimsAbsent"] = all(
            str(phrase).casefold() not in text.casefold() for phrase in forbidden
        )
    return checks


def aggregate_checks(examples: list[dict[str, Any]], key: str) -> dict[str, Any]:
    names = {
        name
        for item in examples
        for name, value in item.get(key, {}).items()
        if isinstance(value, bool)
    }
    result: dict[str, Any] = {}
    for name in sorted(names):
        values = [item[key][name] for item in examples if name in item.get(key, {})]
        result[name] = {
            "correct": sum(values),
            "total": len(values),
            "rate": sum(values) / len(values),
        }
    result["meaning"] = (
        "Deterministic declared task checks; citation-ID validity does not prove claim entailment"
    )
    return result


def regression_metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    if not actual or len(actual) != len(predicted):
        raise ValueError("Matched labelled predictions are required")
    errors = [prediction - label for prediction, label in zip(predicted, actual, strict=True)]
    return {
        "mae": sum(abs(error) for error in errors) / len(errors),
        "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)),
    }


def applicability(
    training: list[str], candidates: list[str], threshold: float = 0.25
) -> list[dict[str, Any]]:
    from rdkit import Chem, DataStructs
    from rdkit.Chem import rdFingerprintGenerator

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=1024)
    reference = [generator.GetFingerprint(Chem.MolFromSmiles(smiles)) for smiles in training]
    results = []
    for smiles in candidates:
        fp = generator.GetFingerprint(Chem.MolFromSmiles(smiles))
        similarity = max(DataStructs.BulkTanimotoSimilarity(fp, reference), default=0.0)
        results.append(
            {
                "nearestTrainingSimilarity": float(similarity),
                "inDomain": similarity >= threshold,
                "threshold": threshold,
                "method": "Morgan1024_radius2_Tanimoto",
                "meaning": "Uncalibrated structural coverage flag",
            }
        )
    return results
