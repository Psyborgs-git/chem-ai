"""Export the committed GraphQL schema (§8.1: schema is generated from
backend definitions and committed for codegen + breaking-change checks).

Usage:
    export_schema.py            # write packages/contracts/schema.graphql
    export_schema.py --check    # exit 2 if the committed file drifts
"""

from __future__ import annotations

import sys
from pathlib import Path

from studio.api.graphql.schema import schema

DEST = Path("packages/contracts/schema.graphql")


def main() -> int:
    text = schema.as_str()
    if not text.endswith("\n"):
        text += "\n"
    if "--check" in sys.argv:
        if not DEST.exists() or DEST.read_text() != text:
            print(
                "schema drift: packages/contracts/schema.graphql differs "
                "from backend definitions; run `make schema-export`"
            )
            return 2
        print("schema.graphql is in sync with backend definitions")
        return 0
    DEST.write_text(text)
    print(f"wrote {DEST} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
