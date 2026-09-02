"""Turn the generator's stage log lines into a progress percentage.

gen/pipeline.py prints "[  12.3s] <stage>" when a stage starts. Each stage name
maps to the percentage reached when it begins (measured share of a full run),
and the value never moves backwards, so lines the table does not know leave the
bar where it is.
"""
from __future__ import annotations

import re


PHASE_PROGRESS = {
    "continent": 2,
    "rivers": 25,
    "towns/roads": 42,
    "material cleanup": 55,
    "tiles": 72,
    "water": 78,
    "bridges": 83,
    "statics": 87,
    "write": 94,
    "metrics": 98,
}

LOG_RE = re.compile(r"^\[\s*[\d.]+s\]\s*(.+)$")


def phase_progress(line: str, previous: int = 0) -> tuple[int, str | None]:
    """(progress after this line, stage name or None if the line starts no stage)."""
    match = LOG_RE.match(line.strip())
    if not match:
        return previous, None
    message = match.group(1).strip()
    phase = message.splitlines()[0]
    value = PHASE_PROGRESS.get(phase)
    return (max(previous, value), phase) if value is not None else (previous, None)
