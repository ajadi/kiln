"""Synthetic GLB files for the asset-pipeline tests (style_anchor.py, lod_check.py,
asset_budget.py): shapes as triangle arrays and a small GLB writer (nodes, UVs, materials,
embedded PNG textures)."""

import io
import json
import struct

import numpy as np


def box(sx=1.0, sy=1.0, sz=1.0, bevel=0.0, centre=(0, 0, 0)):
    """A box; with bevel > 0 every edge is chamfered at 45 degrees (a bevelled hard-surface
    look). Returns (N,3,3) triangles."""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    b = bevel
    if b <= 0:
        v = np.array([[x, y, z] for x in (-hx, hx) for y in (-hy, hy) for z in (-hz, hz)])
        quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        tris = [[v[a], v[b_], v[c]] for a, b_, c, d in quads] + \
               [[v[a], v[c], v[d]] for a, b_, c, d in quads]
        return outward(np.array(tris, float)) + np.array(centre)
    # chamfered box: 6 faces, 12 edge chamfers (45 degrees), 8 corner triangles
    P = {}
    for x in (-1, 1):
        for y in (-1, 1):
            for z in (-1, 1):
                P["x", x, y, z] = [x * hx, y * (hy - b), z * (hz - b)]
                P["y", x, y, z] = [x * (hx - b), y * hy, z * (hz - b)]
                P["z", x, y, z] = [x * (hx - b), y * (hy - b), z * hz]
    ring = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    quads = []
    for s in (-1, 1):
        quads.append([P["x", s, u, v] for u, v in ring])
        quads.append([P["y", u, s, v] for u, v in ring])
        quads.append([P["z", u, v, s] for u, v in ring])
    for u in (-1, 1):
        for v in (-1, 1):
            quads.append([P["x", u, v, -1], P["x", u, v, 1], P["y", u, v, 1], P["y", u, v, -1]])
            quads.append([P["y", -1, u, v], P["y", 1, u, v], P["z", 1, u, v], P["z", -1, u, v]])
            quads.append([P["x", u, -1, v], P["x", u, 1, v], P["z", u, 1, v], P["z", u, -1, v]])
    tris = [[q[0], q[1], q[2]] for q in quads] + [[q[0], q[2], q[3]] for q in quads]
    tris += [[P["x", x, y, z], P["y", x, y, z], P["z", x, y, z]]
             for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    return outward(np.array(tris, float)) + np.array(centre)


def outward(tris):
    """Wind every triangle of a convex shape so its normal points away from the centre."""
    c = tris.reshape(-1, 3).mean(0)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    flip = ((tris.mean(1) - c) * n).sum(1) < 0
    tris = tris.copy()
    tris[flip] = tris[flip][:, [0, 2, 1]]
    return tris


def cylinder(segments=16, r=0.5, h=1.0, centre=(0, 0, 0)):
    ang = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    ring = np.stack([np.cos(ang) * r, np.sin(ang) * r], 1)
    tris = []
    for i in range(segments):
        j = (i + 1) % segments
        a0, a1 = np.r_[ring[i], -h / 2], np.r_[ring[j], -h / 2]
        b0, b1 = np.r_[ring[i], h / 2], np.r_[ring[j], h / 2]
        tris += [[a0, a1, b1], [a0, b1, b0], [[0, 0, h / 2], b0, b1], [[0, 0, -h / 2], a1, a0]]
    return outward(np.array(tris, float)) + np.array(centre)


def sphere(rings=12, segments=24, r=0.5, centre=(0, 0, 0)):
    tris = []
    for i in range(rings):
        t0, t1 = np.pi * i / rings, np.pi * (i + 1) / rings
        for j in range(segments):
            p0, p1 = 2 * np.pi * j / segments, 2 * np.pi * (j + 1) / segments
            q = lambda t, p: [r * np.sin(t) * np.cos(p), r * np.sin(t) * np.sin(p), r * np.cos(t)]  # noqa: E731
            a, b, c, d = q(t0, p0), q(t0, p1), q(t1, p1), q(t1, p0)
            if i:                               # the top ring's a and b are both the pole
                tris.append([a, b, c])
            if i < rings - 1:                   # the bottom ring's c and d are both the pole
                tris.append([a, c, d])
    return outward(np.array(tris, float)) + np.array(centre)


def planar_uvs(tris, scale=1.0):
    """UVs from a box projection (dominant normal axis), `scale` UV units per metre."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    axis = np.abs(n).argmax(1)
    keep = np.array([[1, 2], [0, 2], [0, 1]])[axis]
    return np.take_along_axis(tris, keep[:, None, :].repeat(3, 1), 2) * scale


def png(size=(64, 64), colour=(200, 60, 40)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, "PNG")
    return buf.getvalue()


def write_glb(path, nodes, materials=None, parent=None):
    """nodes: [{"name", "tris": (N,3,3), "uvs": (N,3,2) or None, "material": index}];
    materials: [{"name", "colour": (r,g,b) 0-1, "texture": png bytes or None}]. With `parent`,
    every mesh node is a child of one empty node of that name."""
    blob, views, accessors, meshes, gnodes = bytearray(), [], [], [], []

    def add_view(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data),
                      **({"target": target} if target else {})})
        blob.extend(data)
        return len(views) - 1

    def add_acc(arr, kind):
        arr = np.ascontiguousarray(arr, np.float32)
        v = add_view(arr.tobytes(), 34962)
        acc = {"bufferView": v, "componentType": 5126, "count": len(arr), "type": kind}
        if kind == "VEC3":
            acc.update(min=arr.min(0).tolist(), max=arr.max(0).tolist())
        accessors.append(acc)
        return len(accessors) - 1

    for nd in nodes:
        t = np.asarray(nd["tris"], float)
        attrs = {"POSITION": add_acc(t.reshape(-1, 3), "VEC3")}
        if nd.get("uvs") is not None:
            attrs["TEXCOORD_0"] = add_acc(np.asarray(nd["uvs"]).reshape(-1, 2), "VEC2")
        prim = {"attributes": attrs, "mode": 4}
        if nd.get("material") is not None:
            prim["material"] = nd["material"]
        meshes.append({"name": nd["name"], "primitives": [prim]})
        gnodes.append({"name": nd["name"], "mesh": len(meshes) - 1})
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "nodes": gnodes, "meshes": meshes,
            "accessors": accessors, "bufferViews": views}
    roots = list(range(len(gnodes)))
    if parent:
        gltf["nodes"].append({"name": parent, "children": roots})
        roots = [len(gltf["nodes"]) - 1]
    gltf["scenes"] = [{"nodes": roots}]
    if materials:
        gltf["materials"], images, textures = [], [], []
        for m in materials:
            pbr = {"baseColorFactor": list(m.get("colour", (0.8, 0.8, 0.8))) + [1.0]}
            if m.get("texture"):
                images.append({"bufferView": add_view(m["texture"]), "mimeType": "image/png"})
                textures.append({"source": len(images) - 1})
                pbr["baseColorTexture"] = {"index": len(textures) - 1}
            gltf["materials"].append({"name": m.get("name", "m"), "pbrMetallicRoughness": pbr})
        if images:
            gltf["images"], gltf["textures"] = images, textures
    while len(blob) % 4:
        blob.append(0)
    gltf["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(gltf).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + \
        struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
