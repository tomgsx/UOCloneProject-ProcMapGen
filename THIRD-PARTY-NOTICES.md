# Third-party notices

MapGen is licensed under the GNU General Public License, version 3.0 only
(see `LICENSE`). The release folders bundle the following libraries, each
under its own license. Their license texts are in each library's package
under `_internal/` in a release folder, and at the upstream links below.

| Library | Version | License | Upstream |
| --- | --- | --- | --- |
| Python | 3.12 | Python Software Foundation License | https://www.python.org/ |
| NumPy | 2.4.6 | BSD-3-Clause (with 0BSD, MIT, Zlib and CC0-1.0 parts) | https://numpy.org/ |
| SciPy | 1.18.0 | BSD-3-Clause | https://scipy.org/ |
| Pillow | 12.3.0 | MIT-CMU | https://python-pillow.github.io/ |
| PySide6 and shiboken6 (Qt for Python) | 6.11.1 | LGPL-3.0-only (also offered under GPL-2.0 / GPL-3.0) | https://www.qt.io/qt-for-python |
| Qt (the C++ libraries the PySide6 wheels ship) | 6.11 | LGPL-3.0-only | https://www.qt.io/ |
| edt (euclidean-distance-transform-3d) | 3.1.2 | LGPL-3.0-or-later | https://github.com/seung-lab/euclidean-distance-transform-3d |

**LGPL libraries.** PySide6, shiboken6, Qt and edt are used unmodified. The
release builds are PyInstaller "onedir" bundles, so each of these libraries
stays a separate file under `_internal/` and can be replaced with another
build of the same library, as the LGPL requires. Their source code is
available from the upstream links above.

**Build tool.** The release folders are produced with PyInstaller 6.22.2
(GPL-2.0-or-later with the bootloader exception, https://pyinstaller.org/).
The exception allows the bootloader to be bundled with programs under any
license; PyInstaller places no requirement on the built application beyond
MapGen's own license.

## Data files

`out/transitions/*.json` and `out/vegetation-props/props.json` are tables of
tile ids, frequencies and offsets measured from the Ultima Online Felucca map.
They contain no art or map data and are covered by the project license.

MapGen bundles no Ultima Online client files. The application reads
`tiledata.mul` from an installation the user selects (a legally obtained
Classic Client, https://uo.com/client-download/), and the tools under
`tools/` read the client's art only to render a preview locally.

## Acknowledgements

The file-format and rendering knowledge in `uo/`, `tools/cedrender.py` and
`docs/render-spec.md` was learned from these open-source projects, whose code
is not copied here:

- **ClassicUO** (https://github.com/ClassicUO/ClassicUO): the art, texmap and
  hue loaders, the client's walking rule and land normals.
- **CentrED#** (https://github.com/kaczy93/centredsharp): the map editor
  whose rendering geometry the software renderer reproduces and in which the
  generated worlds are viewed and edited.
- **RunUO** (https://github.com/runuo/runuo) and **ServUO**
  (https://github.com/ServUO/ServUO): the server-side movement rule,
  `Map.GetAverageZ` and `TileData.CalcHeight`.
- **UOFiddler** (https://github.com/polserver/UOFiddler): reference for the
  MUL and UOP file layouts.
