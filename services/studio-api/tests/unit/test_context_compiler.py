"""CS-0304 unit tests — token-budgeted context manifest compiler.

AT-0304-3  over budget → hard constraints remain; omissions disclosed
"""

from __future__ import annotations

from studio.domain.tasks.memory import (
    ManifestItem,
    compile_manifest,
    estimate_tokens,
)


class TestEstimateTokens:
    def test_deterministic_approximation(self) -> None:
        assert estimate_tokens("") == 1
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcde") == 2
        assert estimate_tokens("x" * 400) == 100


class TestCompileManifest:
    """AT-0304-3: when context exceeds capacity the compiler selects —
    pinned constraints are never evicted and every omission is
    disclosed with its kind and ref id."""

    def test_hard_constraints_survive_and_omissions_disclosed(self) -> None:
        pinned = ManifestItem("constraint", "c1", "hard constraint: keep pH < 9", pinned=True)
        items = [
            pinned,
            ManifestItem("contract", "r1", "contract rev 1 " + "x" * 40),
            ManifestItem("evidence", "e1", "claim about viscosity " + "y" * 40),
            ManifestItem("evidence", "e2", "claim about pH " + "z" * 40),
        ]
        budget = pinned.tokens + items[1].tokens + items[2].tokens  # e2 won't fit
        selected, omitted, over = compile_manifest(items, budget)

        assert over is False
        kinds = [i.kind for i in selected]
        assert "constraint" in kinds and "contract" in kinds
        assert selected[0] is pinned
        assert [i.ref_id for i in omitted] == ["e2"]

    def test_pinned_exceeding_budget_kept_and_flagged(self) -> None:
        big = ManifestItem("warning", "w1", "safety warning " + "s" * 400, pinned=True)
        selected, omitted, over = compile_manifest([big, ManifestItem("history", "h1", "x")], 10)
        assert selected == [big]  # never evicted, even over budget
        assert over is True
        assert len(omitted) == 1

    def test_items_never_truncated(self) -> None:
        text = "quantity: 5.0 g/L " + "q" * 200
        item = ManifestItem("evidence", "e9", text)
        selected, omitted, _ = compile_manifest([item], item.tokens - 1)
        assert selected == []
        assert omitted == [item]  # dropped whole, never split mid-unit

        selected2, _, _ = compile_manifest([item], item.tokens)
        assert selected2[0].text == text
