extends RefCounted
## Kiln mesh-fit helpers for headless probes (Godot 4.6/4.7): CPU skinning of a MeshInstance3D
## on its Skeleton3D, so garment, seat, rail and floor fits can be measured where the dummy
## renderer does not skin. Copy to `tests/probes/mesh_fit.gd`:
##
##   var fit = load("res://tests/probes/mesh_fit.gd").new()
##   var legs: PackedInt32Array = fit.verts_on(body_mi, sk, "Leg", 0.5)    # vertices on leg bones
##   var pts: PackedVector3Array = fit.skin_points(body_mi, sk, legs)     # skeleton space
##   check("corpse-floor", fit.lowest(fit.to_world(sk, pts)).y, ">=", -0.005, "floor at y 0")
##   check("hem-thigh", fit.capsule_clearance(hem_pts, hip, knee, 0.075), ">=", 0.0, "no cut")
##
## Rest pose reproduces the mesh to 1 mm (g2 row 149: 6k vertices in 1.5 ms). The death-on-floor
## check is the lowest vertex per body part, not the pelvis, chest and hand bones (prone legs sank
## 7-9 cm while those passed). Ported from the g2 project's tests/probes/qa_npc_lib.gd.

var _cache: Dictionary = {}


## Static arrays of a mesh: vertices, 4 bone indices and weights per vertex, triangles.
func mesh_data(mi: MeshInstance3D) -> Dictionary:
	var key := mi.get_instance_id()
	if _cache.has(key):
		return _cache[key]
	var verts := PackedVector3Array()
	var bones := PackedInt32Array()
	var weights := PackedFloat32Array()
	var tris := PackedInt32Array()
	var m: Mesh = mi.mesh
	for s in m.get_surface_count():
		var arr := m.surface_get_arrays(s)
		var v: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
		var bi: PackedInt32Array = arr[Mesh.ARRAY_BONES] if arr[Mesh.ARRAY_BONES] != null else PackedInt32Array()
		var w: PackedFloat32Array = arr[Mesh.ARRAY_WEIGHTS] if arr[Mesh.ARRAY_WEIGHTS] != null else PackedFloat32Array()
		var per := 8 if v.size() > 0 and bi.size() == v.size() * 8 else 4
		var base := verts.size()
		for i in v.size():
			verts.append(v[i])
			for k in 4:
				if bi.size() >= (i + 1) * per:
					bones.append(bi[i * per + k])
					weights.append(w[i * per + k])
				else:
					bones.append(0)
					weights.append(0.0)
		var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX] if arr[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
		for i in idx:
			tris.append(base + i)
	var d := {"verts": verts, "bones": bones, "weights": weights, "tris": tris}
	_cache[key] = d
	return d


func _bind_bone(mi: MeshInstance3D, sk: Skeleton3D, j: int) -> int:
	var bone := mi.skin.get_bind_bone(j)
	return bone if bone >= 0 else sk.find_bone(mi.skin.get_bind_name(j))


## Skinned vertex positions in skeleton space for the current pose (`subset` = vertex indices).
func skin_points(mi: MeshInstance3D, sk: Skeleton3D, subset: PackedInt32Array = PackedInt32Array()) -> PackedVector3Array:
	var d := mesh_data(mi)
	var skin: Skin = mi.skin
	var mats: Array = []
	mats.resize(skin.get_bind_count())
	for j in skin.get_bind_count():
		mats[j] = sk.get_bone_global_pose(_bind_bone(mi, sk, j)) * skin.get_bind_pose(j)
	var verts: PackedVector3Array = d["verts"]
	var bones: PackedInt32Array = d["bones"]
	var weights: PackedFloat32Array = d["weights"]
	var list := subset if not subset.is_empty() else PackedInt32Array(range(verts.size()))
	var out := PackedVector3Array()
	out.resize(list.size())
	for n in list.size():
		var i := list[n]
		var acc := Vector3.ZERO
		var wsum := 0.0
		for k in 4:
			var w := weights[i * 4 + k]
			if w > 0.0:
				acc += (mats[bones[i * 4 + k]] as Transform3D) * verts[i] * w
				wsum += w
		out[n] = acc / wsum if wsum > 0.0 else verts[i]
	return out


## Vertices whose summed weight on bones whose name starts with `prefix` is >= minw.
func verts_on(mi: MeshInstance3D, sk: Skeleton3D, prefix: String, minw: float) -> PackedInt32Array:
	return _verts_where(mi, sk, func(n: String): return n.begins_with(prefix), minw)


## Vertices whose summed weight on the named bones is >= minw.
func verts_on_set(mi: MeshInstance3D, sk: Skeleton3D, names: Array, minw: float) -> PackedInt32Array:
	return _verts_where(mi, sk, func(n: String): return names.has(n), minw)


func _verts_where(mi: MeshInstance3D, sk: Skeleton3D, pick: Callable, minw: float) -> PackedInt32Array:
	var d := mesh_data(mi)
	var is_b := PackedByteArray()
	is_b.resize(mi.skin.get_bind_count())
	for j in mi.skin.get_bind_count():
		is_b[j] = 1 if pick.call(sk.get_bone_name(_bind_bone(mi, sk, j))) else 0
	var res := PackedInt32Array()
	var bones: PackedInt32Array = d["bones"]
	var weights: PackedFloat32Array = d["weights"]
	for i in (d["verts"] as PackedVector3Array).size():
		var w := 0.0
		for k in 4:
			if is_b[bones[i * 4 + k]] == 1:
				w += weights[i * 4 + k]
		if w >= minw:
			res.append(i)
	return res


func to_world(sk: Skeleton3D, pts: PackedVector3Array) -> PackedVector3Array:
	var out := PackedVector3Array()
	out.resize(pts.size())
	for i in pts.size():
		out[i] = sk.global_transform * pts[i]
	return out


func lowest(pts: PackedVector3Array) -> Vector3:
	var best := Vector3(0, INF, 0)
	for p in pts:
		if p.y < best.y:
			best = p
	return best


## Smallest signed distance of the points to a capsule a-b of radius r (negative = inside):
## a hem against a thigh, a seat against the pelvis, a hand against a rail.
func capsule_clearance(pts: PackedVector3Array, a: Vector3, b: Vector3, r: float) -> float:
	var best := INF
	var ab := b - a
	var len2 := maxf(ab.length_squared(), 1e-12)
	for p in pts:
		var t := clampf((p - a).dot(ab) / len2, 0.0, 1.0)
		best = minf(best, p.distance_to(a + ab * t) - r)
	return best
