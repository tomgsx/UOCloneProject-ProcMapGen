"""UOP archive and map readers.

A .uop file is a "MYP" container: a header, then a linked list of blocks of
entries (offset, header length, compressed and uncompressed length, a 64-bit
hash of the entry's name, an Adler checksum, a compression flag). Entries are
looked up by hashing their virtual file name, e.g. build/map0legacymul/00000000.dat,
with the hash function below (Bob Jenkins' lookup3, as every open-source UO tool
implements it). The map itself is the classic 196-byte-block format split into
chunks inside the archive.
"""
import struct, zlib, numpy as np

M32 = 0xFFFFFFFF
def _rol(x, k): return ((x << k) | (x >> (32 - k))) & M32

def hash_filename(name: str) -> int:
    """The 64-bit UOP entry hash of a virtual file name."""
    n = [ord(ch) for ch in name]
    length = len(n)
    a = b = c = (0xDEADBEEF + length) & M32
    i = 0
    while length - i > 12:
        a = (a + (n[i] | (n[i+1] << 8) | (n[i+2] << 16) | (n[i+3] << 24))) & M32
        b = (b + (n[i+4] | (n[i+5] << 8) | (n[i+6] << 16) | (n[i+7] << 24))) & M32
        c = (c + (n[i+8] | (n[i+9] << 8) | (n[i+10] << 16) | (n[i+11] << 24))) & M32
        a = (a - c) & M32; a ^= _rol(c, 4);  c = (c + b) & M32
        b = (b - a) & M32; b ^= _rol(a, 6);  a = (a + c) & M32
        c = (c - b) & M32; c ^= _rol(b, 8);  b = (b + a) & M32
        a = (a - c) & M32; a ^= _rol(c, 16); c = (c + b) & M32
        b = (b - a) & M32; b ^= _rol(a, 19); a = (a + c) & M32
        c = (c - b) & M32; c ^= _rol(b, 4);  b = (b + a) & M32
        i += 12
    rem = length - i
    if rem > 0:
        if rem >= 12: c = (c + (n[i+11] << 24)) & M32
        if rem >= 11: c = (c + (n[i+10] << 16)) & M32
        if rem >= 10: c = (c + (n[i+9] << 8)) & M32
        if rem >= 9:  c = (c + n[i+8]) & M32
        if rem >= 8:  b = (b + (n[i+7] << 24)) & M32
        if rem >= 7:  b = (b + (n[i+6] << 16)) & M32
        if rem >= 6:  b = (b + (n[i+5] << 8)) & M32
        if rem >= 5:  b = (b + n[i+4]) & M32
        if rem >= 4:  a = (a + (n[i+3] << 24)) & M32
        if rem >= 3:  a = (a + (n[i+2] << 16)) & M32
        if rem >= 2:  a = (a + (n[i+1] << 8)) & M32
        if rem >= 1:  a = (a + n[i]) & M32
        c ^= b; c = (c - _rol(b, 14)) & M32
        a ^= c; a = (a - _rol(c, 11)) & M32
        b ^= a; b = (b - _rol(a, 25)) & M32
        c ^= b; c = (c - _rol(b, 16)) & M32
        a ^= c; a = (a - _rol(c, 4)) & M32
        b ^= a; b = (b - _rol(a, 14)) & M32
        c ^= b; c = (c - _rol(b, 24)) & M32
    return ((b << 32) | c)


class UopArchive:
    """A .uop file read whole into memory, with its entry table indexed by name hash."""
    def __init__(self, path):
        self.path = path
        self.data = open(path, "rb").read()
        d = self.data
        magic, version, sig, next_block, capacity, count = struct.unpack_from("<IIIqII", d, 0)
        if magic != 0x0050594D:
            raise ValueError(f"{path}: not MYP (magic {magic:08x})")
        self.entries = {}
        while next_block != 0:
            cnt, nxt = struct.unpack_from("<Iq", d, next_block)
            off = next_block + 12
            for _ in range(cnt):
                offset, hlen, clen, dlen, fhash, adler, flag = struct.unpack_from("<qiiiQIh", d, off)
                off += 34
                if offset != 0:
                    self.entries[fhash] = (offset, hlen, clen, dlen, flag)
            next_block = nxt

    def get(self, name):
        """The entry tuple (offset, header length, compressed length, length, flag) for a
        virtual file name, or None."""
        return self.entries.get(hash_filename(name))

    def extract(self, name):
        """The bytes of an entry, inflated when it is compressed; None when absent."""
        e = self.get(name)
        if e is None: return None
        offset, hlen, clen, dlen, flag = e
        raw = self.data[offset + hlen: offset + hlen + clen]
        if flag == 0: return raw
        out = zlib.decompress(raw)
        if len(out) != dlen:
            raise ValueError(f"inflate produced {len(out)} of {dlen}")
        return out


