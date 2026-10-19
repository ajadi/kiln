@tool
extends EditorScenePostImport
## Kiln: an authored LOD chain (<mesh>_LOD0, _LOD1, ... nodes from blender-modeling
## lod_build.py) becomes Godot visibility ranges at import. Each level's switch size comes from
## its glTF extras (kiln_lod_screen: the share of the screen height the object's bounding
## diameter covers when the level may show; kiln_lod_diameter_m), converted to a distance with
## the game camera's vertical FOV: d = D / (2 * s * tan(fov / 2)). Visibility ranges measure to
## the AABB centre, so each boundary is d + D / 2 (the nearest surface never comes closer than
## d). Hysteresis margins MARGIN of the distance, fade off (asset-pipeline "LOD chain").
## Set it as the file's import script and switch the automatic LODs off for that file
## (engine-godot import_edit.py: import_script/path and meshes/generate_lods=false).

const FOVY_DEG := 75.0  # the game camera's vertical FOV (Camera3D.fov, keep_height) - GAME.md
const MARGIN := 0.05
const CULL_DISTANCE := 0.0  # > 0: the last level disappears beyond this distance (metres)

var _lod := RegEx.create_from_string("^(.*?)_LOD(\\d+)$")


func _post_import(scene: Node) -> Object:
	var chains := {}
	_collect(scene, chains)
	for base in chains:
		_apply(base, chains[base])
	return scene


func _collect(node: Node, chains: Dictionary) -> void:
	if node is GeometryInstance3D:
		var m := _lod.search(String(node.name))
		if m:
			var base := m.get_string(1)
			if not chains.has(base):
				chains[base] = {}
			chains[base][int(m.get_string(2))] = node
	for child in node.get_children():
		_collect(child, chains)


func _extras(node: Node) -> Dictionary:
	return node.get_meta("extras", {}) if node.has_meta("extras") else {}


func _apply(base: String, levels: Dictionary) -> void:
	var order := levels.keys()
	order.sort()
	if order.size() < 2:
		return
	var lod0: GeometryInstance3D = levels[order[0]]
	var diameter := float(_extras(lod0).get("kiln_lod_diameter_m", 0.0))
	if diameter <= 0.0 and lod0 is MeshInstance3D and lod0.mesh:
		diameter = lod0.mesh.get_aabb().size.length()
	var half_tan := tan(deg_to_rad(FOVY_DEG) / 2.0)
	var bounds := [0.0]
	for i in range(1, order.size()):
		var screen := float(_extras(levels[order[i]]).get("kiln_lod_screen", 0.0))
		if screen <= 0.0:
			push_warning("kiln_lod_ranges: %s_LOD%d has no kiln_lod_screen extra; chain left as is" % [base, order[i]])
			return
		bounds.append(diameter / (2.0 * screen * half_tan) + diameter / 2.0)
	for i in order.size():
		var node: GeometryInstance3D = levels[order[i]]
		node.visibility_range_begin = bounds[i]
		node.visibility_range_begin_margin = bounds[i] * MARGIN
		var end: float = bounds[i + 1] if i + 1 < order.size() else CULL_DISTANCE
		node.visibility_range_end = end
		node.visibility_range_end_margin = end * MARGIN
		node.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED
		node.set_meta("kiln_lod_level", order[i])
