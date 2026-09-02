#!/usr/bin/env bash
# Build the Windows x86_64 release on a Linux host, using Wine to run Windows
# Python + PyInstaller. Wine only hosts the build; the frozen app runs natively
# on Windows. (On Windows itself, use build_windows.ps1 instead.)
#
# Requires Wine 10 or newer on the host (older Wine, e.g. the 9.x in the
# tobix/pywine container images, lacks ucrtbase complex-math exports such as
# crealf, and scipy 1.18 aborts on import). Verified with wine-11.0.
#
# Windows Python is fetched once from the python.org-published NuGet package
# (a full CPython, no installer to run) into .winbuild/, which also holds the
# dedicated WINEPREFIX. Delete .winbuild/ for a from-scratch build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$ROOT/.winbuild"
PYVER="3.12.10"
export WINEPREFIX="$BUILD/wineprefix"
export WINEDEBUG="${WINEDEBUG:--all}"

command -v wine >/dev/null || { echo "wine is required" >&2; exit 1; }

mkdir -p "$BUILD"
if [ ! -f "$BUILD/python/tools/python.exe" ]; then
  echo "Fetching Windows Python $PYVER (NuGet package)..."
  curl -sL -o "$BUILD/python.nupkg.zip" "https://www.nuget.org/api/v2/package/python/$PYVER"
  mkdir -p "$BUILD/python"
  unzip -qo "$BUILD/python.nupkg.zip" "tools/*" -d "$BUILD/python"
fi
WPY() { wine "$BUILD/python/tools/python.exe" "$@"; }

WPY -m ensurepip --default-pip >/dev/null 2>&1 || true
WPY -m pip install --disable-pip-version-check -q -r "$ROOT/requirements-build.txt"

# A rebuild must never destroy the user's generated worlds or settings that
# live inside the release folder - stash them and restore after the build.
KEEP="$(mktemp -d)"
OLD_RELEASE="$ROOT/release/MapGen-Portable-Windows-x86_64"
[ ! -d "$OLD_RELEASE/output" ] || mv "$OLD_RELEASE/output" "$KEEP/output"
[ ! -f "$OLD_RELEASE/portable-settings.json" ] || mv "$OLD_RELEASE/portable-settings.json" "$KEEP/"
rm -rf "$OLD_RELEASE"
mkdir -p "$ROOT/release"
cd "$ROOT"
WPY -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath ./release \
  --workpath "$BUILD/pyinstaller-work" \
  mapgen_portable.spec

RELEASE="$ROOT/release/MapGen-Portable-Windows-x86_64"
if [ -d "$KEEP/output" ]; then mv "$KEEP/output" "$RELEASE/output"; else mkdir -p "$RELEASE/output"; fi
[ ! -f "$KEEP/portable-settings.json" ] || mv "$KEEP/portable-settings.json" "$RELEASE/"
rmdir "$KEEP" 2>/dev/null || true
cp "$ROOT/README.md" "$RELEASE/README.txt"
cp "$ROOT/LICENSE" "$RELEASE/LICENSE.txt"
cp "$ROOT/THIRD-PARTY-NOTICES.md" "$RELEASE/THIRD-PARTY-NOTICES.txt"
(
  cd "$ROOT/release"
  sha256sum "MapGen-Portable-Windows-x86_64/MapGen.exe" > "MapGen-Portable-Windows-x86_64.sha256"
)

echo "Portable release: $RELEASE"
