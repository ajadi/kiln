"""Series style anchor: does a new member of a series share the anchor's style vocabulary?

Normal Python (numpy, Pillow), run with Bash; the glb is parsed directly (glb_mesh.py).

  python style_anchor.py extract art/anchors/<series>/anchor.glb --views art/anchors/<series>/views --out art/anchors/<series>/style.json
  python style_anchor.py check art/anchors/<series>/style.json candidate.glb --views production/captures/<task>/views [--profile strict] [--same-class]
  python style_anchor.py calibrate art/anchors/<series>/style.json approved_a.glb approved_b.glb [--views dir_a dir_b]

Members of a series are meant to differ in silhouette and match in style (TF2's classes: one
shared language, distinct silhouettes). Style lives in element and part statistics, not in the
overall shape, so this compares statistics and never silhouette IoU against the anchor:
  tri_density        triangles per m2 of surface                 ratio <= 1.5           hard
  edge_sharpness     dihedral angles weighted by edge length     EMD <= 8 degrees       hard
  hard_edges         length share of edges >= 30 degrees        +-0.10                 soft
  part_sizes         connected parts by log10(size / object)    EMD <= 0.15 decades    soft
  planar             area share of flat regions (>= 1 % each)    +-0.10                 soft
  materials          material count                               <= anchor + 1         hard
  texel_density      median px/m of the base colour texture       +-15 %                hard
  palette            Lab k-means (k=5, black kept apart), CIEDE2000 matched by share
                                                                  dE <= 10 (strict 5)    soft (strict: hard)
  value              L* 5/50/95 percentiles of the colour views   +-8 L*                 soft
  solidity           silhouette area / convex hull area per view  +-0.06                 soft
  outline            perimeter^2 / (4 pi area) per view           +-25 %                 soft
  proportions        bounding box ratios (--same-class only)      +-15 %                 soft
Views (optional): PNGs with alpha at one fixed object height (silhouette_shot.py), a flat-lit
colour render per view; palette and value fall back to the base colour textures without them.
Every tolerance is a starting value (research 2026-10-19, UNVERIFIED): `calibrate` widens each
to max(default, 1.5 x the spread among members the art-director approved) and writes it into
style.json. Exit 1 when a hard metric fails; soft ones warn for the art-director's lineup review,
which stays the deciding gate.
"""

import argparse
import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glb_mesh import edges, face_areas, face_normals, load_mesh  # noqa: E402

EDGE_BINS = np.array([0, 10, 30, 60, 100, 180])
EDGE_CENTRES = np.array([5, 20, 45, 80, 140])
PART_BINS = np.array([-np.inf, -2.5, -2.0, -1.5, -1.0, -0.5, 0.01])
PART_CENTRES = np.array([-2.75, -2.25, -1.75, -1.25, -0.75, -0.25])
VIEW_HEIGHT = 512

# name: (how to compare, tolerance, kind)
DEFAULTS = {
    "tri_density": ("ratio", 1.5, "hard"),
    "edge_sharpness": ("emd_edges", 8.0, "hard"),
    "hard_edges": ("abs", 0.10, "soft"),
    "part_sizes": ("emd_parts", 0.15, "soft"),
    "planar": ("abs", 0.10, "soft"),
    "materials": ("over", 1, "hard"),
    "texel_density": ("ratio", 1.15, "hard"),
    "palette": ("palette", 10.0, "soft"),
    "value": ("abs_max", 8.0, "soft"),
    "solidity": ("abs", 0.06, "soft"),
    "outline": ("ratio", 1.25, "soft"),
    "proportions": ("ratio_max", 1.15, "soft"),
}


# --- geometry -----------------------------------------------------------------------------------

class Groups:
    """Union-find over integer ids."""

    def __init__(self, n):
        self.p = np.arange(n)

    def find(self, x):
        root = x
        while self.p[root] != root:
            root = self.p[root]
        while self.p[x] != root:
            self.p[x], x = root, self.p[x]
        return root

    def join_all(self, a, b):
        for x, y in zip(a.tolist(), b.tolist()):
            rx, ry = self.find(x), self.find(y)
            if rx != ry:
                self.p[rx] = ry

    def labels(self):
        return np.array([self.find(i) for i in range(len(self.p))])


