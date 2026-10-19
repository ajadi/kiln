"""Read the triangles of a glTF/GLB file into numpy arrays, in world space. Normal Python
(numpy; Pillow only for embedded textures). Shared by style_anchor.py and lod_check.py.

  from glb_mesh import load_mesh
  m = load_mesh("prop.glb")            # LOD0 only (nodes named <base>_LOD1.. are skipped)
  m = load_mesh("prop.glb", lod=2)     # the nodes of one LOD level (plus nodes with no level)
  m.tris (N,3,3) world positions, m.uvs (N,3,2) or None, m.material (N,) index, m.node (N,) name
  m.materials (glTF material list), m.texture_size(material) -> (w, h) or None
"""

import base64
import json
import os
import re
import struct

import numpy as np

MAGIC, JSON_CHUNK, BIN_CHUNK = 0x46546C67, 0x4E4F534A, 0x004E4942
LOD = re.compile(r"^(.*?)_LOD(\d+)$", re.I)
COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32,
             5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_file(path):
    """(gltf json, [buffer bytes])."""
    with open(path, "rb") as fh:
        data = fh.read()
    glb = None
    if data[:4] == b"glTF":
        magic, _version, _length = struct.unpack_from("<III", data, 0)
        off, gltf = 12, None
        while off + 8 <= len(data):
            n, kind = struct.unpack_from("<II", data, off)
            chunk = data[off + 8:off + 8 + n]
            if kind == JSON_CHUNK:
                gltf = json.loads(chunk.decode("utf-8"))
            elif kind == BIN_CHUNK:
                glb = chunk
            off += 8 + n
    else:
        gltf = json.loads(data.decode("utf-8-sig"))
    buffers = []
    for i, b in enumerate(gltf.get("buffers", [])):
        uri = b.get("uri")
        if uri is None:
            buffers.append(glb or b"")
        elif uri.startswith("data:"):
            buffers.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            with open(os.path.join(os.path.dirname(path), uri), "rb") as fh:
                buffers.append(fh.read())
    return gltf, buffers


def accessor(gltf, buffers, index):
    acc = gltf["accessors"][index]
    dtype, width, count = COMPONENT[acc["componentType"]], WIDTH[acc["type"]], acc["count"]
    if "bufferView" not in acc:
        return np.zeros((count, width) if width > 1 else count, dtype)
    bv = gltf["bufferViews"][acc["bufferView"]]
    raw = buffers[bv["buffer"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    item = np.dtype(dtype).itemsize * width
    stride = bv.get("byteStride") or item
    if stride == item:
        arr = np.frombuffer(raw, dtype, count * width, start)
    else:
        rows = np.frombuffer(raw, np.uint8, (count - 1) * stride + item, start)
        arr = np.lib.stride_tricks.as_strided(rows, (count, item), (stride, 1)).copy().view(dtype)
    arr = arr.reshape(count, width) if width > 1 else arr
    if acc.get("normalized") and dtype != np.float32:
        arr = arr.astype(np.float32) / np.iinfo(dtype).max
    return arr


def local_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], float).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), float)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    s = np.array(node.get("scale", [1, 1, 1]), float)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def node_level(name):
    m = LOD.match(name or "")
    return int(m.group(2)) if m else None


class Mesh:
    def __init__(self, path, gltf, buffers, tris, uvs, material, node):
        self.path, self.gltf, self.buffers = path, gltf, buffers
        self.tris, self.uvs, self.material, self.node = tris, uvs, material, node
        self.materials = gltf.get("materials", [])

    def texture_size(self, material_index):
        """Size of the material's base colour texture, or None."""
        img = self.texture_image(material_index, size_only=True)
        return img

    def texture_image(self, material_index, size_only=False):
        try:
            mat = self.materials[material_index]
            tex = mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]
            src = self.gltf["textures"][tex]["source"]
            img = self.gltf["images"][src]
        except (IndexError, KeyError, TypeError):
            return None
        if "bufferView" in img:
            bv = self.gltf["bufferViews"][img["bufferView"]]
            start = bv.get("byteOffset", 0)
            raw = self.buffers[bv["buffer"]][start:start + bv["byteLength"]]
        elif img.get("uri", "").startswith("data:"):
            raw = base64.b64decode(img["uri"].split(",", 1)[1])
        else:
            try:
                with open(os.path.join(os.path.dirname(self.path), img.get("uri", "")), "rb") as fh:
                    raw = fh.read()
            except OSError:
                return None
        import io
        from PIL import Image
        try:
            im = Image.open(io.BytesIO(raw))
        except OSError:
            return None
        return im.size if size_only else im.convert("RGB")


