"""PAR-01 — canonical success-contract schema (draft + freeze gates,
legacy ``requiredMetrics`` read path)."""

from __future__ import annotations

import pytest

from studio.domain.tasks.contract import (
    resolve_metrics,
    validate_draft_payload,
    validate_freeze_payload,
)
from studio.errors import DomainError


def _metric(**over):
    m = {
        "id": "m.viscosity",
        "label": "viscosity",
        "required": True,
        "value_kind": "numeric",
        "operator": "gte",
        "target_values": ["500"],
        "unit": "mPa·s",
        "method_revision_id": None,
        "conditions": {"substrate_revision_id": None, "description": "std"},
        "required_evidence": ["lab_measurement"],
        "aggregation": "mean",
        "replication_rule": {"minIndependentBatches": 2},
    }
    m.update(over)
    return m


def _payload(**over):
    p = {"metrics": [_metric()], "hard_constraints": [], "unknowns": []}
    p.update(over)
    return p


class TestDraftValidation:
    def test_canonical_metric_accepted(self) -> None:
        validate_draft_payload(_payload())

    def test_empty_payload_is_a_valid_draft(self) -> None:
        """A draft may be empty — nothing is demanded at draft time."""
        validate_draft_payload({})

    def test_non_object_rejected(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_draft_payload([1])
        assert exc.value.code == "VALIDATION"

    def test_row_owned_fields_rejected(self) -> None:
        """A payload must not carry revision identity — the row owns it."""
        with pytest.raises(DomainError) as exc:
            validate_draft_payload(_payload(revision=7))
        assert "revision" in exc.value.message

    def test_unsupported_schema_version_rejected(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_draft_payload(_payload(schema_version="9.9.9"))
        assert "schema_version" in exc.value.message

    def test_unknown_metric_field_rejected(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_draft_payload(_payload(metrics=[_metric(nonsense=1)]))
        assert "metrics[0]" in (exc.value.field_path or "")

    def test_unknown_operator_rejected(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_draft_payload(_payload(metrics=[_metric(operator="≈")]))
        assert "operator" in exc.value.message

    def test_unknown_evidence_class_rejected(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_draft_payload(
                _payload(metrics=[_metric(required_evidence=["vibes"])])
            )
        assert "vibes" in exc.value.message

    def test_bad_uuid_rejected(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_draft_payload(
                _payload(metrics=[_metric(method_revision_id="not-a-uuid")])
            )
        assert "method_revision_id" in exc.value.message

    def test_unknown_top_level_field_allowed_on_draft(self) -> None:
        """Unknown fields are explicit unknowns preserved for review —
        drafts keep them; the freeze gate is where they must resolve."""
        validate_draft_payload(_payload(thresholds={"gloss": ">80"}))

    def test_declared_unknowns_allowed_on_draft(self) -> None:
        validate_draft_payload(_payload(unknowns=["target pH unclear"]))


class TestFreezeGate:
    def test_canonical_contract_freezes(self) -> None:
        validate_freeze_payload(_payload())

    def test_loose_persisted_metric_freezes(self) -> None:
        """{name, target: ">= 500"} — already persisted and evaluable."""
        validate_freeze_payload(
            {"metrics": [{"name": "viscosity", "target": ">= 500"}]}
        )

    def test_empty_contract_cannot_freeze(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_freeze_payload({})
        assert "evaluable metrics" in exc.value.message

    def test_empty_metric_list_cannot_freeze(self) -> None:
        with pytest.raises(DomainError):
            validate_freeze_payload({"metrics": []})

    def test_unknown_top_level_field_cannot_freeze(self) -> None:
        """Unknown draft fields must not silently become an assessable
        success contract — they review first or go into a successor."""
        with pytest.raises(DomainError) as exc:
            validate_freeze_payload(_payload(thresholds={"gloss": ">80"}))
        assert "thresholds" in exc.value.message

    def test_declared_unknowns_cannot_freeze(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_freeze_payload(_payload(unknowns=["target pH unclear"]))
        assert "unknowns" in exc.value.message

    def test_boundless_metric_cannot_freeze(self) -> None:
        with pytest.raises(DomainError) as exc:
            validate_freeze_payload({"metrics": [{"id": "m.x"}]})
        assert "no bound" in exc.value.message

    def test_anonymous_metric_cannot_freeze(self) -> None:
        with pytest.raises(DomainError):
            validate_freeze_payload(
                {"metrics": [{"operator": "gte", "target_values": ["1"]}]}
            )

    def test_unparseable_target_cannot_freeze(self) -> None:
        """'between' with a single value cannot form a bound — the
        freeze gate refuses instead of binding an unparseable clause."""
        with pytest.raises(DomainError):
            validate_freeze_payload(
                {"metrics": [{"name": "m", "target": "fast"}]}
            )

    def test_legacy_required_metrics_only_freezes(self) -> None:
        """Pre-PAR-01 UI payloads freeze through the explicit legacy
        read path — they carry real, evaluable content."""
        validate_freeze_payload(
            {
                "requiredMetrics": [
                    {
                        "name": "viscosity",
                        "operator": ">=",
                        "target": {"value": "500", "unit": "mPa·s"},
                    }
                ]
            }
        )


class TestResolveMetrics:
    def test_canonical_metrics_resolve_verbatim(self) -> None:
        m = _metric()
        r = resolve_metrics({"metrics": [m]})
        assert r.metrics == [m]
        assert not r.legacy
        assert not r.issues

    def test_legacy_payload_translates(self) -> None:
        r = resolve_metrics(
            {
                "requiredMetrics": [
                    {
                        "name": "viscosity",
                        "operator": ">=",
                        "target": {"value": "500", "unit": "mPa·s"},
                    }
                ]
            }
        )
        assert r.legacy
        assert len(r.metrics) == 1
        m = r.metrics[0]
        assert m["id"] == "viscosity"
        assert m["operator"] == "gte"
        assert m["target_values"] == ["500"]
        assert m["unit"] == "mPa·s"

    def test_both_vocabularies_canonical_wins_with_issue(self) -> None:
        r = resolve_metrics(_payload(requiredMetrics=["m.tack"]))
        assert len(r.metrics) == 1
        assert r.metrics[0]["id"] == "m.viscosity"
        assert not r.legacy
        assert any("requiredMetrics" in i for i in r.issues)

    def test_ambiguous_legacy_entry_surfaces_issue_not_silent_drop(
        self,
    ) -> None:
        r = resolve_metrics({"requiredMetrics": [{"operator": ">="}]})
        assert r.legacy
        assert r.metrics == []
        assert any("no metric name" in i for i in r.issues)

    def test_legacy_target_without_value_keeps_shell_with_issue(self) -> None:
        r = resolve_metrics(
            {"requiredMetrics": [{"name": "viscosity", "operator": "target"}]}
        )
        assert r.legacy
        assert len(r.metrics) == 1
        assert "target_values" not in r.metrics[0]
        assert any("bound" in i or "operator" in i for i in r.issues)

    def test_constraints_list_resolves_as_gates(self) -> None:
        """Persisted 'constraints' strings are the seeded gate list —
        they evaluate (not_evaluated) rather than vanish."""
        r = resolve_metrics({"constraints": ["keep pH below 9"]})
        assert r.gates == ["keep pH below 9"]

    def test_canonical_gates_beat_legacy_constraints(self) -> None:
        r = resolve_metrics(
            {
                "hard_constraints": [{"text": "canonical"}],
                "constraints": ["legacy"],
            }
        )
        assert r.gates == [{"text": "canonical"}]
        assert any("constraints" in i for i in r.issues)

    def test_non_dict_payload_is_an_issue(self) -> None:
        r = resolve_metrics("nope")
        assert r.metrics == []
        assert r.issues
