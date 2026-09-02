"""Where things live on disk, for a source checkout and for the frozen app alike.

The app is portable: everything it needs sits next to the executable. Bundled
data (the transition tables, presets, the icon) is read from the resource root,
which PyInstaller unpacks to a temporary folder; everything the user creates -
portable-settings.json and the default output folder - goes to the application
root, the folder that holds the executable (or the repository root when run
from source).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def frozen() -> bool:
    """True inside a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """The folder holding the bundled data files (out/, presets/, assets/)."""
    if frozen():
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parents[1]


def application_root() -> Path:
    """The folder the user sees: beside the executable, or the repository root."""
    if frozen():
        return Path(sys.executable).resolve().parent
    return resource_root()


def settings_path() -> Path:
    return application_root() / "portable-settings.json"


def default_output_root() -> Path:
    return application_root() / "output"


def validate_uo_directory(path: str | os.PathLike[str]) -> tuple[bool, str]:
    """(ok, message) for a folder that should hold a client's tiledata.mul."""
    directory = Path(path).expanduser()
    tiledata = directory / "tiledata.mul"
    if not directory.is_dir():
        return False, "The selected UO directory does not exist."
    if not tiledata.is_file():
        return False, "The selected directory does not contain tiledata.mul."
    if tiledata.stat().st_size < 1_000_000:
        return False, "tiledata.mul is unexpectedly small or invalid."
    return True, ""


def load_settings() -> dict[str, Any]:
    """portable-settings.json as a dict; empty when missing or unreadable."""
    path = settings_path()
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_settings(value: dict[str, Any]) -> None:
    """Write portable-settings.json atomically (a temporary file, then a rename)."""
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def world_directory_names(
    seed: int, when: datetime | None = None
) -> tuple[str, str]:
    """(final name, partial name) for a world: seed_<seed>_<timestamp> and the hidden
    .<name>.partial it is written into first."""
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    base = f"seed_{seed}_{stamp}"
    return base, f".{base}.partial"


def unique_world_paths(
    output_root: Path, seed: int, when: datetime | None = None
) -> tuple[Path, Path]:
    """(final path, partial path) under output_root, with a _1, _2, ... suffix when the
    timestamped name is already taken."""
    final_name, partial_name = world_directory_names(seed, when)
    final = output_root / final_name
    partial = output_root / partial_name
    suffix = 1
    while final.exists() or partial.exists():
        final = output_root / f"{final_name}_{suffix}"
        partial = output_root / f"{partial_name}_{suffix}"
        suffix += 1
    return final, partial


def retain_cancelled_output(partial: Path, final: Path) -> Path | None:
    """Rename a cancelled run's partial folder to <final>.cancelled (with a numeric
    suffix if needed) and mark it with CANCELLED.txt. Returns the new path, or None
    when there was no partial folder."""
    if not partial.exists():
        return None
    cancelled = Path(str(final) + ".cancelled")
    suffix = 1
    while cancelled.exists():
        cancelled = Path(str(final) + f".cancelled_{suffix}")
        suffix += 1
    partial.replace(cancelled)
    (cancelled / "CANCELLED.txt").write_text(
        "Generation was cancelled by the user.\n", encoding="utf-8"
    )
    return cancelled