def load_mesh(path, lod=0):
    """Triangles of the scene in world space; `lod` picks one level of `<base>_LOD<n>` nodes."""
    gltf, buffers = read_file(path)
    nodes = gltf.get("nodes", [])
    children = {c for n in nodes for c in n.get("children", [])}
    scenes = gltf.get("scenes", [])
    roots = scenes[gltf.get("scene", 0)].get("nodes", []) if scenes else \
        [i for i in range(len(nodes)) if i not in children]
    tris, uvs, mats, names, has_uv = [], [], [], [], True
    stack = [(r, np.eye(4), None) for r in roots]
    while stack:
        index, parent, inherited = stack.pop()
        node = nodes[index]
        world = parent @ local_matrix(node)
        level = node_level(node.get("name"))
        level = inherited if level is None else level
        for c in node.get("children", []):
            stack.append((c, world, level))
        if "mesh" not in node or (level is not None and level != lod):
            continue
        for prim in gltf["meshes"][node["mesh"]].get("primitives", []):
            if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                continue
            pos = accessor(gltf, buffers, prim["attributes"]["POSITION"]).astype(float)
            idx = accessor(gltf, buffers, prim["indices"]).astype(np.int64) if "indices" in prim \
                else np.arange(len(pos))
            idx = idx[:len(idx) // 3 * 3].reshape(-1, 3)
            world_pos = pos @ world[:3, :3].T + world[:3, 3]
            tris.append(world_pos[idx])
            if "TEXCOORD_0" in prim["attributes"]:
                uvs.append(accessor(gltf, buffers, prim["attributes"]["TEXCOORD_0"]).astype(float)[idx])
            else:
                has_uv = False
            mats.append(np.full(len(idx), prim.get("material", -1)))
            names += [node.get("name", "")] * len(idx)
    if not tris:
        raise ValueError(f"{path}: no triangles (level {lod})")
    return Mesh(path, gltf, buffers, np.concatenate(tris),
                np.concatenate(uvs) if has_uv and uvs else None, np.concatenate(mats),
                np.array(names))


def levels(path):
    """The LOD levels present in the file ([0] when it has no chain)."""
    gltf, _ = read_file(path)
    found = {node_level(n.get("name")) for n in gltf.get("nodes", []) if "mesh" in n}
    found.discard(None)
    return sorted(found | {0})


def face_areas(tris):
    return 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)


def face_normals(tris):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.where(length > 0, length, 1)


def weld(tris, tol_rel=1e-5):
    """Shared vertex ids by position (glTF splits vertices at UV and normal seams)."""
    pts = tris.reshape(-1, 3)
    diag = float(np.linalg.norm(pts.max(0) - pts.min(0))) or 1.0
    keys = np.round(pts / (diag * tol_rel)).astype(np.int64)
    _, ids = np.unique(keys, axis=0, return_inverse=True)
    return ids.reshape(-1, 3), diag


def edges(tris):
    """Edges over welded vertices: (vertex pairs (E,2), face count (E,), first face (E,),
    second face (E,) or -1, length (E,), welded vertex ids (N,3))."""
    ids, _ = weld(tris)
    pairs = np.stack([ids[:, [0, 1]], ids[:, [1, 2]], ids[:, [2, 0]]], axis=1).reshape(-1, 2)
    pairs.sort(axis=1)
    face = np.repeat(np.arange(len(tris)), 3)
    corner = np.tile([[0, 1], [1, 2], [2, 0]], (len(tris), 1))
    uniq, inverse = np.unique(pairs, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    order = np.argsort(inverse, kind="stable")
    counts = np.bincount(inverse, minlength=len(uniq))
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    first = face[order[starts]]
    second = np.where(counts >= 2, face[order[np.minimum(starts + 1, len(order) - 1)]], -1)
    a = tris[face, corner[:, 0]]
    b = tris[face, corner[:, 1]]
    lengths = np.zeros(len(uniq))
    lengths[inverse] = np.linalg.norm(a - b, axis=1)
    return uniq, counts, first, second, lengths, ids
