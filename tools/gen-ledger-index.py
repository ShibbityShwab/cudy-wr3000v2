#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "mem-entries.md"
OUT = ROOT / "mem-entries-INDEX.md"

HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
PHASE = re.compile(r"(?i)\bphase\s*([0-9]+[a-z]*)")


def clean(text: str) -> str:
    return text.replace("|", "\\|").strip()


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    rows: list[tuple[str, str, str, int]] = []
    for number, line in enumerate(lines, 1):
        match = HEADING.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        if title.upper().startswith("CURRENT TRUTHS"):
            continue
        date = DATE.search(title)
        phase = PHASE.search(title)
        rows.append(
            (
                date.group(1) if date else "",
                phase.group(1) if phase else "",
                title,
                number,
            )
        )

    dated = [row for row in rows if row[0]]
    latest = dated[-40:]

    out = [
        "# mem-entries index",
        "",
        "Generated from `mem-entries.md` by `tools/gen-ledger-index.py`. Do not hand-edit.",
        "",
        "The latest dated entry wins. Read the latest table first, then grep the ledger for the phase you need.",
        "",
        "## Latest 40 dated entries",
        "",
        "| date | phase | title | line |",
        "| --- | --- | --- | --- |",
    ]
    for date, phase, title, number in latest:
        out.append(f"| {date} | {phase} | {clean(title)} | `mem-entries.md:{number}` |")

    out += [
        "",
        "## All dated entries",
        "",
        "| date | phase | title | line |",
        "| --- | --- | --- | --- |",
    ]
    for date, phase, title, number in dated:
        out.append(f"| {date} | {phase} | {clean(title)} | `mem-entries.md:{number}` |")

    out.append("")
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} with {len(dated)} dated entries")


if __name__ == "__main__":
    main()
