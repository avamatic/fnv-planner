"""Guardrail: mechanics matrix docs must track audited mechanics keys."""

from __future__ import annotations

from pathlib import Path
import sys

from scripts.audit_mechanics_sources import MECHANICS_ROWS


MATRIX_DOC = Path("docs/MECHANICS_SOURCE_MATRIX.md")


def _extract_keys(doc: str) -> set[str]:
    start = "<!-- MECHANICS_MATRIX_KEYS_START -->"
    end = "<!-- MECHANICS_MATRIX_KEYS_END -->"
    if start not in doc or end not in doc:
        return set()
    segment = doc.split(start, 1)[1].split(end, 1)[0]
    keys: set[str] = set()
    for raw in segment.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        keys.add(line)
    return keys


def main() -> int:
    documented = _extract_keys(MATRIX_DOC.read_text())
    discovered = {mechanic for mechanic, _source, _key, _fallback in MECHANICS_ROWS}

    missing = sorted(discovered - documented)
    stale = sorted(documented - discovered)

    if missing:
        print("Undocumented mechanics keys in docs/MECHANICS_SOURCE_MATRIX.md:")
        for item in missing:
            print(f"  - {item}")
        print("Add missing keys inside MECHANICS_MATRIX_KEYS block.")
        return 1

    if stale:
        print("Stale mechanics keys in docs/MECHANICS_SOURCE_MATRIX.md:")
        for item in stale:
            print(f"  - {item}")
        print("Remove stale keys from MECHANICS_MATRIX_KEYS block.")
        return 1

    print("Mechanics matrix coverage check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
