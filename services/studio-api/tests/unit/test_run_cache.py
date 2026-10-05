"""CS-0403 unit tests — content-addressed run cache keys (§13.5).

AT-0403-3  same molecule, changed method/temperature/policy → the old
           result is never served: the key covers the full context.
"""

from __future__ import annotations

from workers.common.cache import build_context, cache_key

BASE = dict(
    canonical_input={"smiles": "CCO", "mol_revision": 3},
    chemical_context={"representation": "smiles", "version": "r1"},
    engine_id="rdkit",
    engine_version="2024.09.1",
    adapter_version="a1",
    method="xtb-gfn2",
    parameters={"temperature_K": 298.15, "solvent": "none"},
    precision="double",
    seed=42,
    policy_version="p9",
    scope="ws-1",
)


def _k(**over):
    return cache_key(build_context(**{**BASE, **over}))


def test_identical_context_same_key() -> None:
    assert _k() == _k()


def test_temperature_change_misses() -> None:
    assert _k() != _k(parameters={"temperature_K": 310.0, "solvent": "none"})


def test_method_change_misses() -> None:
    assert _k() != _k(method="psi4-b3lyp")


def test_policy_change_misses() -> None:
    assert _k() != _k(policy_version="p10")


def test_precision_and_seed_change_misses() -> None:
    assert _k() != _k(precision="single")
    assert _k() != _k(seed=43)


def test_engine_and_adapter_version_misses() -> None:
    assert _k() != _k(engine_version="2024.09.2")
    assert _k() != _k(adapter_version="a2")


def test_basis_and_descriptor_misses() -> None:
    """A changed formula basis or lot-dependent descriptor is a new
    context — an old incompatible result cannot be served."""
    assert _k() != _k(canonical_input={"smiles": "CCO", "mol_revision": 4})
    assert _k() != _k(chemical_context={"representation": "smiles", "version": "r2"})


def test_scope_isolation() -> None:
    assert _k() != _k(scope="ws-2")


def test_field_ordering_stable() -> None:
    """Dict order must not affect the digest."""
    p1 = {"temperature_K": 298.15, "solvent": "none"}
    p2 = {"solvent": "none", "temperature_K": 298.15}
    assert _k(parameters=p1) == _k(parameters=p2)
