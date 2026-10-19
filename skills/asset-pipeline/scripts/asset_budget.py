"""What each glTF/GLB asset costs, against the project's budgets. Python stdlib only.

  python asset_budget.py "assets/**/*.glb" [--budgets production/budgets.json] [--top 20]

Per file (read from the glTF JSON and the binary chunk, nothing imported):
  triangles         drawn per scene instance (a mesh used by two nodes counts twice); of a LOD
                    chain (`<name>_LOD0`, `_LOD1`, ...) only LOD0 counts, the levels are in `lods`
  unique_triangles  in the meshes themselves
  vertices, draw_calls (one per primitive per mesh instance), materials, bones (largest skin),
  textures          size of every image (embedded PNG/JPEG or an external file next to it)
  vram_mb_uncompressed / vram_mb_compressed
                    RGBA8 (4 bytes/px) vs block-compressed BC7/ASTC 4x4 (1 byte/px), both with a
                    full mip chain (x 4/3). Images are counted once per file: every glb carries its
                    own copy, so a "shared" atlas in 12 glbs costs 12 times (asset-pipeline).
Budgets (JSON, committed): {"<glob>": {"triangles": N, "draw_calls": N, "materials": N,
"bones": N, "texture_px": N (largest side), "vram_mb": N (compressed), "lod_ratio": 0.5 (each LOD
level at most this share of the one before, +10 %)}, ...}; the first glob that
matches a file applies ("*" last as the default). Totals give the whole set. Output: JSON; exit 1
when a file is over its budget.
"""

import argparse
import fnmatch
import glob
import json
import os
import re
import struct
import sys

MAGIC, JSON_CHUNK, BIN_CHUNK = 0x46546C67, 0x4E4F534A, 0x004E4942
LOD = re.compile(r"^(.*?)_LOD(\d+)$", re.I)


