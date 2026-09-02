"""Seeded noise fields: Perlin gradient noise, fractal sums, ridges, domain warping.

All fields are float32 arrays of the requested `shape`, computed in row bands
in parallel (gen/accel.py band_map). Banding is exact because every value is a
pure function of its absolute lattice coordinate, so a band equals the same
slice of a whole-grid call and the thread count cannot change a world.

`wavelength` is in tiles: the distance over which the noise repeats its
character. `octaves` stacks finer copies, each `lacunarity` times higher in
frequency and `gain` times lower in amplitude.
"""
import numpy as np

def _grad_table(seed, n=256):
    """256 unit gradient vectors and a permutation, both drawn from `seed`."""
    rng = np.random.default_rng(seed)
    ang = rng.random(n) * 2 * np.pi
    return np.stack([np.cos(ang), np.sin(ang)], 1).astype(np.float32), rng.permutation(n).astype(np.int64)

def _perlin_rows(h0, h1, w, freq, seed, offset, g, perm):
    """Rows [h0, h1) of the full Perlin grid. Every operation is elementwise on absolute
    lattice coordinates, so a band equals the same slice of a whole-grid call."""
    ys = (np.arange(h0, h1, dtype=np.float32) + offset[0]) * freq
    xs = (np.arange(w, dtype=np.float32) + offset[1]) * freq
    Y, X = np.meshgrid(ys, xs, indexing="ij")
    yi = np.floor(Y).astype(np.int64); xi = np.floor(X).astype(np.int64)
    fy = Y - yi; fx = X - xi
    def hsh(a, b): return perm[(perm[a & 255] + (b & 255)) & 255]
    def dot(iy, ix, dy, dx):
        gi = g[hsh(iy, ix)]
        return gi[..., 0] * dx + gi[..., 1] * dy
    n00 = dot(yi, xi, fy, fx); n01 = dot(yi, xi + 1, fy, fx - 1)
    n10 = dot(yi + 1, xi, fy - 1, fx); n11 = dot(yi + 1, xi + 1, fy - 1, fx - 1)
    u = fx * fx * fx * (fx * (fx * 6 - 15) + 10); v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    nx0 = n00 + u * (n01 - n00); nx1 = n10 + u * (n11 - n10)
    return (nx0 + v * (nx1 - nx0)) * np.float32(1.41421356)

def perlin(shape, freq, seed, offset=(0.0, 0.0)):
    """2D Perlin noise in [-1, 1] on a grid of `shape`; `freq` = lattice cells per tile (1 / wavelength)."""
    h, w = shape
    g, perm = _grad_table(seed)
    from .accel import band_map
    return np.vstack(band_map(h, lambda y0, y1: _perlin_rows(y0, y1, w, freq, seed, offset, g, perm)))

def fbm(shape, seed, octaves=5, wavelength=256.0, lacunarity=2.0, gain=0.5, offset=(0.0, 0.0)):
    """Fractal Brownian motion: `octaves` Perlin layers summed and normalised, roughly in [-1, 1]."""
    out = np.zeros(shape, np.float32); amp = 1.0; freq = 1.0 / wavelength; norm = 0.0
    for o in range(octaves):
        out += amp * perlin(shape, freq, seed * 1000 + o, offset)
        norm += amp; amp *= gain; freq *= lacunarity
    return out / norm

def ridged(shape, seed, octaves=5, wavelength=256.0, lacunarity=2.0, gain=0.5):
    """Ridged multifractal in [0, 1] (1 along the ridges), used for mountain crests."""
    out = np.zeros(shape, np.float32); amp = 1.0; freq = 1.0 / wavelength; norm = 0.0; weight = 1.0
    for o in range(octaves):
        n = 1.0 - np.abs(perlin(shape, freq, seed * 1000 + 17 + o))
        n = n * n * weight
        weight = np.clip(n * 2.0, 0, 1)
        out += amp * n; norm += amp; amp *= gain; freq *= lacunarity
    return out / norm

def warp(shape, seed, strength=60.0, wavelength=400.0, octaves=3):
    """Domain-warp offsets (dy, dx) in tiles, each an fbm field scaled by `strength`."""
    return (fbm(shape, seed + 11, octaves, wavelength) * strength, fbm(shape, seed + 23, octaves, wavelength) * strength)

def sample_warped(field, dy, dx):
    """Bilinear sample of `field` at (y + dy, x + dx), clamped to the field."""
    h, w = field.shape
    def rows(r0, r1):
        Y, X = np.meshgrid(np.arange(r0, r1, dtype=np.float32), np.arange(w, dtype=np.float32), indexing="ij")
        Y = np.clip(Y + dy[r0:r1], 0, h - 1.001); X = np.clip(X + dx[r0:r1], 0, w - 1.001)
        y0 = Y.astype(np.int64); x0 = X.astype(np.int64); fy = Y - y0; fx = X - x0
        return (field[y0, x0] * (1 - fy) * (1 - fx) + field[y0, x0 + 1] * (1 - fy) * fx
                + field[y0 + 1, x0] * fy * (1 - fx) + field[y0 + 1, x0 + 1] * fy * fx)
    from .accel import band_map
    return np.vstack(band_map(h, rows))

def upsample(field, factor):
    """Bilinear upsample by an integer factor (scipy zoom, order 1)."""
    from scipy.ndimage import zoom
    return zoom(field, factor, order=1)
