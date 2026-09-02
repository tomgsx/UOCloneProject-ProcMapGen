"""UO art decoding: land tiles and static sprites from artLegacyMUL.uop.

The format follows the public loaders (ClassicUO's ArtLoader, UOFiddler):

Land   : a 44x44 diamond stored as raw RGB555 rows of 2, 4, .., 44, 44, .., 4, 2
         pixels, each row centred.
Static : 4-byte header, ushort width and height, a per-row lookup table of
         16-bit offsets, then per row a sequence of (xOffset, runLength) runs of
         RGB555 pixels ended by a (0, 0) pair. Colour 0 is transparent.
Both decode to an (H, W, 4) uint8 RGBA array with rows top-down.
"""
import struct, numpy as np
from .uomap import UopArchive

def _rgb555(buf):
    """RGB555 pixels (uint16 array) to RGBA uint8; colour 0 becomes transparent."""
    c = buf.astype(np.uint32)
    r = (c >> 10) & 0x1F; g = (c >> 5) & 0x1F; b = c & 0x1F
    out = np.zeros(c.shape + (4,), np.uint8)
    out[..., 0] = (r << 3) | (r >> 2)
    out[..., 1] = (g << 3) | (g >> 2)
    out[..., 2] = (b << 3) | (b >> 2)
    out[..., 3] = np.where(c == 0, 0, 255)
    return out

class ArtLoader:
    """Decodes land and static art on demand from artLegacyMUL.uop, with a cache."""
    def __init__(self, path):
        self.uop = UopArchive(path)
        self._land, self._static = {}, {}

    def land(self, tid):
        """The 44x44 RGBA diamond of land id `tid`, or None when the archive has no entry."""
        if tid in self._land: return self._land[tid]
        d = self.uop.extract(f"build/artlegacymul/{tid:08d}.tga")
        tex = None
        if d is not None and len(d) >= 2:
            SZ = 44
            tex = np.zeros((SZ, SZ, 4), np.uint8)
            pos = 0
            for y in range(SZ):
                w = (y + 1) * 2 if y < 22 else (SZ - y) * 2
                x0 = 22 - w // 2
                if pos + w*2 > len(d): break
                row = np.frombuffer(d, dtype="<u2", count=w, offset=pos); pos += w*2
                tex[y, x0:x0+w] = _rgb555(row)
        self._land[tid] = tex
        return tex

    def static(self, tid):
        """The RGBA sprite of static id `tid` (art index 0x4000 + tid), or None."""
        if tid in self._static: return self._static[tid]
        d = self.uop.extract(f"build/artlegacymul/{0x4000 + tid:08d}.tga")
        tex = None
        if d is not None and len(d) >= 8:
            w, h = struct.unpack_from("<HH", d, 4)
            if 0 < w <= 2048 and 0 < h <= 2048:
                tex = np.zeros((h, w, 4), np.uint8)
                lookup_base = 8
                pixel_base = lookup_base + h*2
                for y in range(h):
                    lut, = struct.unpack_from("<H", d, lookup_base + y*2)
                    pos = pixel_base + lut*2
                    x = 0
                    while pos + 4 <= len(d):
                        xoff, run = struct.unpack_from("<HH", d, pos); pos += 4
                        if xoff == 0 and run == 0: break
                        x += xoff
                        if run == 0 or pos + run*2 > len(d) or x + run > w: break
                        px = np.frombuffer(d, dtype="<u2", count=run, offset=pos); pos += run*2
                        tex[y, x:x+run] = _rgb555(px)
                        x += run
        self._static[tid] = tex
        return tex