def load(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if path.lower().endswith(".gltf"):
        gltf = json.loads(data.decode("utf-8"))
        return gltf, None
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    if magic != MAGIC:
        raise ValueError("not a GLB file")
    off, gltf, blob = 12, None, b""
    while off + 8 <= len(data):
        n, kind = struct.unpack_from("<II", data, off)
        chunk = data[off + 8:off + 8 + n]
        if kind == JSON_CHUNK:
            gltf = json.loads(chunk.decode("utf-8"))
        elif kind == BIN_CHUNK:
            blob = chunk
        off += 8 + n
    return gltf, blob


def image_size(raw):
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return list(struct.unpack(">II", raw[16:24]))
    if raw[:2] == b"\xff\xd8":                        # JPEG: find a SOF marker
        i = 2
        while i + 9 < len(raw):
            if raw[i] != 0xFF:
                i += 1
                continue
            marker, length = raw[i + 1], struct.unpack(">H", raw[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", raw[i + 5:i + 9])
                return [w, h]
            i += 2 + length
    return None


def image_bytes(gltf, blob, img, base):
    if "bufferView" in img and blob is not None:
        bv = gltf["bufferViews"][img["bufferView"]]
        start = bv.get("byteOffset", 0)
        return blob[start:start + bv["byteLength"]]
    uri = img.get("uri", "")
    if uri and not uri.startswith("data:"):
        try:
            with open(os.path.join(base, uri), "rb") as fh:
                return fh.read(65536)
        except OSError:
            return None
    return None


def measure(path):
    gltf, blob = load(path)
    acc = gltf.get("accessors", [])

    def prim_tris(p):
        mode = p.get("mode", 4)
        count = acc[p["indices"]]["count"] if "indices" in p else \
            acc[p["attributes"]["POSITION"]]["count"]
        return count // 3 if mode == 4 else max(0, count - 2) if mode in (5, 6) else 0

    meshes = gltf.get("meshes", [])
    mesh_tris = [sum(prim_tris(p) for p in m.get("primitives", [])) for m in meshes]
    mesh_verts = [sum(acc[p["attributes"]["POSITION"]]["count"] for p in m.get("primitives", [])
                      if "POSITION" in p.get("attributes", {})) for m in meshes]
    # LOD chains (`<base>_LOD<n>` node or mesh names, asset-pipeline "LOD chain"): one level is
    # drawn at a time, so the drawn numbers take the highest-detail level only
    levels, uses = {}, []
    for n in gltf.get("nodes", []):
        if "mesh" not in n:
            continue
        name = n.get("name") or meshes[n["mesh"]].get("name") or ""
        m = LOD.match(name)
        if m:
            levels.setdefault(m.group(1), []).append((int(m.group(2)), n["mesh"]))
            if int(m.group(2)) > 0:
                continue
        uses.append(n["mesh"])
    uses = uses or list(range(len(meshes)))
    textures = []
    for img in gltf.get("images", []):
        raw = image_bytes(gltf, blob, img, os.path.dirname(path))
        size = image_size(raw) if raw else None
        textures.append({"name": img.get("name") or img.get("uri") or "embedded", "size": size})
    px = sum(t["size"][0] * t["size"][1] for t in textures if t["size"])
    return {"file": path.replace("\\", "/"),
            "triangles": sum(mesh_tris[m] for m in uses),
            "unique_triangles": sum(mesh_tris),
            "vertices": sum(mesh_verts[m] for m in uses),
            "draw_calls": sum(len(meshes[m].get("primitives", [])) for m in uses),
            "materials": len(gltf.get("materials", [])),
            "bones": max((len(s.get("joints", [])) for s in gltf.get("skins", [])), default=0),
            "textures": textures,
            "texture_px": max((max(t["size"]) for t in textures if t["size"]), default=0),
            "vram_mb_uncompressed": px * 4 * 4 / 3 / 2 ** 20,
            "vram_mb_compressed": px * 1 * 4 / 3 / 2 ** 20,
            "lods": {base: [mesh_tris[m] for _, m in sorted(lv)] for base, lv in levels.items()}}


def budget_for(path, budgets):
    for pattern, limits in budgets.items():
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
            return pattern, limits
    return None, {}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--budgets")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    files = sorted({f for p in a.patterns for f in glob.glob(p, recursive=True)
                    if f.lower().endswith((".glb", ".gltf"))})
    budgets = {}
    if a.budgets:
        with open(a.budgets, encoding="utf-8") as fh:
            budgets = json.load(fh)
    rows, failed = [], 0
    for path in files:
        try:
            row = measure(path)
        except (ValueError, KeyError, IndexError, struct.error) as exc:
            rows.append({"file": path, "verdict": "NOT ASSESSED", "problems": [str(exc)]})
            continue
        pattern, limits = budget_for(row["file"], budgets)
        problems = []
        checks = {"triangles": row["triangles"], "draw_calls": row["draw_calls"],
                  "materials": row["materials"], "bones": row["bones"],
                  "texture_px": row["texture_px"], "vram_mb": row["vram_mb_compressed"]}
        for key, value in checks.items():
            if key in limits and value > limits[key]:
                problems.append(f"{key} {round(value, 2)} > {limits[key]} ({pattern})")
        if "lod_ratio" in limits:
            for base, tris in row["lods"].items():
                for i in range(1, len(tris)):
                    if tris[i - 1] and tris[i] / tris[i - 1] > limits["lod_ratio"] * 1.1:
                        problems.append(f"lod_ratio {base}_LOD{i}: {tris[i]} of {tris[i - 1]} "
                                        f"triangles > {limits['lod_ratio']} ({pattern})")
        row["vram_mb_uncompressed"] = round(row["vram_mb_uncompressed"], 6)
        row["vram_mb_compressed"] = round(row["vram_mb_compressed"], 6)
        row.update({"budget": pattern, "problems": problems,
                    "verdict": "FAIL" if problems else ("PASS" if pattern else "NO BUDGET")})
        failed += bool(problems)
        rows.append(row)
    ok = [r for r in rows if "triangles" in r]
    totals = {"files": len(rows), "triangles": sum(r["triangles"] for r in ok),
              "draw_calls": sum(r["draw_calls"] for r in ok),
              "vram_mb_compressed": round(sum(r["vram_mb_compressed"] for r in ok), 3),
              "vram_mb_uncompressed": round(sum(r["vram_mb_uncompressed"] for r in ok), 3)}
    heaviest = sorted(ok, key=lambda r: -r["triangles"])[:a.top]
    print(json.dumps({"assets": rows, "totals": totals,
                      "heaviest": [[r["file"], r["triangles"]] for r in heaviest],
                      "verdict": "FAIL" if failed else "PASS"}, indent=1))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
