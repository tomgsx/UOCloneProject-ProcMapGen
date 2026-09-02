"""Exact-preserving parallel drop-ins for the scipy.ndimage calls the generator makes.

Every function here must return BYTE-IDENTICAL results to the scipy call it replaces;
parallelism may never change the generated world. The gate is the seed-7 release run:
map0/staidx0/statics0.mul SHA256 must match VERIFICATION.md before any change ships.

Three mechanisms, each exact by construction:
- Binary morphology is tiled into row bands with a halo of the structuring-element
  radius: a kept output row depends only on input rows within that radius, so the
  band result equals the global result away from the cut edges we discard.
  Opening/closing compose two exact passes.
- The Euclidean distance transform's squared distances are integers with a unique
  minimum, so any exact-EDT implementation produces the same values; the multithreaded
  `edt` package (Felzenszwalb) replaces scipy's single-threaded transform, and
  sqrt-of-the-same-integer in float64 is bit-deterministic. Calls that need nearest-
  feature INDICES keep scipy: equidistant ties are implementation-defined there.
- gaussian_filter is a separable convolution: bands with a kernel-radius halo sum the
  same taps in the same order for every kept row.

Anything with kwargs these wrappers don't model falls straight through to scipy.
Every other scipy.ndimage name (label, binary_fill_holes, distance_transform_cdt, ...)
delegates via module __getattr__, so `from . import accel as ndimage` is a drop-in.

The worker count is every logical CPU unless the MAPGEN_THREADS environment
variable caps it. Output never depends on it.
"""
import os
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from scipy import ndimage as _nd

try:
    import edt as _edt
except ImportError:          # pure-scipy fallback keeps the build runnable
    _edt = None

_MIN_PAR = 1 << 20           # arrays below ~1M cells aren't worth the thread overhead
_F32_EXACT = 2 ** 24         # largest integer float32 holds exactly


def thread_count():
    """Worker threads: MAPGEN_THREADS when set to a positive integer, else all CPUs."""
    v = os.environ.get("MAPGEN_THREADS", "")
    if v.isdigit() and int(v) > 0:
        return int(v)
    return max(1, os.cpu_count() or 1)


_pool = None


def _executor():
    """The process-wide thread pool, created on first use."""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=thread_count(), thread_name_prefix="mapgen")
    return _pool


