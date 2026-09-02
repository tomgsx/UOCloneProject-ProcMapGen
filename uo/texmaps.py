"""texmaps.mul / texidx.mul reader: the square RGB555 textures (64x64 or 128x128)
the client stretches over sloped land, indexed by a land tile's TexID."""
import numpy as np
from .tiledata import UO
from .art import _rgb555

class Texmaps:
    """Texture lookup by TexID from a client folder (default: UO_CLIENT_DIR), cached."""
    def __init__(self, client_dir=UO):
        self.idx = np.frombuffer(open(f"{client_dir}/texidx.mul", "rb").read(), dtype="<u4").reshape(-1, 3)
        self.data = open(f"{client_dir}/texmaps.mul", "rb").read()
        self._cache = {}
    def valid(self, texid):
        """True when the index has a texture for `texid`."""
        if texid >= len(self.idx): return False
        s, l, _ = self.idx[texid]
        return s != 0xFFFFFFFF and l > 0
    def get(self, texid):
        """Returns HxWx4 uint8 RGBA (rows top-down) or None."""
        if texid in self._cache: return self._cache[texid]
        tex = None
        if self.valid(texid):
            s, l, _ = (int(v) for v in self.idx[texid])
            n = int(round((l // 2) ** 0.5))
            if n * n * 2 == l and n in (64, 128):
                px = np.frombuffer(self.data, dtype="<u2", count=n*n, offset=s).reshape(n, n)
                tex = _rgb555(px)
        self._cache[texid] = tex
        return tex
