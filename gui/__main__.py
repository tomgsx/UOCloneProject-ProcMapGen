"""Launch the desktop application: python3 -m gui"""
import multiprocessing


def main() -> int:
    multiprocessing.freeze_support()
    from gui.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
