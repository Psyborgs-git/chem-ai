"""Relay transport/cache boundary check (§8.2, AT-0104-3).

Static rules over apps/studio-web/src:
- `network.ts` is the only file that may touch /graphql or call fetch
  for GraphQL transport.
- `environment.ts` is the only file that may create a Relay
  Environment.
- No second server-state cache: no react-query/swr/apollo imports.
- No browser-storage persistence of Relay/server state.

Exit 2 with findings; these are the §8.2 invariants, not style.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path("apps/studio-web/src")
NETWORK = SRC / "relay" / "network.ts"
ENVIRONMENT = SRC / "relay" / "environment.ts"

FILES = sorted(
    p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx"} and "__generated__" not in str(p)
)

RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "graphql-transport",
        re.compile(r"fetch\(|/graphql|XMLHttpRequest|graphql-request|useSubscription\s*\("),
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
    "graphql-transport": {NETWORK},
    "environment": {ENVIRONMENT},
    "server-cache": set(),
    "persist": set(),
}


def main() -> int:
    findings: list[str] = []
    for path in FILES:
        text = path.read_text()
        for rule, pattern, why in RULES:
            if path in EXEMPTIONS[rule]:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    findings.append(f"{path}:{i}: {why}: {line.strip()[:80]}")
    if findings:
        print("Relay boundary violations (§8.2):")
        for f in findings:
            print(f"  {f}")
        return 2
    print(f"relay boundaries clean ({len(FILES)} files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
