"""LOD gate: does each level of an exported LOD chain look like LOD0 where it switches in?

Normal Python (numpy, Pillow), run with Bash after blender-modeling lod_build.py and
lod_shots.py and the export (export_extras=True keeps each level's kiln_lod_* values).

  python lod_check.py art/props/crate.glb --shots .kiln/tmp/lod [--profile performance] [--screen-h 1080]

Per level i >= 1 (asset-pipeline "LOD chain"; research 2026-10-19 lod-and-style-anchor):
  G1 triangles      <= 0.55 x the previous level passes, over 0.75 fails (a level must cut 25 %)
  G2 chain length   a level after one under 1,000 triangles or a switch size under 0.02 warns
  G4 contour        two-sided distance between the LOD0 and LOD_i silhouette outlines at the
                    switch size, in game pixels: p95 <= p and max <= 2p (p = 1, performance 3)
  G5 boundary shift XOR area / LOD0 outline length <= 0.5 p game pixels
  G6 shading        mean / p95 L* difference inside both silhouettes <= 2 / 8 (x2 performance)
                    - warn only until calibrated on approved assets
  G7 triangle size  mean projected triangle area at the switch size >= 8 px2 (performance 4)
                    - warn only (an estimate from surface area)
  G8 materials      a level uses no more materials than the one before; the last level 1 (warn)
Without --shots only G1, G2, G7 and G8 are checked. Thresholds marked warn are UNVERIFIED
working values: record what approved assets measure in memory/pipeline.md. Exit 1 on a fail.
"""

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from glb_mesh import LOD, face_areas, levels, load_mesh, read_file  # noqa: E402

PROFILES = {"default": {"p": 1.0, "tri_px2": 8.0, "shade": 1.0},
            "performance": {"p": 3.0, "tri_px2": 4.0, "shade": 2.0}}


def level_extras(path):
    gltf, _ = read_file(path)
    out = {}
    for n in gltf.get("nodes", []):
        m = LOD.match(n.get("name", ""))
        if m and "mesh" in n:
            ex = n.get("extras") or {}
            out.setdefault(int(m.group(2)), ex)
    return out


def mask_and_rgb(path):
    from PIL import Image
    arr = np.asarray(Image.open(path).convert("RGBA")).astype(float)
    return arr[..., 3] >= 128, arr[..., :3]


def outline(mask):
    inner = mask.copy()
    inner[1:, :] &= mask[:-1, :]
    inner[:-1, :] &= mask[1:, :]
    inner[:, 1:] &= mask[:, :-1]
    inner[:, :-1] &= mask[:, 1:]
    return np.argwhere(mask & ~inner).astype(float)


def nearest(a, b, chunk=2048):
    """Distance from every point of a to the nearest point of b."""
    if not len(a) or not len(b):
        return np.full(len(a), np.inf)
    out = np.empty(len(a))
    for i in range(0, len(a), chunk):
        d = ((a[i:i + chunk, None, :] - b[None, :, :]) ** 2).sum(2)
        out[i:i + chunk] = np.sqrt(d.min(1))
    return out


