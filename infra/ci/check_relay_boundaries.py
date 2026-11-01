"""Relay transport/cache boundary check (§8.2, AT-0104-3).

Static rules over apps/studio-web/src:
- `network.ts` is the only file that may touch /graphql or call fetch
  for GraphQL transport.
- `environment.ts` is the only file that may create a Relay
  Environment.
- No second server-state cache: no react-query/swr/apollo imports.
- No browser-storage persistence of Relay/server state.
  Owner-scoped selected-thread IDs and unsent notebook drafts have narrow,
  explicitly reviewed exceptions; neither is a persisted server-state cache.

Exit 2 with findings; these are the §8.2 invariants, not style.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path("apps/studio-web/src")
AGENT_SIDEBAR = Path("features/agent/AgentSidebar.tsx")
NOTEBOOK_DRAFTS = Path("features/notebooks/drafts.ts")
TEST_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
NON_PRODUCTION_DIRS = {"__generated__", "__tests__", "__fixtures__", "__mocks__"}

RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "graphql-transport",
        # `refetch(` is the Relay pagination API, not raw transport —
        # exclude only that identifier, keep catching `fetch(` callers.
        re.compile(
            r"(?<!re)fetch\(|/graphql|XMLHttpRequest|graphql-request|useSubscription\s*\("
        ),
        "GraphQL transport outside relay/network.ts",
    ),
    (
        "environment",
        re.compile(r"new Environment\(|new RelayEnvironment\("),
        "Relay Environment created outside relay/environment.ts",
    ),
    (
        "server-cache",
        re.compile(
            r"react-query|@tanstack|useSWR|apollo-client|urql|"
            r"createStore\s*\(\s*\)\s*;?\s*//.*server"
        ),
        "second server-state cache library",
    ),
    (
        "persist",
        re.compile(r"localStorage|sessionStorage|indexedDB"),
        "browser-storage persistence of server state (§8.2)",
    ),
]

# Which files each rule is allowed in.
EXEMPTIONS: dict[str, set[Path]] = {
    "graphql-transport": {Path("relay/network.ts")},
    "environment": {Path("relay/environment.ts")},
    "server-cache": set(),
    "persist": set(),
}


def source_files(src: Path = SRC) -> list[Path]:
    """Only production TS/TSX participates in application boundary enforcement."""
    return sorted(
        path for path in src.rglob("*")
        if path.suffix in {".ts", ".tsx"}
        and not path.name.endswith(TEST_SUFFIXES)
        and not NON_PRODUCTION_DIRS.intersection(path.relative_to(src).parts)
    )


def _expression_pattern(expression: str) -> re.Pattern[str]:
    # Match a fixed token sequence, allowing formatting changes between tokens.
    # A qualified window.localStorage or another identifier must not inherit it.
    tokens = re.findall(r"[A-Za-z_$][\w$]*|\d+|[^\s]", expression)
    return re.compile(r"(?<![\w$.])" + r"\s*".join(map(re.escape, tokens)))


def _mask(text: str, expressions: tuple[str, ...]) -> str:
    for expression in expressions:
        text = _expression_pattern(expression).sub(
            lambda match: re.sub(r"[^\n]", " ", match.group()), text
        )
    return text


def persistence_source(relative: Path, text: str) -> str:
    """Keep every unreviewed storage token visible to the persistence rule."""
    if relative == AGENT_SIDEBAR and re.search(
        r"const\s+activeKey\s*=\s*\(\s*scope\s*:\s*string\s*\)\s*=>\s*"
        r"`studio\.agent\.activeThread:\$\{scope\}`\s*;", text
    ):
        # This UI preference contains one thread ID per workspace/owner scope.
        # No thread titles, messages, tool results or Relay records are allowed.
        return _mask(text, (
            "localStorage.getItem(activeKey(ownerScope))",
            "localStorage.setItem(activeKey(ownerScope), threadId)",
            "localStorage.removeItem(activeKey(ownerScope))",
        ))
    if relative == NOTEBOOK_DRAFTS and re.search(
        r'const\s+PREFIX\s*=\s*"chemistry-studio:private-notebook-draft:"\s*;', text
    ) and re.search(
        r"const\s+key\s*=\s*\(\s*ownerKey\s*:\s*string\s*,\s*pageId\s*:\s*string"
        r"\s*\)\s*=>\s*`\$\{PREFIX\}\$\{encodeURIComponent\(ownerKey\)\}:\$\{pageId\}`\s*;",
        text,
    ):
        # Unsent edits are recoverable in this tab's sessionStorage, keyed by
        # owner and page. This designated module is not a server-response cache;
        # clearing on sign-out must remain restricted to its own draft prefix.
        return _mask(text, (
            "sessionStorage.getItem(key(ownerKey, pageId))",
            "sessionStorage.setItem(key(ownerKey, pageId), JSON.stringify(value))",
            "sessionStorage.removeItem(key(ownerKey, pageId))",
            "for (let index = sessionStorage.length - 1; index >= 0; index--) { "
            "const name = sessionStorage.key(index); "
            "if (name?.startsWith(PREFIX)) sessionStorage.removeItem(name); }",
        ))
    return text


def check(src: Path = SRC) -> list[str]:
    findings: list[str] = []
    for path in source_files(src):
        relative = path.relative_to(src)
        text = path.read_text()
        for rule, pattern, why in RULES:
            if relative in EXEMPTIONS[rule]:
                continue
            scan = persistence_source(relative, text) if rule == "persist" else text
            for i, line in enumerate(scan.splitlines(), 1):
                if pattern.search(line):
                    original = text.splitlines()[i - 1]
                    findings.append(f"{path}:{i}: {why}: {original.strip()[:80]}")
    return findings


def main() -> int:
    findings = check()
    if findings:
        print("Relay boundary violations (§8.2):")
        for f in findings:
            print(f"  {f}")
        return 2
    print(f"relay boundaries clean ({len(source_files())} production files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