def _bands(n, k):
    """Split [0, n) into k contiguous (start, stop) row ranges."""
    step = -(-n // k)
    return [(i, min(i + step, n)) for i in range(0, n, step)]


def band_map(h, fn, min_band=256):
    """Run fn(y0, y1) for row bands of [0, h) in parallel; returns results in band order.

    fn must be a pure function of its row range (plus read-only closures) so that
    concatenating the bands equals computing the whole range at once.
    """
    nb = min(thread_count(), max(1, h // min_band))
    if nb <= 1:
        return [fn(0, h)]
    return list(_executor().map(lambda b: fn(b[0], b[1]), _bands(h, nb)))


def _tiled(op, a, halo, out_dtype):
    """Apply op to row bands with `halo` extra rows on each side; exact for ops whose
    output row depends only on input rows within `halo`."""
    h = a.shape[0]
    nb = min(thread_count(), max(1, h // max(256, 4 * halo)))
    if nb <= 1:
        return op(a)
    out = np.empty(a.shape, out_dtype)

    def work(band):
        y0, y1 = band
        lo = max(0, y0 - halo)
        hi = min(h, y1 + halo)
        out[y0:y1] = op(a[lo:hi])[y0 - lo: y0 - lo + (y1 - y0)]

    list(_executor().map(work, _bands(h, nb)))
    return out


def _square_structure(structure):
    """Radius of a centred all-ones structuring element, or None if not that shape."""
    if structure is None:
        return None
    s = np.asarray(structure)
    if s.ndim == 2 and s.shape[0] == s.shape[1] and s.shape[0] % 2 == 1 and s.all():
        return s.shape[0] // 2
    return None


def binary_dilation(input, structure=None, **kw):
    """scipy.ndimage.binary_dilation, banded when the structure is a square of ones."""
    a = np.asarray(input)
    r = _square_structure(structure)
    if kw or r is None or a.ndim != 2 or a.size < _MIN_PAR:
        return _nd.binary_dilation(input, structure, **kw)
    st = np.asarray(structure)
    return _tiled(lambda x: _nd.binary_dilation(x, st), a.astype(bool, copy=False), r, bool)


def binary_erosion(input, structure=None, **kw):
    """scipy.ndimage.binary_erosion, banded when the structure is a square of ones."""
    a = np.asarray(input)
    r = _square_structure(structure)
    if kw or r is None or a.ndim != 2 or a.size < _MIN_PAR:
        return _nd.binary_erosion(input, structure, **kw)
    st = np.asarray(structure)
    return _tiled(lambda x: _nd.binary_erosion(x, st), a.astype(bool, copy=False), r, bool)


def binary_opening(input, structure=None, **kw):
    """scipy.ndimage.binary_opening as an exact erosion then dilation."""
    a = np.asarray(input)
    r = _square_structure(structure)
    if kw or r is None or a.ndim != 2 or a.size < _MIN_PAR:
        return _nd.binary_opening(input, structure, **kw)
    return binary_dilation(binary_erosion(a, structure), structure)


def binary_closing(input, structure=None, **kw):
    """scipy.ndimage.binary_closing as an exact dilation then erosion."""
    a = np.asarray(input)
    r = _square_structure(structure)
    if kw or r is None or a.ndim != 2 or a.size < _MIN_PAR:
        return _nd.binary_closing(input, structure, **kw)
    return binary_erosion(binary_dilation(a, structure), structure)


def gaussian_filter(input, sigma, **kw):
    """scipy.ndimage.gaussian_filter, banded with a kernel-radius halo for a scalar sigma."""
    a = np.asarray(input)
    if kw or not np.isscalar(sigma) or a.ndim != 2 or a.size < _MIN_PAR:
        return _nd.gaussian_filter(input, sigma, **kw)
    halo = int(4.0 * float(sigma) + 0.5) + 1     # scipy default truncate=4.0
    return _tiled(lambda x: _nd.gaussian_filter(x, sigma), a, halo, a.dtype)


def _plain_sampling(sampling):
    """True when `sampling` means unit spacing along every axis."""
    if sampling is None:
        return True
    s = np.atleast_1d(sampling)
    return bool(np.all(s == 1))


def distance_transform_edt(input, sampling=None, return_distances=True,
                           return_indices=False, distances=None, indices=None):
    """scipy.ndimage.distance_transform_edt; the distances-only, unit-sampling case goes
    through the multithreaded edt package, everything else through scipy."""
    if (_edt is None or return_indices or not return_distances
            or distances is not None or indices is not None
            or not _plain_sampling(sampling)):
        return _nd.distance_transform_edt(
            input, sampling=sampling, return_distances=return_distances,
            return_indices=return_indices, distances=distances, indices=indices)
    a = np.ascontiguousarray(np.asarray(input) != 0)
    sq = _edt.edtsq(a, parallel=thread_count())
    # squared distances are exact integers; if they outgrow float32's exact range the
    # fast path can no longer promise bit equality, so take scipy instead
    if sq.dtype != np.float64 and a.size and float(sq.max()) >= _F32_EXACT:
        return _nd.distance_transform_edt(input)
    return np.sqrt(sq.astype(np.float64, copy=False))


def nearest_indices(fg, read_mask, pad=4, max_reach=96, block=512):
    """scipy's distance_transform_edt(fg, return_indices=True), computed only where it
    will be read.

    Valid wherever read_mask is set; other positions hold in-bounds but unspecified
    indices, so a caller must gather values through the result ONLY at read positions.
    Exactness rests on two verified facts: every read tile's nearest background lies
    within its measured distance (so a crop with that halo sees every candidate), and
    scipy's tie-breaking is translation-invariant (verified with zero index mismatches
    over 1.5 million localizable pixels of dense random masks), so the crop picks the
    same feature the full transform would. Reads farther than max_reach fall back to
    the full transform.
    """
    fgb = np.ascontiguousarray(np.asarray(fg) != 0)
    reads = np.asarray(read_mask, bool)
    full = lambda: np.array(_nd.distance_transform_edt(
        fgb, return_distances=False, return_indices=True))
    if _edt is None or fgb.ndim != 2 or not reads.any():
        return full()
    sq = _edt.edtsq(fgb, parallel=thread_count())
    reach = float(np.sqrt(sq[reads].max()))
    if reach > max_reach:
        return full()
    halo = int(np.ceil(reach)) + pad
    h, w = fgb.shape
    out = np.empty((2, h, w), np.int32)
    out[0] = np.arange(h, dtype=np.int32)[:, None]
    out[1] = np.arange(w, dtype=np.int32)[None, :]
    tasks = [(y0, min(y0 + block, h), x0, min(x0 + block, w))
             for y0 in range(0, h, block) for x0 in range(0, w, block)]
    tasks = [t for t in tasks if reads[t[0]:t[1], t[2]:t[3]].any()]

    def work(t):
        y0, y1, x0, x1 = t
        ly, hy = max(0, y0 - halo), min(h, y1 + halo)
        lx, hx = max(0, x0 - halo), min(w, x1 + halo)
        idx = _nd.distance_transform_edt(fgb[ly:hy, lx:hx],
                                         return_distances=False, return_indices=True)
        out[0, y0:y1, x0:x1] = idx[0][y0 - ly:y1 - ly, x0 - lx:x1 - lx] + ly
        out[1, y0:y1, x0:x1] = idx[1][y0 - ly:y1 - ly, x0 - lx:x1 - lx] + lx

    list(_executor().map(work, tasks))
    return out


def __getattr__(name):
    """Every other scipy.ndimage name, unchanged."""
    return getattr(_nd, name)
