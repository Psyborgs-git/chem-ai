"""CS-1002 unit tests — the transform pipeline pieces (pure, no DB).

Covers the §20.3 mechanics: allowlisted fields, the LOCAL alias map,
metadata-key stripping, suspicious-content flags, and residual-risk
reporting that never labels anything anonymous or safe.
"""

from __future__ import annotations

import hashlib

import pytest

from studio.domain.learning.exports.transform import (
    MAX_DECLARED_TEXT,
    TransformService,
    _declared,
    _digest,
    _field_paths,
    _looks_like_structure,
    _Scan,
)
from studio.errors import DomainError


class TestAliases:
    def test_names_become_stable_tokens(self) -> None:
        scan = _Scan()
        t1 = scan.alias("material", "AcmeBond 3000")
        t2 = scan.alias("metric", "metric.tack-4h")
        assert t1 == "mat-0001"
        assert t2 == "m-0001"
        # Same name → same token (deterministic, deduped map).
        assert scan.alias("material", "AcmeBond 3000") == t1
        out = scan.text("AcmeBond 3000 cured per SOP-9", path="x", ref="r-0")
        assert out == "mat-0001 cured per SOP-9"
        assert "AcmeBond" not in out
        # The map exists locally only.
        assert scan.map["mat-0001"] == {"kind": "material", "original": "AcmeBond 3000"}

    def test_short_strings_never_alias(self) -> None:
        scan = _Scan()
        assert scan.alias("material", "ab") == "ab"
        assert scan.alias("material", None) is None
        assert scan.map == {}

    def test_longest_match_replaced_first(self) -> None:
        scan = _Scan()
        scan.alias("material", "Bond")
        scan.alias("material", "Bond Resin 9")
        out = scan.text("Bond Resin 9 and Bond", path="x", ref="r-0")
        assert out == "mat-0002 and mat-0001"


class TestDenylist:
    def test_metadata_keys_stripped_and_reported(self) -> None:
        scan = _Scan()
        out = scan.filter(
            {
                "claim": "viscosity 900",
                "recorded_by": "jdoe",
                "internal_note": "talk to Qi",
                "details": {"source": "SOP-44", "value": 1.2},
            },
            path="statement",
            ref="r-0001",
        )
        assert out == {"claim": "viscosity 900", "details": {"value": 1.2}}
        removed = {(k["path"], k["reason"]) for k in scan.removed_keys}
        assert ("statement.recorded_by", "metadata_key") in removed
        assert ("statement.internal_note", "metadata_key") in removed
        assert ("statement.details.source", "metadata_key") in removed

    def test_deep_nesting_flagged(self) -> None:
        scan = _Scan()
        node: dict = {}
        cur = node
        for _i in range(30):
            cur["next"] = {}
            cur = cur["next"]
        scan.filter(node, path="v", ref="r-0", depth=0)
        assert any(f["pattern"] == "max_depth" for f in scan.flags)


class TestPatternScan:
    @pytest.mark.parametrize(
        ("text", "pattern"),
        [
            ("contact jdoe@acme-lab.example for data", "email"),
            ("see https://internal.example/sop", "url"),
            ("file at /srv/vault/docs/spec.pdf", "filesystem_path"),
            ("id 3f2504e0-4f89-41d3-9a0c-0305e82c3301", "uuid"),
            ("api_key=sk-live-9911", "secret_value"),
            ("sha256 " + "ab" * 32, "hash_blob"),
        ],
    )
    def test_suspicious_content_flagged(self, text: str, pattern: str) -> None:
        scan = _Scan()
        scan.text(text, path="p", ref="r-0")
        assert any(f["pattern"] == pattern for f in scan.flags)

    def test_clean_numeric_text_unflagged(self) -> None:
        scan = _Scan()
        scan.text("viscosity 900 mPa.s at 298 K", path="p", ref="r-0")
        assert scan.flags == []


