"""Stage 4, land ids: give every tile a concrete land id from its material.

Input : material[x, y] (gen.materials codes) and the tables in out/transitions/
        (learned from Felucca, docs/transitions.md).
Output: land_id[x, y] uint16.

Two passes. assign_pure() picks a PURE VARIANT for every tile - one of the
interchangeable ids of its material, e.g. the four grass tiles 0x3-0x6, with
Felucca's frequencies. decode_corners() then replaces every tile that sits on a
material boundary with a TRANSITION PIECE from the pair's KIT.

The corner rule. A tile is drawn as a quad whose four corners are the tiles
U=(x, y) [own], R=(x+1, y), L=(x, y+1) and D=(x+1, y+1) - the same 2 x 2 block
that defines its corner heights. Every Ultima Online transition kit is a
marching-squares set over that block (verified on the art and on Felucca masks):
  one corner B      -> A-majority piece with a B spot at that corner       (e.g. sand 0x35, grass at U)
  two adjacent B    -> edge piece, B along that side: UR=N RD=E DL=S LU=W  (e.g. sand 0x3A, grass to the N)
  three corners B   -> B-majority piece with an A spot at the missing one  (e.g. 0x3B, grass with sand at R)
The PATTERN of a tile is the 4-bit set of corners holding material B (bits
U=1, R=2, D=4, L=8), and a kit is a table from pattern to candidate ids. Read
this way, map-diagonal boundaries decode into the alternating spot pieces
Britannia uses, which gives the soft scalloped edges of the original map.
"""
import json, numpy as np
from . import materials as M

U_, R_, D_, L_ = 1, 2, 4, 8          # corner bits
# Which material of a pair becomes B (the one whose corners are counted): the
# higher priority. Water and sand dominate everything, rock next, and grass is
# the universal background.
PRIORITY = {M.WATER: 10, M.LAKE: 10, M.SAND: 9, M.ROCK: 8, M.SNOW: 7, M.SWAMP: 6, M.SWAMP_RIM: 6, M.JUNGLE: 5,
            M.FOREST: 4, M.ROAD: 3, M.DIRT: 3, M.COBBLE: 3, M.GRASS: 1}

def _corner_kit(spot, edge, three):
    """Build a kit table from three dicts of ids: `spot` {corner letter: ids} (B at that
    corner only), `edge` {'N','E','S','W': ids} (B along that side) and `three`
    {missing-corner letter: ids} (B everywhere but that corner). Returns
    {pattern: (ids array, uniform probabilities)}."""
    c = {"U": U_, "R": R_, "D": D_, "L": L_}
    t = {}
    for k, v in spot.items(): t[c[k]] = v
    for k, v in edge.items(): t[{"N": U_ | R_, "E": R_ | D_, "S": D_ | L_, "W": L_ | U_}[k]] = v
    for k, v in three.items(): t[15 & ~c[k]] = v
    return {k: (np.array(v, np.uint16), np.full(len(v), 1.0 / len(v))) for k, v in t.items()}

