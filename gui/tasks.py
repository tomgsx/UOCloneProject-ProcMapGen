"""Child-process entry points for previews and complete worlds.

Both tasks run in a process the window spawns (gui/app.py) and talk back only
through `queue`, as tuples: ("log", line), ("progress", percent),
("preview_done", png path), ("world_started", partial, final),
("world_done", folder) and ("error", traceback text). The frozen app's
--headless-* flags (mapgen_portable.py) call the same functions in-process.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
from queue import Empty
from typing import Any

from gui.config_io import config_dict, make_config


def config_fingerprint(value: dict[str, Any]) -> str:
    """A short hash of a settings dict, independent of key order; names the cached preview."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


class QueueLog:
    """A file-like sink that writes to generation.log and forwards each complete line
    to the queue as a log event. The generator prints through it."""
    def __init__(self, queue, file):
        self.queue = queue
        self.file = file
        self.buffer = ""

    def write(self, value: str) -> int:
        self.file.write(value)
        self.file.flush()
        self.buffer += value
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line:
                self.queue.put(("log", line))
        return len(value)

    def flush(self) -> None:
        self.file.flush()
        if self.buffer:
            self.queue.put(("log", self.buffer))
            self.buffer = ""


def preview_task(config_data: dict[str, Any], target: str, queue) -> None:
    """Render the overview of the macro stages only (continent, terrain, biomes) to
    `target`. Needs no UO data."""
    try:
        from gen import macro

        cfg = make_config(config_data)
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        queue.put(("log", "Building continent preview…"))
        queue.put(("progress", 10))
        land, _lake = macro.continent(cfg)
        queue.put(("log", "Classifying terrain…"))
        queue.put(("progress", 45))
        hilly, rock, _score = macro.terrain_classes(cfg, land)
        z = macro.terrace_dem(cfg, land, hilly, rock)
        queue.put(("log", "Painting preview biomes…"))
        queue.put(("progress", 75))
        material = macro.biomes(cfg, land, hilly, rock, z)
        macro.overview_png(material, z, str(target_path), 8)
        queue.put(("progress", 100))
        queue.put(("preview_done", str(target_path)))
    except BaseException:
        queue.put(("error", traceback.format_exc()))


def world_task(
    config_data: dict[str, Any],
    uo_directory: str,
    partial_path: str,
    final_path: str,
    queue,
) -> None:
    """Generate a complete world into `partial_path`, then rename it to `final_path`.
    The settings are saved as config.json and every log line as generation.log; on
    failure the partial folder stays, with FAILED.txt holding the traceback."""
    partial = Path(partial_path)
    final = Path(final_path)
    try:
        os.environ["UO_CLIENT_DIR"] = uo_directory
        partial.mkdir(parents=True, exist_ok=False)
        (partial / "config.json").write_text(
            json.dumps(config_data, indent=2), encoding="utf-8"
        )
        queue.put(("world_started", str(partial), str(final)))
        with (partial / "generation.log").open("w", encoding="utf-8") as log:
            stream = QueueLog(queue, log)
            with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                from gen.pipeline import run

                run(make_config(config_data), str(partial))
            stream.flush()
        partial.replace(final)
        queue.put(("progress", 100))
        queue.put(("world_done", str(final)))
    except BaseException:
        details = traceback.format_exc()
        try:
            partial.mkdir(parents=True, exist_ok=True)
            with (partial / "generation.log").open("a", encoding="utf-8") as log:
                log.write("\nGENERATION FAILED\n")
                log.write(details)
            (partial / "FAILED.txt").write_text(details, encoding="utf-8")
        except OSError:
            pass
        queue.put(("error", details))


def drain_queue(queue) -> list[tuple]:
    """Every event waiting in the queue, without blocking."""
    events = []
    while True:
        try:
            events.append(queue.get_nowait())
        except Empty:
            return events
