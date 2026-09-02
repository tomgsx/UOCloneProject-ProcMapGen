#!/usr/bin/env bash
# Build the Linux x86_64 release into release/MapGen-Portable-Linux-x86_64/.
#
# PyInstaller runs inside a Debian 12 / Python 3.12 container (Podman), so the
# frozen app links against glibc 2.36 and runs on any distribution at least
# that new. Set MAPGEN_BUILD_IMAGE to use another image.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${MAPGEN_BUILD_IMAGE:-docker.io/library/python:3.12-slim-bookworm}"

# A rebuild must never destroy the user's generated worlds or settings that
# live inside the release folder - stash them and restore after the build.
KEEP="$(mktemp -d)"
OLD_RELEASE="$ROOT/release/MapGen-Portable-Linux-x86_64"
[ ! -d "$OLD_RELEASE/output" ] || mv "$OLD_RELEASE/output" "$KEEP/output"
[ ! -f "$OLD_RELEASE/portable-settings.json" ] || mv "$OLD_RELEASE/portable-settings.json" "$KEEP/"
rm -rf "$OLD_RELEASE"
mkdir -p "$ROOT/release"

podman run --rm \
  -v "$ROOT:/project:Z" \
  -w /project \
  "$IMAGE" \
  /bin/bash -lc '
    set -euo pipefail
    PY=python3
    apt-get update
    apt-get install -y --no-install-recommends \
      binutils \
      libdbus-1-3 \
      libegl1 \
      libfontconfig1 \
      libgl1 \
      libglib2.0-0 \
      libx11-6 \
      libxcb1 \
      libxkbcommon0
    rm -rf /var/lib/apt/lists/*
    "$PY" -m venv /tmp/mapgen-build
    /tmp/mapgen-build/bin/python -m pip install --disable-pip-version-check -r requirements-build.txt
    /tmp/mapgen-build/bin/pyinstaller \
      --noconfirm \
      --clean \
      --distpath /project/release \
      --workpath /tmp/mapgen-pyinstaller \
      /project/mapgen_portable.spec
  '

RELEASE="$ROOT/release/MapGen-Portable-Linux-x86_64"
if [ -d "$KEEP/output" ]; then mv "$KEEP/output" "$RELEASE/output"; else mkdir -p "$RELEASE/output"; fi
[ ! -f "$KEEP/portable-settings.json" ] || mv "$KEEP/portable-settings.json" "$RELEASE/"
rmdir "$KEEP" 2>/dev/null || true
cp "$ROOT/README.md" "$RELEASE/README.txt"
cp "$ROOT/LICENSE" "$RELEASE/LICENSE.txt"
cp "$ROOT/THIRD-PARTY-NOTICES.md" "$RELEASE/THIRD-PARTY-NOTICES.txt"
cp "$ROOT/assets/mapgen.svg" "$RELEASE/mapgen.svg"
cp "$ROOT/assets/mapgen.desktop" "$RELEASE/MapGen.desktop"
chmod +x "$RELEASE/MapGen"
(
  cd "$ROOT/release"
  sha256sum "MapGen-Portable-Linux-x86_64/MapGen" > "MapGen-Portable-Linux-x86_64.sha256"
)

echo "Portable release: $RELEASE"
