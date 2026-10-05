"""CS-0404 acceptance tests — real RDKit via the engine adapter.

AT-0404-1  benign known-valid molecule -> parsed structure, descriptors
           and the exact engine version recorded as structural evidence
AT-0404-2  invalid-valence structure -> explicit typed failure, and no
           fabricated descriptors

These run wherever a *real* rdkit exists: the container image (this
host) or a native install (CI engines job). A missing engine is an
explicit skip — never a simulated pass.
"""

from __future__ import annotations

import pytest

from engine_adapter_rdkit import EngineError, RDKitAdapter, StructuralResult

pytestmark = pytest.mark.engine


@pytest.fixture(scope="module")
def adapter() -> RDKitAdapter:
    a = RDKitAdapter()
    info = a.capability()
    if not info.available:
        pytest.skip(f"rdkit engine unavailable: {info.detail}")
    return a


class TestBenignMolecule:
    """AT-0404-1: ethanol parses, sanitizes and describes."""

    def test_descriptors_and_version(self, adapter: RDKitAdapter) -> None:
        result = adapter.describe(smiles="CCO")
        assert isinstance(result, StructuralResult)
        assert result.ok
        assert result.canonical_smiles == "CCO"
        assert result.formula == "C2H6O"
        assert result.inchi_key == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        d = result.descriptors
        # A real engine run records real values — ranges, not
        # hardcoded equality where numeric formatting may vary.
        assert 45.0 < d["mw"] < 47.0
        assert d["hbd"] == 1
        assert d["hba"] == 1
        assert d["num_heavy_atoms"] == 3
        assert result.engine_version and result.engine_version.count(".") >= 2
        assert result.evidence_type == "descriptor"  # structural, not lab
        assert result.method == "rdkit-descriptors/v1"

    def test_capability_reports_real_version(self, adapter: RDKitAdapter) -> None:
        info = adapter.capability()
        assert info.available
        assert info.version is not None
        assert info.engine_id == "rdkit"


class TestInvalidValence:
    """AT-0404-2: explicit failure, zero fabricated output."""

    def test_invalid_valence_fails_explicitly(self, adapter: RDKitAdapter) -> None:
        # Pentavalent carbon — parses, fails sanitization.
        result = adapter.describe(smiles="C(C)(C)(C)(C)(C)")
        assert isinstance(result, EngineError)
        assert result.code in {"SANITIZE_FAILED", "PARSE_FAILED"}
        assert result.stage in {"sanitize", "parse"}
        assert result.message  # a real engine diagnostic

    def test_unparseable_fails_explicitly(self, adapter: RDKitAdapter) -> None:
        result = adapter.describe(smiles="definitely_not_a_smiles_$$$")
        assert isinstance(result, EngineError)
        assert result.code == "PARSE_FAILED"
        assert result.stage == "parse"

    def test_empty_input_typed_failure(self, adapter: RDKitAdapter) -> None:
        result = adapter.describe(smiles=None, molfile=None)
        assert isinstance(result, EngineError)
        assert result.code == "EMPTY_INPUT"

    def test_no_fabricated_descriptors(self, adapter: RDKitAdapter) -> None:
        """A failed run must carry no descriptor-shaped data."""
        result = adapter.describe(smiles="C(C)(C)(C)(C)(C)")
        assert isinstance(result, EngineError)
        assert not hasattr(result, "descriptors")
        assert not hasattr(result, "canonical_smiles")