def lightness(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    y = c @ np.array([0.2126, 0.7152, 0.0722])
    return np.where(y > 216 / 24389, 116 * np.cbrt(y) - 16, 24389 / 27 * y)


def shots_checks(shots_dir, entry, prof):
    p = prof["p"]
    k = entry["px_per_game_px"]
    dist, shift, d_mean, d_p95 = [], [], [], []
    for v in entry["views"]:
        m0, rgb0 = mask_and_rgb(os.path.join(shots_dir, v["lod0"]))
        m1, rgb1 = mask_and_rgb(os.path.join(shots_dir, v["lod"]))
        c0, c1 = outline(m0), outline(m1)
        dist.append(np.concatenate([nearest(c0, c1), nearest(c1, c0)]) / k)
        shift.append(np.logical_xor(m0, m1).sum() / (max(len(c0), 1) * k))
        both = m0 & m1
        if both.any():
            dl = np.abs(lightness(rgb0[both]) - lightness(rgb1[both]))
            d_mean.append(float(dl.mean()))
            d_p95.append(float(np.percentile(dl, 95)))
    alld = np.concatenate(dist) if dist else np.zeros(1)
    p95, mx = float(np.percentile(alld, 95)), float(alld.max())
    out = {"G4_contour": {"p95_px": round(p95, 3), "max_px": round(mx, 3),
                          "limit": [p, 2 * p], "views": len(entry["views"]),
                          "verdict": "pass" if p95 <= p and mx <= 2 * p else "fail"},
           "G5_shift": {"px": round(max(shift), 3), "limit": 0.5 * p,
                        "verdict": "pass" if max(shift) <= 0.5 * p else "fail"}}
    if d_mean:
        lim = (2 * prof["shade"], 8 * prof["shade"])
        out["G6_shading"] = {"mean_dl": round(max(d_mean), 2), "p95_dl": round(max(d_p95), 2),
                             "limit": list(lim), "verdict": "pass" if max(d_mean) <= lim[0]
                             and max(d_p95) <= lim[1] else "warn"}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glb")
    ap.add_argument("--shots", help="lod_shots.py output folder (with lod_shots.json)")
    ap.add_argument("--profile", choices=list(PROFILES), default="default")
    ap.add_argument("--screen-h", type=int, default=1080)
    a = ap.parse_args(argv)
    prof = PROFILES[a.profile]
    present = levels(a.glb)
    extras = level_extras(a.glb)
    shots = {}
    if a.shots:
        with open(os.path.join(a.shots, "lod_shots.json"), encoding="utf-8") as fh:
            shots = {e["level"]: e for e in json.load(fh)["levels"]}
    sys.stdout.reconfigure(encoding="utf-8")
    if len(present) < 2:
        print(json.dumps({"glb": a.glb, "levels": [], "verdict": "pass",
                          "note": "no authored LOD chain (fine under 1,000 triangles: the engine's "
                                  "automatic LOD, or a cull distance under 256)"}, indent=1))
        return 0
    meshes = {lv: load_mesh(a.glb, lod=lv) for lv in present}
    diameter = float(np.linalg.norm(np.ptp(meshes[0].tris.reshape(-1, 3), axis=0)))
    rows, worst, prev = [], "pass", None
    for lv in present:
        m = meshes[lv]
        tris, area = len(m.tris), float(face_areas(m.tris).sum())
        mats = len({int(x) for x in m.material if x >= 0}) or 1
        row = {"level": lv, "tris": tris, "materials": mats, "checks": {}}
        screen = (extras.get(lv) or {}).get("kiln_lod_screen")
        if screen is not None:
            row["screen"] = screen
        if prev is not None:
            ratio = tris / prev["tris"]
            row["ratio"] = round(ratio, 3)
            row["checks"]["G1_triangles"] = {
                "ratio": round(ratio, 3), "target": 0.5, "limit": 0.75,
                "verdict": "pass" if ratio <= 0.55 else ("warn" if ratio <= 0.75 else "fail")}
            small = prev["tris"] < 1000 or (prev.get("screen") or 1) < 0.02
            row["checks"]["G2_chain"] = {"verdict": "warn" if small else "pass",
                                         **({"why": "the previous level was already under 1,000 "
                                             "triangles or 0.02 of the screen"} if small else {})}
            row["checks"]["G8_materials"] = {
                "materials": mats, "previous": prev["materials"],
                "verdict": "fail" if mats > prev["materials"] else
                ("warn" if lv == present[-1] and mats > 1 else "pass")}
            if screen:
                px_per_m = screen * a.screen_h / diameter
                tri_px2 = area / tris * px_per_m ** 2 * 0.5
                row["checks"]["G7_triangle_px2"] = {
                    "mean_px2": round(tri_px2, 2), "limit": prof["tri_px2"],
                    "verdict": "pass" if tri_px2 >= prof["tri_px2"] else "warn"}
            if lv in shots:
                row["checks"].update(shots_checks(a.shots, shots[lv], prof))
            elif a.shots:
                row["checks"]["G4_contour"] = {"verdict": "fail", "why": "no shots for this level"}
        for c in row["checks"].values():
            if c["verdict"] == "fail" or (c["verdict"] == "warn" and worst == "pass"):
                worst = c["verdict"]
        rows.append(row)
        prev = row
    print(json.dumps({"glb": a.glb.replace("\\", "/"), "profile": a.profile,
                      "diameter_m": round(diameter, 4), "levels": rows, "verdict": worst,
                      "checked": "G1 G2 G7 G8" + (" G4 G5 G6" if a.shots else
                                                   " (no --shots: silhouette and shading not checked)")},
                     indent=1))
    return 1 if worst == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
