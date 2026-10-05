"""Physics-level validation and QCSchema construction (§16.2).

Pure Python — no qcengine/qcelemental import — so the host process can
validate and build the persisted QCSchema payload without science deps
(E05). The container re-validates the same bytes against the real
AtomicInput model before execution.
"""

from __future__ import annotations

import math
from typing import Any

from .contracts import (
    ADAPTER_VERSION,
    ANGSTROM_TO_BOHR,
    EngineFailure,
    QuantumJobSpec,
    program_support,
)

# Full periodic table by atomic number (index = Z). Symbols are public
# chemical data; a valid symbol is still not a promise the *engine* can
# treat it — element coverage is a method property (e.g. GFN methods
# cover Z <= 86) and real engine rejection stays a typed failure.
ELEMENTS: tuple[str, ...] = (
    "H",
    "He",
    "Li",
    "Be",
    "B",
    "C",
    "N",
    "O",
    "F",
    "Ne",
    "Na",
    "Mg",
    "Al",
    "Si",
    "P",
    "S",
    "Cl",
    "Ar",
    "K",
    "Ca",
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Ga",
    "Ge",
    "As",
    "Se",
    "Br",
    "Kr",
    "Rb",
    "Sr",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "In",
    "Sn",
    "Sb",
    "Te",
    "I",
    "Xe",
    "Cs",
    "Ba",
    "La",
    "Ce",
    "Pr",
    "Nd",
    "Pm",
    "Sm",
    "Eu",
    "Gd",
    "Tb",
    "Dy",
    "Ho",
    "Er",
    "Tm",
    "Yb",
    "Lu",
    "Hf",
    "Ta",
    "W",
    "Re",
    "Os",
    "Ir",
    "Pt",
    "Au",
    "Hg",
    "Tl",
    "Pb",
    "Bi",
    "Po",
    "At",
    "Rn",
    "Fr",
    "Ra",
    "Ac",
    "Th",
    "Pa",
    "U",
    "Np",
    "Pu",
    "Am",
    "Cm",
    "Bk",
    "Cf",
    "Es",
    "Fm",
    "Md",
    "No",
    "Lr",
    "Rf",
    "Db",
    "Sg",
    "Bh",
    "Hs",
    "Mt",
    "Ds",
    "Rg",
    "Cn",
    "Nh",
    "Fl",
    "Mc",
    "Lv",
    "Ts",
    "Og",
)
_ATOMIC_NUMBER = {s: z for z, s in enumerate(ELEMENTS, start=1)}

# Physical sanity bounds — coordinates beyond ~5e4 Å are never real
# input for these methods; they are a units/precision bug.
_MAX_COORD_BOHR = 1.0e5
_MAX_CHARGED_ELECTRONS_DEFICIT = 0


def canonical_method(spec: QuantumJobSpec) -> str:
    """Map the requested method to its canonical support-matrix name."""
    support = program_support(spec.program)
    methods: dict[str, frozenset[str]] = (support or {}).get("methods", {})
    for name in methods:
        if name.lower() == spec.method.lower():
            return str(name)
    raise EngineFailure(
        "ENGINE_UNSUPPORTED_INPUT",
        f"method '{spec.method}' is not supported for {spec.program}",
    )


def validate_molecule(spec: QuantumJobSpec) -> list[int]:
    """Structure-level checks (in the pydantic model) plus physics-level
    checks here: real element symbols, geometry length/order, finite and
    sane coordinates, charge/spin parity. Returns atomic numbers."""
    mol = spec.molecule
    numbers: list[int] = []
    for symbol in mol.symbols:
        z = _ATOMIC_NUMBER.get(symbol)
        if z is None:
            raise EngineFailure("ENGINE_UNSUPPORTED_INPUT", f"unknown element symbol '{symbol}'")
        numbers.append(z)
    if len(mol.geometry) != 3 * len(numbers):
        raise EngineFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            f"geometry must be a flat 3N vector; got {len(mol.geometry)} values "
            f"for {len(numbers)} atoms — atom ordering must follow `symbols`",
        )
    coords = list(mol.geometry)
    for c in coords:
        if not math.isfinite(c):
            raise EngineFailure(
                "ENGINE_UNSUPPORTED_INPUT", "geometry contains a non-finite coordinate"
            )
    bohr = [c if mol.units == "bohr" else c * ANGSTROM_TO_BOHR for c in coords]
    if max(abs(c) for c in bohr) > _MAX_COORD_BOHR:
        raise EngineFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            f"coordinate magnitude exceeds {_MAX_COORD_BOHR} bohr — check units",
        )
    # Coincident atoms are a structural error, not a convergence risk.
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            dx = bohr[3 * i] - bohr[3 * j]
            dy = bohr[3 * i + 1] - bohr[3 * j + 1]
            dz = bohr[3 * i + 2] - bohr[3 * j + 2]
            if dx * dx + dy * dy + dz * dz < 1e-12:
                raise EngineFailure(
                    "ENGINE_UNSUPPORTED_INPUT",
                    f"atoms {i} and {j} coincide — geometry is degenerate",
                )
    electrons = sum(numbers) - mol.charge
    if electrons <= _MAX_CHARGED_ELECTRONS_DEFICIT:
        raise EngineFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            f"charge {mol.charge} leaves {electrons} electrons — impossible",
        )
    unpaired = mol.multiplicity - 1
    if unpaired > electrons or (electrons - unpaired) % 2 != 0:
        raise EngineFailure(
            "ENGINE_UNSUPPORTED_INPUT",
            f"multiplicity {mol.multiplicity} is incompatible with "
            f"{electrons} electrons (parity/count)",
        )
    return numbers


