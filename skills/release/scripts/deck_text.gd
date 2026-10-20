extends SceneTree
## Kiln Steam Deck text check (Godot 4.6/4.7). Loads UI scenes headless and reports the on-screen
## pixel size of every text-bearing Control at the Deck's 1280x800, with the project's stretch
## settings applied. store_check.py deck runs it and measures glyph heights from the font files.
##
##   godot --headless --path <project> -s .kiln/tmp/deck_text.gd -- --scene res://ui/menu.tscn
##         [--scene ...] --out <abs json> [--width 1280 --height 800]
##
## Hidden Controls are reported too (visible=false): a pause menu or a dialog is hidden when the
## scene loads and still has to be readable when it opens.

var _scenes: PackedStringArray = []
var _out := ""
var _w := 1280.0
var _h := 800.0


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var i := 0
	while i < args.size():
		match args[i]:
			"--scene": _scenes.append(args[i + 1]); i += 1
			"--out": _out = args[i + 1]; i += 1
			"--width": _w = float(args[i + 1]); i += 1
			"--height": _h = float(args[i + 1]); i += 1
		i += 1
	_run.call_deferred()


func stretch_scale() -> float:
	var bw := float(ProjectSettings.get_setting("display/window/size/viewport_width", 1152))
	var bh := float(ProjectSettings.get_setting("display/window/size/viewport_height", 648))
	var mode := str(ProjectSettings.get_setting("display/window/stretch/mode", "disabled"))
	var aspect := str(ProjectSettings.get_setting("display/window/stretch/aspect", "keep"))
	var factor := float(ProjectSettings.get_setting("display/window/stretch/scale", 1.0))
	var integer := str(ProjectSettings.get_setting("display/window/stretch/scale_mode", "fractional")) == "integer"
	if mode == "disabled":
		return factor
	var s := _h / bh if aspect == "ignore" else minf(_w / bw, _h / bh)
	if integer:  # Godot never scales below 1 in integer mode (bug hunt 2026-10-20, checked live)
		s = maxf(1.0, floorf(s))
	return s * factor


func font_file(f: Font) -> String:
	if f is FontVariation and (f as FontVariation).base_font:
		f = (f as FontVariation).base_font
	if f == ThemeDB.fallback_font or f == null:
		return "default"
	if f is SystemFont:
		return "system:" + ",".join((f as SystemFont).font_names)
	var path := f.resource_path
	if path.get_extension().to_lower() in ["ttf", "otf", "woff", "woff2", "ttc", "pfb", "pfm"]:
		return ProjectSettings.globalize_path(path)
	return "unknown:" + path


func text_of(c: Control) -> String:
	for prop in ["text", "placeholder_text"]:
		if prop in c and str(c.get(prop)) != "":
			return str(c.get(prop))
	if c is ItemList and (c as ItemList).item_count > 0:
		return (c as ItemList).get_item_text(0)
	if c is TabBar and (c as TabBar).tab_count > 0:
		return (c as TabBar).get_tab_title(0)
	if c is ProgressBar and (c as ProgressBar).show_percentage:
		return "100%"
	if c is Tree and (c as Tree).get_root() != null:
		return "tree"
	return ""


## [[size, font, what]] for one Control: the theme size, a LabelSettings size, BBCode sizes.
func sizes_of(c: Control) -> Array:
	if c is Label and (c as Label).label_settings:
		var ls := (c as Label).label_settings
		return [[ls.font_size, ls.font if ls.font else c.get_theme_font("font"), "label_settings"]]
	if c is RichTextLabel:
		var out := [[c.get_theme_font_size("normal_font_size"), c.get_theme_font("normal_font"), "normal_font_size"]]
		var rx := RegEx.create_from_string("\\[font_size=(\\d+)\\]")
		for m in rx.search_all((c as RichTextLabel).text):
			out.append([int(m.get_string(1)), c.get_theme_font("normal_font"), "[font_size]"])
		return out
	return [[c.get_theme_font_size("font_size"), c.get_theme_font("font"), "font_size"]]


func walk(n: Node, scale: float, scene: String, rows: Array) -> void:
	if n is Control:
		var c := n as Control
		var text := text_of(c)
		if text != "":
			var canvas := c.get_global_transform_with_canvas().get_scale().y
			for s in sizes_of(c):
				rows.append({"scene": scene, "node": str(c.owner.get_path_to(c) if c.owner else c.get_path()),
					"type": c.get_class(), "text": text.substr(0, 40), "visible": c.is_visible_in_tree(),
					"font_size": int(s[0]), "source": s[2], "px": float(s[0]) * canvas * scale,
					"font": font_file(s[1])})
	for child in n.get_children():
		walk(child, scale, scene, rows)


func _run() -> void:
	var scale := stretch_scale()
	var rows := []
	var label3d := 0
	var missing := []
	for path in _scenes:
		var packed := load(path) as PackedScene
		if packed == null:
			missing.append(path)
			continue
		var inst := packed.instantiate()
		root.add_child(inst)
		for k in 3:  # _ready and the deferred calls that fill menus
			await process_frame
		walk(inst, scale, path, rows)
		label3d += inst.find_children("*", "Label3D", true, false).size()
		inst.queue_free()
		await process_frame
	var data := {"screen": [_w, _h], "stretch_scale": scale, "rows": rows,
		"label3d": label3d, "missing": missing}
	var f := FileAccess.open(_out, FileAccess.WRITE)
	f.store_string(JSON.stringify(data, " "))
	f.close()
	quit(0)