# ---- hand-verified kits, keyed by the unordered pair (A, B): pattern bits = corners that are B
KITS = {
    (M.SAND, M.GRASS): _corner_kit({"U": [0x35], "R": [0x36], "D": [0x33], "L": [0x34]},
                                   {"N": [0x3A], "E": [0x37], "S": [0x39], "W": [0x38]},
                                   {"R": [0x3B], "L": [0x3C], "D": [0x3D], "U": [0x3E]}),
    (M.GRASS, M.FOREST): _corner_kit({"U": [0xD8], "D": [0xD9], "R": [0xDA], "L": [0xDB]},
                                     {"N": [0xC8, 0xC9], "W": [0xCB], "E": [0xCE, 0xCF], "S": [0xD1]},
                                     {"D": [0xD4], "U": [0xD5], "R": [0xD6], "L": [0xD7]}),
    (M.JUNGLE, M.GRASS): _corner_kit({"D": [0xBC], "L": [0xBD], "U": [0xBE], "R": [0xBF]},
                                     {"S": [0xB0], "W": [0xB3], "N": [0xB6], "E": [0xB9]},
                                     {"U": [0xC0], "R": [0xC1], "D": [0xC2], "L": [0xC3]}),
    (M.ROAD, M.GRASS): _corner_kit({"R": [0x7C], "D": [0x79], "L": [0x7B], "U": [0x7A]},
                                   {"N": [0x8B, 0x8C], "E": [0x87, 0x88], "S": [0x85, 0x86], "W": [0x89, 0x8A]},
                                   {"D": [0x7D], "L": [0x82], "U": [0x7E], "R": [0x83]}),
    (M.ROAD, M.SAND): _corner_kit({"R": [0x33F], "D": [0x33E], "L": [0x340], "U": [0x33D]},
                                  {"N": [0x335], "E": [0x337], "S": [0x338], "W": [0x336]},
                                  {"D": [0x33A], "L": [0x33C], "U": [0x339], "R": [0x33B]}),
    (M.ROAD, M.SNOW): _corner_kit({"U": [0x38D], "D": [0x38E], "R": [0x38F], "L": [0x390]},
                                  {"N": [0x385], "E": [0x387], "S": [0x388], "W": [0x386]},
                                  {"L": [0x38C], "U": [0x389], "R": [0x38B], "D": [0x38A]}),
    # rock kits (A = rock, B = the other material; pattern = corners that are B), learned
    # from Felucca's 8-neighbour classes
    (M.ROCK, M.GRASS): _corner_kit({"D": [0x235], "L": [0x236], "U": [0x237], "R": [0x238]},
                                   {"N": [0x239], "E": [0x23A], "S": [0x23B], "W": [0x23C]},
                                   {"D": [0x231], "L": [0x232], "U": [0x233], "R": [0x234]}),
    (M.ROCK, M.SAND): _corner_kit({"D": [0x122], "L": [0x123], "U": [0x124], "R": [0x125]},
                                  {"W": [0x126], "N": [0x127], "E": [0x128], "S": [0x129]},
                                  {"U": [0x7BD], "D": [0x7BE], "R": [0x7BF], "L": [0x7C0]}),
    (M.ROCK, M.SNOW): _corner_kit({"D": [0x110], "L": [0x111], "U": [0x112], "R": [0x113]},
                                  {"N": [0x114], "E": [0x115], "S": [0x116], "W": [0x117]},
                                  {"D": [0x10C], "L": [0x10D], "U": [0x10E], "R": [0x10F]}),
    (M.ROCK, M.FOREST): _corner_kit({"D": [0xF4], "L": [0xF5], "U": [0xF6], "R": [0xF7]},
                                    {"S": [0xEC], "W": [0xED], "N": [0xEE], "E": [0xEF]},
                                    {"R": [0xF0], "D": [0xF1], "L": [0xF2], "U": [0xF3]}),
    (M.ROCK, M.JUNGLE): _corner_kit({"L": [0x104], "U": [0x105], "R": [0x106], "D": [0x107]},
                                    {"S": [0xFC], "W": [0xFD], "N": [0xFE], "E": [0xFF]},
                                    {"R": [0x100], "D": [0x101], "L": [0x102], "U": [0x103]}),
    (M.ROCK, M.ROAD): _corner_kit({"D": [0xE4], "L": [0xE5], "U": [0xE6], "R": [0xE7]},
                                  {"W": [0xDC], "N": [0xDD], "E": [0xDE], "S": [0xDF]},
                                  {"R": [0xE0], "D": [0xE1], "L": [0xE2], "U": [0xE3]}),
    # swamp: the dark core (0x3DE9-0x3DEC) meets its lighter rim (0x3DED-0x3DF0) through the
    # mid-tone ring pieces, and the rim meets grass through the swamp-grass pieces
    (M.SWAMP_RIM, M.SWAMP): _corner_kit({"U": [0x3DDC], "D": [0x3DE8]},
                                        {"W": [0x3DDB], "E": [0x3DDE, 0x3DDD], "S": [0x3DDF], "N": [0x3DE2, 0x3DE1, 0x3DE0]},
                                        {"R": [0x3DE3], "L": [0x3DE4], "U": [0x3DE5], "D": [0x3DE6]}),
    (M.GRASS, M.SWAMP_RIM): _corner_kit({"L": [0x3DD5], "D": [0x3DD6], "R": [0x3DD7], "U": [0x3DD8]},
                                        {"W": [0x3DC4], "S": [0x3DC5, 0x3DC6], "N": [0x3DC7, 0x3DC8], "E": [0x3DC9, 0x3DCA]},
                                        {"R": [0x3DCF], "D": [0x3DD1], "L": [0x3DD2], "U": [0x3DD3]}),
}
# dirt (town plazas) uses the road kits: both are the same dark dirt art
for (a, b), v in list(KITS.items()):
    if a == M.ROAD: KITS[(M.DIRT, b)] = v
    if b == M.ROAD: KITS[(a, M.DIRT)] = v

