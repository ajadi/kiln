@tool
extends RefCounted
## Kiln: a 47-tile blob autotile (art-2d autotile.py: atlas.png + terrain.json) as a Godot 4.6/4.7
## TileSet terrain - TERRAIN_MODE_MATCH_CORNERS_AND_SIDES, the 8 peering bits of every tile set
## from terrain.json, so TileMapLayer.set_cells_terrain_connect() and the editor's terrain
## painter pick the right tile. The Godot AI MCP has no terrain op: run it through the engine-godot
## run-once @tool route (references/mcp-and-editor.md), e.g.
##
##   var T = load("res://tools/godot_terrain.gd")
##   var ts: TileSet = T.build("res://art/tiles/grass/atlas.png", "res://art/tiles/grass/terrain.json", "grass")
##   ResourceSaver.save(ts, "res://art/tiles/grass/grass.tres")
##
## or `T.add_to(existing_tileset, ...)` to add the terrain to a TileSet the project already has.

const NEIGHBOUR := {
	"n": TileSet.CELL_NEIGHBOR_TOP_SIDE, "ne": TileSet.CELL_NEIGHBOR_TOP_RIGHT_CORNER,
	"e": TileSet.CELL_NEIGHBOR_RIGHT_SIDE, "se": TileSet.CELL_NEIGHBOR_BOTTOM_RIGHT_CORNER,
	"s": TileSet.CELL_NEIGHBOR_BOTTOM_SIDE, "sw": TileSet.CELL_NEIGHBOR_BOTTOM_LEFT_CORNER,
	"w": TileSet.CELL_NEIGHBOR_LEFT_SIDE, "nw": TileSet.CELL_NEIGHBOR_TOP_LEFT_CORNER,
}


static func _texture(path: String) -> Texture2D:
	if ResourceLoader.exists(path):
		var tex = load(path)
		if tex is Texture2D:
			return tex
	var img := Image.load_from_file(path)
	return ImageTexture.create_from_image(img) if img else null


static func build(atlas_path: String, terrain_path: String, terrain_name: String = "terrain") -> TileSet:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(terrain_path))
	var ts := TileSet.new()
	ts.tile_size = Vector2i(int(data["tile"]), int(data["tile"]))
	add_to(ts, atlas_path, data, terrain_name)
	return ts


## Adds one terrain set (corners and sides) with one terrain and an atlas source to `ts`;
## returns the new source id.
static func add_to(ts: TileSet, atlas_path: String, data: Dictionary, terrain_name: String) -> int:
	var t := int(data["tile"])
	var set_index := ts.get_terrain_sets_count()
	ts.add_terrain_set()
	ts.set_terrain_set_mode(set_index, TileSet.TERRAIN_MODE_MATCH_CORNERS_AND_SIDES)
	ts.add_terrain(set_index)
	ts.set_terrain_name(set_index, 0, terrain_name)
	var src := TileSetAtlasSource.new()
	src.texture = _texture(atlas_path)
	src.texture_region_size = Vector2i(t, t)
	var source_id := ts.add_source(src)
	for tile in data["tiles"]:
		var coords := Vector2i(int(tile["atlas"][0]), int(tile["atlas"][1]))
		src.create_tile(coords)
		var td: TileData = src.get_tile_data(coords, 0)
		td.terrain_set = set_index
		td.terrain = 0
		for bit in NEIGHBOUR:
			td.set_terrain_peering_bit(NEIGHBOUR[bit], 0 if int(tile[bit]) else -1)
	return source_id