class TestStructures:
    def test_structure_notation_is_residual_not_flag(self) -> None:
        assert _looks_like_structure("CC(=O)Oc1ccccc1C(=O)O")
        assert _looks_like_structure("InChI=1S/H2O/h1H2")
        assert not _looks_like_structure("plain english words here")
        scan = _Scan()
        scan.text("SMILES CC(=O)Oc1ccccc1C(=O)O", path="p", ref="r-0")
        assert scan.flags == []
        assert scan.residuals["structures"] != []

    def test_derived_keys_residual(self) -> None:
        scan = _Scan()
        scan.filter({"spectrum": {"peaks": [1, 2]}}, path="v", ref="r-0")
        assert any(f["path"] == "v" for f in scan.residuals["derived_features"])
        assert any(f["path"] == "v.spectrum" for f in scan.residuals["derived_features"])


class TestResidualDetection:
    def test_process_windows(self) -> None:
        scan = _Scan()
        scan.filter({"actual": {"temperature": 298.15, "rpm": 300}}, path="c", ref="r-0")
        hits = [f for f in scan.residuals["process_windows"] if f["path"] == "c.actual"]
        assert hits and set(hits[0]["keys"]) == {"temperature", "rpm"}

    def test_compositional_dict_is_ratio_residual(self) -> None:
        scan = _Scan()
        scan.filter({"resin": 55.0, "hardener": 45.0}, path="v.parts", ref="r-0")
        assert any(f["path"] == "v.parts" for f in scan.residuals["ratios"])

    def test_ratio_named_key(self) -> None:
        scan = _Scan()
        scan.filter({"wt_pct": 72}, path="v", ref="r-0")
        assert any(f["path"] == "v" for f in scan.residuals["ratios"])

    def test_percent_unit_value(self) -> None:
        scan = _Scan()
        scan.filter({"kind": "numeric", "value": "55", "unit": "wt%"}, path="v", ref="r-0")
        assert any(f["path"] == "v" for f in scan.residuals["ratios"])

    def test_scientific_numbers_alone_not_ratios(self) -> None:
        scan = _Scan()
        scan.filter({"value": "4.2", "uncertainty": "0.1"}, path="v", ref="r-0")
        assert scan.residuals["ratios"] == []


class TestResidualReport:
    def test_never_anonymous_never_safe(self) -> None:
        scan = _Scan()
        report = TransformService._residual_report(
            [{"ref": "r-0000", "kind": "measurement", "fields": {}}], scan
        )
        assert report["verdict"] == "residual_disclosure"
        assert report["anonymous"] is False
        assert report["safe"] is False
        assert report["certified"] is False
        assert "Masking is not confidentiality" in report["advisory"]
        # Even an empty record set reports the metadata exposure.
        assert any(c["kind"] == "metadata" for c in report["categories"])

    def test_flags_surface_flagged_records(self) -> None:
        scan = _Scan()
        scan.text("email me at a@b.co", path="p", ref="r-0001")
        report = TransformService._residual_report(
            [{"ref": "r-0001", "kind": "claim", "fields": {}}], scan
        )
        assert report["flaggedRecords"] == ["r-0001"]
        assert report["flags"][0]["severity"] == "high"


class TestHelpers:
    def test_field_paths(self) -> None:
        paths = _field_paths({"a": {"b": 1, "c": [{"d": 2}]}, "e": "x"})
        assert paths == {"a.b", "a.c.d", "e"}

    def test_digest_deterministic_and_sensitive(self) -> None:
        a = _digest({"x": 1, "y": [2, 3]})
        assert a == _digest({"y": [2, 3], "x": 1})
        assert a != _digest({"x": 1, "y": [2, 4]})
        assert a == hashlib.sha256(b'{"x":1,"y":[2,3]}').hexdigest()

    def test_declared_bounds(self) -> None:
        assert _declared(None, "f") is None
        assert _declared("  acme  ", "f") == "acme"
        with pytest.raises(DomainError):
            _declared("x" * (MAX_DECLARED_TEXT + 1), "f")