# The learned tables (docs/transitions.md) name a piece by its class; this maps a
# class to the corner pattern of the kit table.
CLASS_TO_PATTERN = {"B_edge_N": U_ | R_, "B_edge_E": R_ | D_, "B_edge_S": D_ | L_, "B_edge_W": L_ | U_,
                    "B_diag_U": U_, "B_diag_R": R_, "B_diag_D": D_, "B_diag_L": L_,
                    "B_L_NE": U_ | R_ | D_, "B_L_SE": R_ | D_ | L_, "B_L_SW": D_ | L_ | U_, "B_L_NW": L_ | U_ | R_}

class Kits:
    """The kit tables and pure-variant tables: the hand-verified KITS above plus every
    pair the learned transition table (`trans_path`) describes with a canonical kit,
    and the pure variants (`pure_path`) with Felucca's frequencies. Learned pieces
    rarer than `min_p` are dropped."""
    def __init__(self, trans_path, pure_path, min_p=0.08):
        self.kits = dict(KITS)
        raw = json.load(open(trans_path))
        for key, v in raw.items():
            a, b = key.split("->")
            if a not in M.CODES or b not in M.CODES: continue
            A, B = M.CODES[a], M.CODES[b]
            if (A, B) in self.kits or (B, A) in self.kits: continue
            if M.ROCK in (A, B) or M.SAND in (A, B): continue   # hand-coded above, or no real kit in UO
            if v.get("band_side") != a: continue
            can = v.get("canonical_from_band_side")
            if not can: continue
            t = {}
            for k, lst in can.items():
                cls = k.split("(")[0]
                if cls not in CLASS_TO_PATTERN: continue
                ents = [(int(i, 16), p) for i, p in lst if i != "n" and p >= min_p]
                if not ents: continue
                ids = np.array([i for i, _ in ents], np.uint16); p = np.array([q for _, q in ents], float)
                t[CLASS_TO_PATTERN[cls]] = (ids, p / p.sum())
            if t: self.kits[(A, B)] = t
        pv = json.load(open(pure_path))
        self.pure = {}
        for name, v in pv.items():
            if name not in M.CODES: continue
            ents = [(int(i, 16), c) for i, c, *rest in v["ids"] if rest and rest[1] in ("pure", "road", "floor") and c > 0]
            if not ents: continue
            ids = np.array([i for i, _ in ents], np.uint16); c = np.array([q for _, q in ents], float)
            keep = c / c.sum() >= 0.02
            self.pure[M.CODES[name]] = (ids[keep], c[keep] / c[keep].sum())
        self.pure[M.ROAD] = (np.array([0x75, 0x76, 0x77, 0x78], np.uint16), np.full(4, 0.25))
        self.pure[M.DIRT] = self.pure[M.ROAD]
        self.pure[M.SWAMP] = (np.array([0x3DE9, 0x3DEA, 0x3DEB, 0x3DEC], np.uint16), np.full(4, 0.25))
        self.pure[M.SWAMP_RIM] = (np.array([0x3DED, 0x3DEE, 0x3DEF, 0x3DF0], np.uint16), np.full(4, 0.25))

    def pure_ids(self, mat):
        """(ids, probabilities) of a material's pure variants, from the learned table or
        the fallback list in gen.materials."""
        if mat in self.pure: return self.pure[mat]
        ids = np.array(M.PURE_FALLBACK[mat], np.uint16); return ids, np.full(len(ids), 1.0 / len(ids))

    def kit(self, a, b):
        """Returns (table, flipped): table keyed by pattern of B corners. flipped=True if the stored kit is (b,a)."""
        if (a, b) in self.kits: return self.kits[(a, b)], False
        if (b, a) in self.kits: return self.kits[(b, a)], True
        return None, False