BLOCK_SIZE = 196

class MapFile:
    """A map read from its .uop (land) plus staidx/statics .mul files (statics).
    Land is stored column-major: block index = bx * blocks_h + by. After loading,
    land_id[x, y] and land_z[x, y] hold the whole map."""
    def __init__(self, uop_path, uop_name, staidx_path, statics_path, blocks_w, blocks_h):
        self.blocks_w, self.blocks_h = blocks_w, blocks_h
        self.tiles_w, self.tiles_h = blocks_w * 8, blocks_h * 8
        uop = UopArchive(uop_path)
        chunks, i = [], 0
        while True:
            e = uop.get(f"build/{uop_name}/{i:08d}.dat")
            if e is None: break
            offset, hlen, clen, dlen, flag = e
            if flag != 0:
                raise NotImplementedError("compressed map chunks not supported")
            chunks.append(uop.data[offset + hlen: offset + hlen + clen])
            i += 1
        self.chunk_count = i
        stream = b"".join(chunks)
        self.stream_len = len(stream)
        expected = blocks_w * blocks_h * BLOCK_SIZE
        if self.stream_len < expected:
            raise ValueError(f"map stream {self.stream_len} < expected {expected}")
        self.expected = expected

        raw = np.frombuffer(stream[:expected], dtype=np.uint8).reshape(-1, BLOCK_SIZE)
        cells = raw[:, 4:].reshape(-1, 64, 3)
        ids = (cells[:, :, 0].astype(np.uint16) | (cells[:, :, 1].astype(np.uint16) << 8))
        z = cells[:, :, 2].copy().view(np.int8)
        # [block][cy*8+cx] -> [bx][by][cy][cx] -> [x][y]
        ids = ids.reshape(blocks_w, blocks_h, 8, 8).transpose(0, 3, 1, 2).reshape(self.tiles_w, self.tiles_h)
        z = z.reshape(blocks_w, blocks_h, 8, 8).transpose(0, 3, 1, 2).reshape(self.tiles_w, self.tiles_h)
        self.land_id = np.ascontiguousarray(ids)
        self.land_z = np.ascontiguousarray(z)

        self._staidx = np.frombuffer(open(staidx_path, "rb").read(), dtype=np.uint32)
        self._statics = open(statics_path, "rb").read()

    def statics_block(self, bx, by):
        """The static records of one 8 x 8 block, with block-relative x and y."""
        bi = bx * self.blocks_h + by
        start = int(self._staidx[bi * 3]); length = int(self._staidx[bi * 3 + 1])
        if start == 0xFFFFFFFF or length <= 0 or length > 0x7FFFFFFF:
            return np.empty(0, dtype=[("id", "<u2"), ("x", "u1"), ("y", "u1"), ("z", "i1"), ("hue", "<u2")])
        rec = self._statics[start:start + length]
        return np.frombuffer(rec, dtype=[("id", "<u2"), ("x", "u1"), ("y", "u1"), ("z", "i1"), ("hue", "<u2")])

    @staticmethod
    def open_felucca(client_dir):
        """Felucca (map 0, 896 x 512 blocks) from a client folder."""
        import os
        j = lambda f: os.path.join(client_dir, f)
        return MapFile(j("map0LegacyMUL.uop"), "map0legacymul", j("staidx0.mul"), j("statics0.mul"), 896, 512)


def load_radarcol(path):
    """radarcol.mul: the radar colour of every land and static id as an (n, 3) uint8 RGB array."""
    u = np.frombuffer(open(path, "rb").read(), dtype="<u2")
    r = ((u >> 10) & 31).astype(np.uint8) * 8
    g = ((u >> 5) & 31).astype(np.uint8) * 8
    b = (u & 31).astype(np.uint8) * 8
    return np.stack([r, g, b], axis=1)
