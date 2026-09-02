"""Ultima Online file formats: readers for the client's data files and writers for
the classic map and statics files.

Everything here reads the client install strictly read-only. The generator
itself needs only tiledata.mul (through uo.tiledata); the other readers serve
the rendering and analysis tools in tools/.

uomap    - UOP (MYP) container reader and the map0LegacyMUL.uop map loader
map      - load_felucca() cached loader, write_map_mul(), write_statics(), load_mul()
tiledata - TileData (land/static flags, names, TexID, heights) and the TileFlag bits
art      - ArtLoader: land 44x44 diamonds, static RLE sprites (RGBA uint8)
texmaps  - Texmaps: 64/128 px square textures used for sloped land

The formats are the ones every open-source UO tool shares; the layouts were
taken from the public loaders in ClassicUO (ClassicUO.Assets) and UOFiddler.
"""