def build_atomic_input(spec: QuantumJobSpec) -> dict[str, Any]:
    """Construct the QCSchema v1 AtomicInput payload — the exact bytes
    persisted to the vault before execution and consumed inside the
    isolated worker. Geometry is QCSchema-native bohr."""
    validate_molecule(spec)
    mol = spec.molecule
    bohr = [c if mol.units == "bohr" else c * ANGSTROM_TO_BOHR for c in mol.geometry]
    support = program_support(spec.program)
    model: dict[str, Any] = {"method": canonical_method(spec)}
    if support and support["needs_basis"]:
        model["basis"] = spec.basis
    molecule: dict[str, Any] = {
        "schema_name": "qcschema_molecule",
        "schema_version": 2,
        "symbols": list(mol.symbols),
        "geometry": bohr,
        "molecular_charge": mol.charge,
        "molecular_multiplicity": mol.multiplicity,
        "provenance": {
            "creator": f"chemistry-studio {spec.program}-adapter",
            "routine": "engine_adapter_qcengine.contracts",
            "version": "1.0.0",  # PEP 440; adapter id lives in extras.studio
        },
    }
    if mol.name:
        molecule["name"] = mol.name
    return {
        "schema_name": "qcschema_input",
        "schema_version": 1,
        "molecule": molecule,
        "driver": spec.driver,
        "model": model,
        "keywords": dict(spec.keywords),
        "protocols": {"stdout": True},
        "extras": {
            "studio": {
                "adapter_version": ADAPTER_VERSION,
                "geometry_provenance": spec.molecule.provenance.model_dump(mode="json"),
            }
        },
    }


# ------------------------------------------------------------------
# Result classification (AT-0701-2): exit-0 + malformed/nonconverged
# output is NOT a scientific success.
# ------------------------------------------------------------------


def _finite_tree(value: Any) -> bool:
    if hasattr(value, "tolist"):
        return _finite_tree(value.tolist())
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, (list, tuple)):
        return all(_finite_tree(v) for v in value)
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    return value is None


def _to_jsonable(value: Any) -> Any:
    """Convert engine outputs (numpy arrays) into plain data without
    importing numpy here."""
    if hasattr(value, "tolist"):
        return _to_jsonable(value.tolist())
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def classify_result(*, program: str, driver: str, result: dict[str, Any]) -> dict[str, Any]:
    """Classify a parsed AtomicResult-shaped dict. The engine's own
    ``success`` flag is necessary but NOT sufficient: required outputs
    must exist and be finite."""
    if result.get("success") is not True:
        err = result.get("error") or {}
        return {
            "usable": False,
            "converged": False,
            "classification": "engine_failure",
            "error": {
                "code": "ENGINE_FAILURE",
                "message": str(err.get("error_message", "engine reported failure"))[:400],
            },
        }
    properties = result.get("properties") or {}
    return_result = result.get("return_result")
    required_ok = True
    if driver == "energy":
        energy = properties.get("return_energy")
        required_ok = (
            isinstance(energy, (int, float))
            and not isinstance(energy, bool)
            and math.isfinite(energy)
        )
    elif driver == "gradient":
        rr_list = (
            return_result.tolist()
            if return_result is not None and hasattr(return_result, "tolist")
            else return_result
        )
        required_ok = isinstance(rr_list, (list, tuple)) and _finite_tree(rr_list)
    if not required_ok:
        return {
            "usable": False,
            "converged": None,
            "classification": "malformed_result",
            "error": {
                "code": "ENGINE_MALFORMED_OUTPUT",
                "message": f"exit-0 result is missing a finite '{driver}' output",
            },
        }
    # Engines that expose a convergence flag get one; xtb has none —
    # a returned SCC energy is converged by construction, a failed one
    # never reaches this branch.
    converged = bool(result.get("success"))
    return {
        "usable": True,
        "converged": converged,
        "classification": "reference_integration",
        "error": None,
    }