def geometry(mesh):
    tris = mesh.tris
    area = face_areas(tris)
    total = float(area.sum()) or 1.0
    normals = face_normals(tris)
    pairs, counts, f0, f1, lengths, ids = edges(tris)
    inner = counts == 2
    cos = np.clip((normals[f0[inner]] * normals[f1[inner]]).sum(1), -1, 1)
    dihedral = np.degrees(np.arccos(cos))
    weights = lengths[inner]
    hist, _ = np.histogram(dihedral, EDGE_BINS, weights=weights)
    hist = hist / (hist.sum() or 1)
    hard = float(weights[dihedral >= 30].sum() / (weights.sum() or 1))
    # parts: faces joined through shared (welded) vertices
    nverts = int(ids.max()) + 1
    g = Groups(nverts)
    g.join_all(ids[:, 0], ids[:, 1])
    g.join_all(ids[:, 1], ids[:, 2])
    vlabel = g.labels()
    flabel = vlabel[ids[:, 0]]
    pts = tris.reshape(-1, 3)
    diag = float(np.linalg.norm(pts.max(0) - pts.min(0))) or 1.0
    sizes = []
    for lab in np.unique(flabel):
        p = tris[flabel == lab].reshape(-1, 3)
        sizes.append(np.linalg.norm(p.max(0) - p.min(0)) / diag)
    phist, _ = np.histogram(np.log10(np.maximum(sizes, 1e-6)), PART_BINS)
    phist = phist / (phist.sum() or 1)
    # planar regions: faces joined across edges flatter than 2 degrees
    fg = Groups(len(tris))
    flat = inner.copy()
    flat[inner] = dihedral < 2.0
    fg.join_all(f0[flat], f1[flat])
    region = fg.labels()
    region_area = np.bincount(region, weights=area)
    planar = float(region_area[region_area >= 0.01 * total].sum() / total)
    dims = pts.max(0) - pts.min(0)
    return {"tri_density": len(tris) / total, "edge_sharpness": hist.round(4).tolist(),
            "hard_edges": round(hard, 4), "part_sizes": phist.round(4).tolist(),
            "parts": len(sizes), "planar": round(planar, 4),
            "materials": len(mesh.materials) or 1,
            "texel_density": texel_density(mesh, area),
            "proportions": (np.sort(dims)[::-1] / (dims.max() or 1)).round(4).tolist(),
            "triangles": len(tris), "surface_m2": round(total, 4)}


def texel_density(mesh, area):
    if mesh.uvs is None:
        return None
    uv = mesh.uvs
    uv_area = 0.5 * np.abs(np.cross(uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]))
    values = []
    for mat in np.unique(mesh.material):
        size = mesh.texture_size(int(mat)) if mat >= 0 else None
        if not size:
            continue
        sel = (mesh.material == mat) & (area > 0)
        values.append(np.sqrt(uv_area[sel] * size[0] * size[1] / area[sel]))
    return round(float(np.median(np.concatenate(values))), 2) if values else None


# --- colour and views ---------------------------------------------------------------------------

def to_lab(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722],
                        [0.0193, 0.1192, 0.9505]]).T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def ciede2000(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    if C1p * C2p == 0:
        dh = 0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lpm, Cpm = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hpm = (h1p + h2p) / 2
    else:
        hpm = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    dtheta = 30 * np.exp(-((hpm - 275) / 25) ** 2)
    Rc = 2 * np.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cpm, 1 + 0.015 * Cpm * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return float(np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                         + Rt * (dCp / Sc) * (dHp / Sh)))


def palette(lab, k=5, iterations=20):
    """k Lab clusters with their shares; pixels darker than L* 15 go to a fixed black cluster
    so dark pixels do not pull the colour clusters."""
    dark = lab[:, 0] < 15
    out = []
    if dark.any():
        out.append({"lab": [0.0, 0.0, 0.0], "share": float(dark.mean()), "locked": True})
    rest = lab[~dark]
    if len(rest):
        order = np.argsort(rest[:, 0], kind="stable")
        centres = rest[order[np.linspace(0, len(rest) - 1, min(k, len(rest))).astype(int)]]
        for _ in range(iterations):                      # deterministic: seeded by L* quantiles
            d = ((rest[:, None, :] - centres[None]) ** 2).sum(2)
            lab_of = d.argmin(1)
            centres = np.array([rest[lab_of == i].mean(0) if (lab_of == i).any() else centres[i]
                                for i in range(len(centres))])
        share = np.bincount(lab_of, minlength=len(centres)) / len(lab)
        out += [{"lab": c.round(2).tolist(), "share": float(s)} for c, s in zip(centres, share) if s > 0]
    return out


