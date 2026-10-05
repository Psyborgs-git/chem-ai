"""In-process RDKit worker — runs inside the isolated backend.

Reads one JSON document from the input file (``{"smiles": str}`` or
``{"molfile": str}``) and prints one typed JSON result. Failure is an
explicit typed error — a descriptor is never fabricated to fill a gap.
This file is self-contained: the adapter writes it into the run's
scratch so the image itself stays generic.
"""

from __future__ import annotations

import json
import sys

DESCRIPTORS = (
    "mw",
    "exact_mw",
    "logp",
    "hbd",
    "hba",
    "tpsa",
    "rotatable_bonds",
    "num_atoms",
    "num_heavy_atoms",
    "num_rings",
    "fraction_csp3",
)


def _fail(code: str, message: str, stage: str) -> dict[str, object]:
    return {"ok": False, "error": {"code": code, "message": message, "stage": stage}}


def run(payload: dict[str, object]) -> dict[str, object]:
    try:
        from rdkit import Chem, rdBase
        from rdkit.Chem import Descriptors, rdMolDescriptors
    except ImportError:
        return _fail("ENGINE_UNAVAILABLE", "rdkit is not importable", "init")

    smiles = payload.get("smiles")
    molfile = payload.get("molfile")
    if smiles is None and molfile is None:
        return _fail("EMPTY_INPUT", "a 'smiles' or 'molfile' field is required", "input")
    if smiles is not None and not isinstance(smiles, str):
        return _fail("EMPTY_INPUT", "'smiles' must be a string", "input")
    if molfile is not None and not isinstance(molfile, str):
        return _fail("EMPTY_INPUT", "'molfile' must be a string", "input")
    if smiles is not None and len(smiles) > 8192:
        return _fail("ENGINE_UNSUPPORTED_INPUT", "smiles exceeds 8192 chars", "input")

    # Parse without sanitizing first so a parse failure and a valence/
    # sanitization failure are distinct typed stages (AT-0404-2).
    if smiles is not None:
        mol = Chem.MolFromSmiles(smiles, sanitize=False)
        stage_in = "smiles"
    else:
        mol = Chem.MolFromMolBlock(molfile, sanitize=False)
        stage_in = "molfile"
    if mol is None:
        return _fail("PARSE_FAILED", f"input cannot be parsed as {stage_in}", "parse")
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # valence/aromaticity/kekulization errors
        return _fail("SANITIZE_FAILED", str(exc)[:400], "sanitize")

    try:
        canonical = Chem.MolToSmiles(mol)
        inchi = Chem.MolToInchiKey(mol) or None
        formula = rdMolDescriptors.CalcMolFormula(mol)
        descriptors = {
            "mw": round(Descriptors.MolWt(mol), 4),
            "exact_mw": round(Descriptors.ExactMolWt(mol), 4),
            "logp": round(Descriptors.MolLogP(mol), 4),
            "hbd": Descriptors.NumHDonors(mol),
            "hba": Descriptors.NumHAcceptors(mol),
            "tpsa": round(Descriptors.TPSA(mol), 4),
            "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
            "num_atoms": mol.GetNumAtoms(),
            "num_heavy_atoms": mol.GetNumHeavyAtoms(),
            "num_rings": rdMolDescriptors.CalcNumRings(mol),
            "fraction_csp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 4),
        }
    except Exception as exc:
        return _fail("INTERNAL", f"descriptor computation failed: {exc}", "describe")

    return {
        "ok": True,
        "engine": {"id": "rdkit", "version": rdBase.rdkitVersion},
        "method": "rdkit-descriptors/v1",
        "structure": {
            "canonical_smiles": canonical,
            "inchi_key": inchi,
            "formula": formula,
        },
        "descriptors": descriptors,
    }


if __name__ == "__main__":
    try:
        with open(sys.argv[1]) as fh:
            doc = json.load(fh)
    except Exception as exc:
        print(json.dumps(_fail("EMPTY_INPUT", f"cannot read input: {exc}", "input")))
        sys.exit(0)  # typed failure is the contract — exit stays clean
    print(json.dumps(run(doc)))
