"""Guardrail: hardcoded mechanics literals in derived_stats must be documented.

The machine-readable allowlist lives in docs/MECHANICS_SOURCE_MATRIX.md:

```text
<!-- HARD_CODED_LITERALS_ALLOWLIST_START -->
method:literal
...
<!-- HARD_CODED_LITERALS_ALLOWLIST_END -->
```
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys


DERIVED_STATS = Path("src/fnv_planner/models/derived_stats.py")
MATRIX_DOC = Path("docs/MECHANICS_SOURCE_MATRIX.md")


def _extract_allowlist(doc: str) -> set[str]:
    start = "<!-- HARD_CODED_LITERALS_ALLOWLIST_START -->"
    end = "<!-- HARD_CODED_LITERALS_ALLOWLIST_END -->"
    if start not in doc or end not in doc:
        return set()
    segment = doc.split(start, 1)[1].split(end, 1)[0]
    out: set[str] = set()
    for raw in segment.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line)
    return out


def _hardcoded_literals_in_derived_stats(source: str) -> set[str]:
    tree = ast.parse(source)
    entries: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        doc = ast.get_docstring(node) or ""
        if "No known GMST" not in doc:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)):
                if isinstance(child.value, bool):
                    continue
                entries.add(f"{node.name}:{child.value}")
    return entries


def main() -> int:
    derived_source = DERIVED_STATS.read_text()
    doc_source = MATRIX_DOC.read_text()

    discovered = _hardcoded_literals_in_derived_stats(derived_source)
    allowlist = _extract_allowlist(doc_source)

    missing = sorted(discovered - allowlist)
    stale = sorted(allowlist - discovered)

    if missing:
        print("Undocumented hardcoded literals detected in derived_stats.py:")
        for item in missing:
            print(f"  - {item}")
        print("Add each item to docs/MECHANICS_SOURCE_MATRIX.md allowlist block.")
        return 1

    if stale:
        print("Allowlist contains stale entries not present in derived_stats.py:")
        for item in stale:
            print(f"  - {item}")
        print("Remove stale items from docs/MECHANICS_SOURCE_MATRIX.md allowlist block.")
        return 1

    print("Hardcoded mechanics literal check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