def palette_distance(p, q):
    """Share-weighted CIEDE2000 under the best one-to-one match of the clusters."""
    if not p or not q:
        return None
    small, big = (p, q) if len(p) <= len(q) else (q, p)
    best = None
    for perm in itertools.permutations(range(len(big)), len(small)):
        cost = sum((s["share"] + big[j]["share"]) / 2 * ciede2000(s["lab"], big[j]["lab"])
                   for s, j in zip(small, perm))
        weight = sum((s["share"] + big[j]["share"]) / 2 for s, j in zip(small, perm)) or 1
        best = cost / weight if best is None else min(best, cost / weight)
    return round(best, 3)


def view_stats(folder):
    from PIL import Image
    names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".png"))
    solidity, outline, pixels = [], [], []
    for n in names:
        img = Image.open(os.path.join(folder, n)).convert("RGBA")
        arr = np.asarray(img)
        mask = arr[..., 3] >= 128
        ys, xs = np.nonzero(mask)
        if not len(xs):
            continue
        crop = Image.fromarray(arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
        w = max(1, round(crop.width * VIEW_HEIGHT / crop.height))
        crop = np.asarray(crop.resize((w, VIEW_HEIGHT), Image.NEAREST))
        m = crop[..., 3] >= 128
        a = m.sum()
        hull = hull_area(m)
        solidity.append(min(1.0, a / hull) if hull else 1.0)
        perim = np.count_nonzero(np.diff(np.pad(m, 1).astype(np.int8), axis=0)) + \
            np.count_nonzero(np.diff(np.pad(m, 1).astype(np.int8), axis=1))
        outline.append(perim ** 2 / (4 * np.pi * a))
        rgb = crop[..., :3][m]
        if len(rgb) and np.ptp(rgb) > 0:                 # a silhouette-only view has no colour
            pixels.append(rgb)
    out = {"views": len(solidity)}
    if solidity:
        out["solidity"] = round(float(np.mean(solidity)), 4)
        out["outline"] = round(float(np.mean(outline)), 4)
    if pixels:
        out.update(colour_stats(np.concatenate(pixels)))
    return out


def colour_stats(rgb):
    rng = np.random.default_rng(0)
    if len(rgb) > 40000:
        rgb = rgb[rng.choice(len(rgb), 40000, replace=False)]
    lab = to_lab(rgb.astype(float))
    return {"palette": palette(lab),
            "value": np.percentile(lab[:, 0], [5, 50, 95]).round(2).tolist()}


def texture_colours(mesh):
    pixels = []
    for mat in np.unique(mesh.material):
        img = mesh.texture_image(int(mat)) if mat >= 0 else None
        if img is not None:
            pixels.append(np.asarray(img.resize((128, 128))).reshape(-1, 3))
        elif mat >= 0:
            f = mesh.materials[int(mat)].get("pbrMetallicRoughness", {}).get("baseColorFactor")
            if f:
                share = int((mesh.material == mat).mean() * 4096) + 1
                rgb = np.clip(np.array(f[:3]) ** (1 / 2.2) * 255, 0, 255)
                pixels.append(np.tile(rgb, (share, 1)))
    return colour_stats(np.concatenate(pixels)) if pixels else {}


def hull_area(mask):
    """Pixel area of the convex hull of a mask (monotone chain over each row's end pixels)."""
    rows = np.flatnonzero(mask.any(axis=1))
    if len(rows) < 2:
        return float(mask.sum())
    first = mask[rows].argmax(axis=1)
    last = mask.shape[1] - 1 - mask[rows][:, ::-1].argmax(axis=1)
    pts = sorted({(float(x), float(y)) for y, a, b in zip(rows, first, last)
                  for x in (a - 0.5, b + 0.5) for y in (y - 0.5, y + 0.5)})

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(p)
        return h

    hull = half(pts)[:-1] + half(pts[::-1])[:-1]
    x, y = np.array(hull)[:, 0], np.array(hull)[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


# --- comparing ----------------------------------------------------------------------------------

def emd(p, q, centres):
    cdf = np.cumsum(np.asarray(p) - np.asarray(q))[:-1]
    return float(np.sum(np.abs(cdf) * np.diff(centres)))


def delta(how, a, c):
    if how == "ratio":
        return max(a / c, c / a) if a and c else None
    if how == "ratio_max":
        return max(max(x / y, y / x) for x, y in zip(a, c) if x and y)
    if how == "abs":
        return abs(a - c)
    if how == "abs_max":
        return max(abs(x - y) for x, y in zip(a, c))
    if how == "over":
        return c - a
    if how == "emd_edges":
        return emd(a, c, EDGE_CENTRES)
    if how == "emd_parts":
        return emd(a, c, PART_CENTRES)
    if how == "palette":
        return palette_distance(a, c)
    raise ValueError(how)


def describe(glb, views):
    mesh = load_mesh(glb)
    out = geometry(mesh)
    vs = view_stats(views) if views else {}
    out.update({k: v for k, v in vs.items() if k in ("solidity", "outline")})
    colours = vs if "palette" in vs else texture_colours(mesh)
    out.update({k: colours[k] for k in ("palette", "value") if k in colours})
    out["colour_source"] = "views" if "palette" in vs else ("textures" if colours else None)
    return out


def compare(style, cand, profile="default", same_class=False):
    rows, worst = [], "pass"
    for name, (how, default_tol, kind) in DEFAULTS.items():
        if name == "proportions" and not same_class:
            continue
        tol = style.get("tolerances", {}).get(name, default_tol)
        if profile == "strict" and name == "palette":
            tol, kind = min(tol, 5.0), "hard"
        a, c = style["metrics"].get(name), cand.get(name)
        if a is None or c is None:
            rows.append({"metric": name, "verdict": "skipped",
                         "why": "not measured on the anchor or the candidate"})
            continue
        d = delta(how, a, c)
        if d is None:
            continue
        ok = d <= tol
        verdict = "pass" if ok else ("fail" if kind == "hard" else "warn")
        if verdict == "fail" or (verdict == "warn" and worst == "pass"):
            worst = verdict
        rows.append({"metric": name, "kind": kind, "delta": round(float(d), 4),
                     "tolerance": tol, "verdict": verdict,
                     **({"anchor": a, "candidate": c} if not isinstance(a, list) else {})})
    return rows, worst


# --- commands -----------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("glb")
    e.add_argument("--views")
    e.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("style")
    c.add_argument("glb")
    c.add_argument("--views")
    c.add_argument("--profile", choices=["default", "strict"], default="default")
    c.add_argument("--same-class", action="store_true")
    k = sub.add_parser("calibrate")
    k.add_argument("style")
    k.add_argument("glbs", nargs="+")
    k.add_argument("--views", nargs="*", default=[])
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "extract":
        style = {"anchor": a.glb.replace("\\", "/"), "metrics": describe(a.glb, a.views),
                 "tolerances": {}, "calibrated_with": []}
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(style, fh, indent=1)
        print(json.dumps({"out": a.out, "metrics": style["metrics"]}, indent=1))
        return 0
    with open(a.style, encoding="utf-8") as fh:
        style = json.load(fh)
    if a.cmd == "check":
        rows, verdict = compare(style, describe(a.glb, a.views), a.profile, a.same_class)
        print(json.dumps({"anchor": style["anchor"], "candidate": a.glb.replace("\\", "/"),
                          "metrics": rows, "verdict": verdict,
                          "note": "style statistics only; silhouettes are meant to differ. The "
                                  "art-director's lineup next to the anchor decides."}, indent=1))
        return 1 if verdict == "fail" else 0
    # calibrate: widen each tolerance to 1.5 x the spread among approved members
    views = a.views + [None] * (len(a.glbs) - len(a.views))
    spreads = {}
    for glb, v in zip(a.glbs, views):
        cand = describe(glb, v)
        for name, (how, _, _) in DEFAULTS.items():
            x, y = style["metrics"].get(name), cand.get(name)
            if x is None or y is None:
                continue
            d = delta(how, x, y)
            if d is not None:
                spreads[name] = max(spreads.get(name, 0), d)
    for name, d in spreads.items():
        how, default_tol, _ = DEFAULTS[name]
        widened = 1 + 1.5 * (d - 1) if how.startswith("ratio") else 1.5 * d
        style["tolerances"][name] = round(max(default_tol, widened), 4)
    style["calibrated_with"] = sorted(set(style.get("calibrated_with", []) +
                                          [g.replace("\\", "/") for g in a.glbs]))
    with open(a.style, "w", encoding="utf-8") as fh:
        json.dump(style, fh, indent=1)
    print(json.dumps({"style": a.style, "tolerances": style["tolerances"],
                      "spread": {k: round(v, 4) for k, v in spreads.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
