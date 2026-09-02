# Building the releases

A release is a self-contained folder under `release/` that end users run
without installing anything: `MapGen` (Linux) or `MapGen.exe` (Windows) plus
an `_internal/` folder holding Python, Qt, NumPy, SciPy, Pillow, the `edt`
library and the generator's data tables. All three build paths freeze the
same sources with the same `mapgen_portable.spec`, which picks the release
name from the platform it runs on.

| Build | Where you run it | Script | Result |
| --- | --- | --- | --- |
| Linux x86_64 | Linux with Podman | `./build_linux.sh` | `release/MapGen-Portable-Linux-x86_64/` |
| Windows x86_64, native | Windows with Python 3.12 | `build_windows.ps1` | `release/MapGen-Portable-Windows-x86_64/` |
| Windows x86_64, from Linux | Linux with Wine 10+ | `./build_windows_from_linux.sh` | `release/MapGen-Portable-Windows-x86_64/` |

Every script copies `README.md`, `LICENSE` and `THIRD-PARTY-NOTICES.md` into
the release folder as `.txt` files, creates an empty `output/` folder, and
writes a `.sha256` of the executable beside the folder. A rebuild keeps the
`output/` folder and `portable-settings.json` of the previous build.

## Linux (Podman)

```bash
./build_linux.sh
```

PyInstaller runs inside the `python:3.12-slim-bookworm` container image, so
the executable links against Debian 12's glibc 2.36 and runs on any
distribution at least that new (Debian 12, Ubuntu 24.04, Fedora 38 and
later). `MAPGEN_BUILD_IMAGE` overrides the image.

## Native Windows

1. Install **Python 3.12 from python.org** (not the Microsoft Store build)
   with the default "py launcher" option enabled.
2. Open PowerShell in the repository folder and run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
   ```

The script creates a private virtual environment under `.winbuild\`,
installs the pinned `requirements-build.txt` into it (every pin has a Windows
wheel, including `edt`), runs PyInstaller with the shared spec, and copies
the documents in. Delete `.winbuild\` to build from scratch; otherwise the
environment and pip's cache are reused.

The executable is not code-signed, so SmartScreen shows "Windows protected
your PC" the first time it runs: choose "More info", then "Run anyway".

## Windows from a Linux host (Wine)

```bash
./build_windows_from_linux.sh
```

Needs Wine **10 or newer** (verified with wine-11.0), `curl` and `unzip`.
Wine only hosts the build; the frozen app runs natively on Windows. The
script downloads the python.org NuGet package of CPython 3.12 (a plain zip,
no installer) into `.winbuild/`, creates a dedicated `WINEPREFIX` there,
installs the requirements with Windows `pip`, and runs Windows PyInstaller
under Wine. Delete `.winbuild/` for a from-scratch build.

Why not a container: the `tobix/pywine` images ship Wine 9.x, whose
`ucrtbase` lacks the C99 complex-math exports (`crealf` and friends), so SciPy
aborts on import and PyInstaller's isolated hook subprocess dies with exit
code 0x80000100. Host Wine 10+ imports SciPy cleanly.

**What Wine cannot do.** Qt6Core.dll depends on `icuuc.dll`, a Windows
system library that Wine does not provide, so `PySide6.QtCore` cannot be
imported under Wine at all. Two consequences:

- PyInstaller's Qt hook, which imports QtCore in a child process to learn
  where the plugins live, fails with "failed to obtain Qt library info" and
  collects no plugins. `mapgen_portable.spec` detects that and collects the
  plugin DLLs itself, so the bundle still gets `PySide6/plugins/platforms/
  qwindows.dll` and the rest; check that the folder is there after a Wine
  build.
- The GUI of a Wine-built app cannot be launched under Wine to test it (the
  headless `--headless-preview` and `--headless-world` modes work, because
  they never load Qt). A Wine build therefore needs one launch on a real
  Windows machine before it is published. The native build
  (`build_windows.ps1`, or the CI "Release build" job on a Windows runner)
  has neither limitation and is the build to prefer for a release.

## Verifying a build

The project's contract is that a given seed always produces byte-identical
MUL files (VERIFICATION.md). Check a release the same way:

```bash
# the tests against the working tree (no client files or display needed)
python3 -m unittest discover -s tests

# the frozen Linux app: a preview without client data, then a full world
cd release/MapGen-Portable-Linux-x86_64
./MapGen --headless-preview /tmp/preview.png
./MapGen --headless-world /tmp/world --uo-directory "/path/to/Ultima Online Classic"
sha256sum /tmp/world/*.mul          # must match VERIFICATION.md

# the frozen Windows app, natively (PowerShell) ...
.\MapGen.exe --headless-world C:\Temp\world --uo-directory "C:\Program Files (x86)\Ultima Online Classic"
Get-FileHash C:\Temp\world\*.mul

# ... or under the Linux build host's Wine
wine MapGen.exe --headless-world /tmp/winworld --uo-directory 'Z:\path\to\Ultima Online Classic'
sha256sum /tmp/winworld/*.mul
```

`--headless-preview` needs no client data; `--headless-world` needs a folder
containing `tiledata.mul` from a legally obtained client (the Classic Client,
https://uo.com/client-download/). `--headless-cancel-test <dir>` exercises
cancellation and succeeds when the retained `.cancelled` folder carries its
marker. `tools/verify_release.py --world <dir>` checks that a world folder
holds every expected file and, with `--baseline`, that its `metrics.json`
matches a reference.

## Development

```bash
./run_development.sh                              # the GUI from source (Linux)
run_development.cmd                               # the GUI from source (Windows)
python3 -m gen.pipeline --seed 7 --out /tmp/gen   # the generator alone; set UO_CLIENT_DIR for the metrics stage
MAPGEN_THREADS=4 python3 -m gen.pipeline ...      # cap the worker threads (default: every logical CPU)
```

The dependencies are pinned in `pyproject.toml`; `requirements-build.txt`
adds PyInstaller. See CONTRIBUTING.md for the tests and the gate every change
under `gen/` or `uo/` must pass.
