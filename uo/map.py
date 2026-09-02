"""The Felucca loader and the classic .mul writers and reader.

Arrays are indexed [x, y]. Statics are structured arrays with fields
(id, x, y, z, hue) and ABSOLUTE tile coordinates; on disk they are stored per
8 x 8 block with block-relative x and y (STATIC_DT).

File layouts (the classic, pre-UOP map format every server and tool reads):
- map0.mul: one 196-byte record per 8 x 8 block, blocks column-major
  (block index = bx * 512 + by), a 4-byte header then 64 cells of
  (land id u16, z i8) in row-major order within the block.
- staidx0.mul: per block (start u32, length u32, unused u32); start 0xFFFFFFFF
  means no statics.
- statics0.mul: 7-byte records (id u16, x u8, y u8, z i8, hue u16).
"""
import os, numpy as np
from .uomap import MapFile, load_radarcol
from .tiledata import UO

STATIC_DT = np.dtype([("id", "<u2"), ("x", "u1"), ("y", "u1"), ("z", "i1"), ("hue", "<u2")])
W, H = 7168, 4096
BW, BH = 896, 512

def load_felucca(cache_dir=None):
    """The client's Felucca (map0LegacyMUL.uop + staidx0/statics0.mul from UO_CLIENT_DIR).
    Returns (land_id[x, y] uint16, land_z[x, y] int8, statics with absolute x, y).
    With `cache_dir`, the decoded arrays are stored as felucca.npz there and reused."""
    if cache_dir:
        p = os.path.join(cache_dir, "felucca.npz")
        if os.path.exists(p):
            z = np.load(p)
            return z["id"], z["z"], z["st"]
    mf = MapFile.open_felucca(UO)
    # statics: gather every block with absolute coordinates
    idx = mf._staidx.reshape(-1, 3)
    starts, lens = idx[:, 0], idx[:, 1]
    ok = (starts != 0xFFFFFFFF) & (lens > 0) & (lens < 0x7FFFFFFF)
    bis = np.flatnonzero(ok)
    parts = []
    buf = np.frombuffer(mf._statics, dtype=np.uint8)
    for bi in bis:
        s, l = int(starts[bi]), int(lens[bi]) - int(lens[bi]) % 7
        if l <= 0: continue
        rec = buf[s:s+l].view(STATIC_DT)
        bx, by = divmod(int(bi), BH)
        out = np.empty(len(rec), dtype=[("id", "<u2"), ("x", "<u2"), ("y", "<u2"), ("z", "i1"), ("hue", "<u2")])
        out["id"] = rec["id"]; out["x"] = rec["x"].astype(np.uint16) + bx*8
        out["y"] = rec["y"].astype(np.uint16) + by*8; out["z"] = rec["z"]; out["hue"] = rec["hue"]
        parts.append(out)
    st = np.concatenate(parts)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        np.savez(os.path.join(cache_dir, "felucca.npz"), id=mf.land_id, z=mf.land_z, st=st)
    return mf.land_id, mf.land_z, st

def write_map_mul(path, land_id, land_z):
    """Write a classic map0.mul from land_id/land_z indexed [x, y] (column-major 196-byte blocks)."""
    w, h = land_id.shape
    bw, bh = w // 8, h // 8
    ids = land_id.reshape(bw, 8, bh, 8).transpose(0, 2, 3, 1).reshape(bw*bh, 64)  # [block][cy*8+cx]
    zs = land_z.reshape(bw, 8, bh, 8).transpose(0, 2, 3, 1).reshape(bw*bh, 64)
    blk = np.zeros((bw*bh, 196), np.uint8)
    blk[:, 4::3] = ids & 0xFF
    blk[:, 5::3] = ids >> 8
    blk[:, 6::3] = zs.astype(np.int8).view(np.uint8)
    blk.tofile(path)

def write_statics(idx_path, mul_path, st, bw=BW, bh=BH):
    """Write staidx/statics .mul files from a statics array with absolute x, y. The
    records are sorted into blocks (stable, so the input order within a block holds)."""
    bx = st["x"] // 8; by = st["y"] // 8
    bi = bx.astype(np.int64) * bh + by
    order = np.argsort(bi, kind="stable")
    st = st[order]; bi = bi[order]
    rec = np.empty(len(st), dtype=STATIC_DT)
    rec["id"] = st["id"]; rec["x"] = (st["x"] % 8).astype(np.uint8); rec["y"] = (st["y"] % 8).astype(np.uint8)
    rec["z"] = st["z"]; rec["hue"] = st["hue"]
    counts = np.bincount(bi, minlength=bw*bh)
    offsets = np.concatenate([[0], np.cumsum(counts)[:-1]])
    idx = np.zeros((bw*bh, 3), np.uint32)
    idx[:, 0] = np.where(counts > 0, offsets * 7, 0xFFFFFFFF)
    idx[:, 1] = counts * 7
    idx[:, 2] = 0
    idx.tofile(idx_path)
    rec.tofile(mul_path)

def load_mul(map_path, staidx_path, statics_path, bw=BW, bh=BH):
    """Load a classic (non-UOP) map + statics set. Returns (land_id[x,y], land_z[x,y], statics)."""
    raw = np.fromfile(map_path, dtype=np.uint8)
    n = bw * bh
    raw = raw[: n * 196].reshape(n, 196)
    cells = raw[:, 4:].reshape(n, 64, 3)
    ids = cells[:, :, 0].astype(np.uint16) | (cells[:, :, 1].astype(np.uint16) << 8)
    z = cells[:, :, 2].copy().view(np.int8)
    ids = ids.reshape(bw, bh, 8, 8).transpose(0, 3, 1, 2).reshape(bw * 8, bh * 8)
    z = z.reshape(bw, bh, 8, 8).transpose(0, 3, 1, 2).reshape(bw * 8, bh * 8)
    idx = np.fromfile(staidx_path, dtype=np.uint32).reshape(-1, 3)
    buf = np.fromfile(statics_path, dtype=np.uint8)
    parts = []
    for bi in np.flatnonzero((idx[:, 0] != 0xFFFFFFFF) & (idx[:, 1] > 0)):
        s, l = int(idx[bi, 0]), int(idx[bi, 1]) - int(idx[bi, 1]) % 7
        if l <= 0 or s + l > len(buf): continue
        rec = buf[s:s + l].view(STATIC_DT)
        bx, by = divmod(int(bi), bh)
        out = np.empty(len(rec), dtype=[("id", "<u2"), ("x", "<u2"), ("y", "<u2"), ("z", "i1"), ("hue", "<u2")])
        out["id"] = rec["id"]; out["x"] = rec["x"].astype(np.uint16) + bx * 8
        out["y"] = rec["y"].astype(np.uint16) + by * 8; out["z"] = rec["z"]; out["hue"] = rec["hue"]
        parts.append(out)
    st = np.concatenate(parts) if parts else np.empty(0, dtype=[("id", "<u2"), ("x", "<u2"), ("y", "<u2"), ("z", "i1"), ("hue", "<u2")])
    return np.ascontiguousarray(ids), np.ascontiguousarray(z), st
