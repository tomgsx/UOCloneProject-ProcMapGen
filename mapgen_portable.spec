# PyInstaller spec shared by every release build (build_linux.sh, build_windows.ps1,
# build_windows_from_linux.sh). The release folder name follows the platform the
# spec runs on; the frozen app is a "onedir" bundle: MapGen[.exe] plus _internal/
# holding Python, the libraries and the data files listed in `datas`.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


root = Path(SPECPATH)
platform_tag = "Windows" if sys.platform.startswith("win") else "Linux"
release_name = f"MapGen-Portable-{platform_tag}-x86_64"
datas = [
    (str(root / "out" / "transitions"), "out/transitions"),
    (str(root / "out" / "vegetation-props" / "props.json"), "out/vegetation-props"),
    (str(root / "presets"), "presets"),
    (str(root / "assets"), "assets"),
    (str(root / "README.md"), "."),
    (str(root / "LICENSE"), "."),
    (str(root / "THIRD-PARTY-NOTICES.md"), "."),
]

binaries = []
hiddenimports = []
for package in ("scipy",):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

analysis = Analysis(
    ["mapgen_portable.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)

# --- Qt plugins, by hand, when PyInstaller's Qt hook could not query Qt ---
# PyInstaller learns where PySide6 keeps its plugins by importing PySide6.QtCore in
# a child process. Under Wine that import fails (Qt6Core.dll needs Windows' own
# icuuc.dll, which Wine does not provide), the hook logs "failed to obtain Qt
# library info" and collects no plugins, and the frozen app then dies on Windows
# with "no Qt platform plugin could be initialized". PyInstaller's run-time hook
# still points QT_PLUGIN_PATH at PySide6/plugins, so placing the plugin DLLs there
# ourselves is enough. On a native build the hook works and this block does nothing.
import importlib.util

_win = sys.platform.startswith("win")
_pyside_dir = Path(importlib.util.find_spec("PySide6").submodule_search_locations[0])
_plugins_src = _pyside_dir / "plugins" if _win else _pyside_dir / "Qt" / "plugins"
_plugins_dst = "PySide6/plugins" if _win else "PySide6/Qt/plugins"
_have_platforms = any(
    dest.replace("\\", "/").startswith(_plugins_dst + "/platforms/") for dest, _src, _kind in analysis.binaries
)
if not _have_platforms and _plugins_src.is_dir():
    print(f"mapgen_portable.spec: Qt hook collected no plugins; collecting them from {_plugins_src}")
    for _sub in ("platforms", "styles", "imageformats", "iconengines", "generic",
                 "platformthemes", "platforminputcontexts", "accessiblebridge"):
        _dir = _plugins_src / _sub
        if not _dir.is_dir():
            continue
        for _file in sorted(_dir.iterdir()):
            if _file.suffix.lower() in (".dll", ".so", ".dylib"):
                analysis.binaries.append((f"{_plugins_dst}/{_sub}/{_file.name}", str(_file), "BINARY"))
    # libraries the plugins need that a working hook would have added (the svg
    # icon engine needs Qt6Svg; the rest are Qt's optional Windows GL backends)
    _bundled = {Path(dest).name.lower() for dest, _src, _kind in analysis.binaries}
    for _extra in ("Qt6Svg.dll", "d3dcompiler_47.dll", "opengl32sw.dll", "libEGL.dll", "libGLESv2.dll"):
        _path = _pyside_dir / _extra
        if _path.is_file() and _extra.lower() not in _bundled:
            analysis.binaries.append((f"PySide6/{_extra}", str(_path), "BINARY"))

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MapGen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name=release_name,
)
