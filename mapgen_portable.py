"""Entry point of the frozen app (mapgen_portable.spec), and its headless modes.

Without arguments it starts the desktop application. The flags below run the
same tasks without a window, which is how a release build is verified
(BUILDING.md):

    MapGen --headless-preview <png> [--seed N]
    MapGen --headless-world <dir> --uo-directory <client folder> [--seed N]
    MapGen --headless-cancel-test <dir> --uo-directory <client folder>

The cancel test starts a world in a child process, terminates it as soon as
the partial folder appears, and succeeds when the retained .cancelled folder
carries its CANCELLED.txt marker.
"""
from __future__ import annotations

import argparse
import multiprocessing
import queue
import time
from pathlib import Path


def _events(result_queue) -> list[tuple]:
    values = []
    while True:
        try:
            values.append(result_queue.get_nowait())
        except queue.Empty:
            return values


def main() -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--headless-preview")
    parser.add_argument("--headless-world")
    parser.add_argument("--headless-cancel-test")
    parser.add_argument("--uo-directory")
    parser.add_argument("--seed", type=int, default=7)
    options, _unknown = parser.parse_known_args()

    if options.headless_preview:
        from gen.config import Config
        from gui.config_io import config_dict
        from gui.tasks import preview_task

        result_queue = queue.Queue()
        preview_task(
            config_dict(Config(seed=options.seed)),
            options.headless_preview,
            result_queue,
        )
        return 0 if Path(options.headless_preview).is_file() else 1

    if options.headless_world:
        if not options.uo_directory:
            return 2
        from gen.config import Config
        from gui.config_io import config_dict
        from gui.tasks import world_task

        final = Path(options.headless_world)
        partial = Path(str(final) + ".partial")
        result_queue = queue.Queue()
        world_task(
            config_dict(Config(seed=options.seed)),
            options.uo_directory,
            str(partial),
            str(final),
            result_queue,
        )
        return 0 if (final / "metrics.json").is_file() else 1

    if options.headless_cancel_test:
        if not options.uo_directory:
            return 2
        from gen.config import Config
        from gui.config_io import config_dict
        from gui.paths import retain_cancelled_output
        from gui.tasks import world_task

        final = Path(options.headless_cancel_test)
        partial = Path(str(final) + ".partial")
        context = multiprocessing.get_context("spawn")
        result_queue = context.Queue()
        process = context.Process(
            target=world_task,
            args=(
                config_dict(Config(seed=options.seed)),
                options.uo_directory,
                str(partial),
                str(final),
                result_queue,
            ),
        )
        process.start()
        deadline = time.monotonic() + 30
        while not partial.exists() and process.is_alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
        cancelled = retain_cancelled_output(partial, final)
        return 0 if cancelled and (cancelled / "CANCELLED.txt").is_file() else 1

    from gui.__main__ import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