def assign_pure(material, kits: Kits, rng):
    """A pure variant for every tile of every material. Returns land_id[x, y] uint16."""
    land_id = np.zeros(material.shape, np.uint16)
    for mat in np.unique(material):
        m = material == mat
        ids, p = kits.pure_ids(int(mat))
        land_id[m] = rng.choice(ids, size=int(m.sum()), p=p)
    return land_id


def decode_corners(material, land_id, kits: Kits, rng, skip=(M.WATER, M.LAKE)):
    """Corner-rule transition decoding: every tile whose quad corners hold two materials
    takes a piece from the pair's kit. Tiles touching a `skip` material are left alone
    (the shoreline stage handles water). Returns (land_id, stats, unkitted): stats maps
    each pair to (boundary tiles, tiles that received a piece), unkitted counts the
    boundary tiles of pairs that have no kit at all."""
    W, H = material.shape
    own = material
    cr = np.empty_like(own); cr[:-1] = own[1:]; cr[-1] = own[-1]
    cl = np.empty_like(own); cl[:, :-1] = own[:, 1:]; cl[:, -1] = own[:, -1]
    cd = np.empty_like(own); cd[:-1, :-1] = own[1:, 1:]; cd[-1] = cr[-1]; cd[:, -1] = cl[:, -1]
    corners = [own, cr, cd, cl]   # bits U=1 R=2 D=4 L=8
    mixed = (cr != own) | (cl != own) | (cd != own)
    for s in skip: mixed &= (own != s) & (cr != s) & (cl != s) & (cd != s)
    idx = np.flatnonzero(mixed)
    if len(idx) == 0: return land_id, {}, {}
    stats = {}; unk = {}
    vals = np.stack([c.ravel()[idx] for c in corners], 1)   # (n,4)
    # choose the pair: A = own material, B = the highest-priority other material among the corners
    pri = np.vectorize(lambda m: PRIORITY.get(int(m), 2))(vals)
    others = np.where(vals != vals[:, :1], pri, -1)
    bsel = others.argmax(1)
    B = vals[np.arange(len(idx)), bsel]; A = vals[:, 0]
    isB = (vals == B[:, None])
    pattern = (isB[:, 0] * U_ + isB[:, 1] * R_ + isB[:, 2] * D_ + isB[:, 3] * L_).astype(np.int16)
    out = land_id.ravel()
    for a in np.unique(A):
        for b in np.unique(B[A == a]):
            sel = (A == a) & (B == b)
            table, flipped = kits.kit(int(a), int(b))
            if table is None:
                unk[(int(a), int(b))] = unk.get((int(a), int(b)), 0) + int(sel.sum()); continue
            pats = pattern[sel]
            if flipped: pats = 15 - pats      # the table is keyed by corners of the stored B (= our a)
            tile_idx = idx[sel]; used = 0
            for pat in np.unique(pats):
                r = table.get(int(pat))
                m = pats == pat
                if r is None:
                    nb = bin(int(pat)).count("1")
                    if nb == 3:      # three corners of the other material and no piece in UO -> pure other material
                        bmat = int(a) if flipped else int(b)
                        ids_b, p_b = kits.pure_ids(bmat)
                        out[tile_idx[m]] = rng.choice(ids_b, size=int(m.sum()), p=p_b); used += int(m.sum())
                    continue   # saddles and missing single pieces keep the pure own tile
                ids, p = r
                out[tile_idx[m]] = rng.choice(ids, size=int(m.sum()), p=p); used += int(m.sum())
            stats[(int(a), int(b))] = (int(sel.sum()), used)
    return out.reshape(W, H), stats, unk
