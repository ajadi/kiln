"""Tests for plugins/kiln/skills/engine-godot/scripts/import_edit.py (stdlib only).

g2 rows 4, 61, 93, 106, 107, 134, 145: import options (audio loop/bpm, clip loop modes, material
extraction, per-node cast_shadow, Animation Library import) had no sanctioned route.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "engine-godot", "scripts", "import_edit.py")

OGG = '''[remap]

importer="oggvorbisstr"
type="AudioStreamOggVorbis"
uid="uid://c1"
path="res://.godot/imported/calm.ogg-9f.oggvorbisstr"

[deps]

source_file="res://assets/music/calm.ogg"
dest_files=["res://.godot/imported/calm.ogg-9f.oggvorbisstr"]

[params]

loop=false
loop_offset=0
bpm=0
beat_count=0
bar_beats=4
'''

GLB = '''[remap]

importer="scene"
importer_version=1
type="PackedScene"
uid="uid://b2"
path="res://.godot/imported/npc.glb-77.scn"

[deps]

source_file="res://assets/npc/npc.glb"
dest_files=["res://.godot/imported/npc.glb-77.scn"]

[params]

nodes/root_type=""
nodes/root_name=""
materials/extract=0
animation/import=true
import_script/path=""
_subresources={
"materials": {
"Skin": {
"use_external/enabled": false
}
}
}
gltf/naming_version=2
'''


def project(name, text, source):
    root = tempfile.mkdtemp(prefix="kiln-import-")
    src = os.path.join(root, *source.split("/"))
    os.makedirs(os.path.dirname(src), exist_ok=True)
    with open(src, "wb") as fh:
        fh.write(b"data")
    old = time.time() - 3600
    os.utime(src, (old, old))
    path = src + ".import"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path, src


def run(*args):
    proc = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                          timeout=20)
    return proc.returncode, proc.stdout, proc.stderr


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def get(path):
    code, out, err = run("get", path)
    assert code == 0, err
    return json.loads(out)


class ImportEditTests(unittest.TestCase):
    def test_audio_loop_and_beats(self):
        path, src = project("calm", OGG, "assets/music/calm.ogg")
        before = os.path.getmtime(src)
        code, out, err = run("set", path, "--param", "loop=true", "--param", "bpm=96",
                             "--param", "beat_count=64")
        self.assertEqual(code, 0, err)
        info = get(path)
        self.assertEqual(info["params"]["loop"], "true")
        self.assertEqual(info["params"]["bpm"], "96")
        self.assertEqual(info["params"]["bar_beats"], "4")      # untouched
        self.assertIn('source_file="res://assets/music/calm.ogg"', read(path))
        # the editor skips a reimport when the source mtime did not change (g2 row 93)
        self.assertGreater(os.path.getmtime(src), before)

    def test_clip_loop_material_extract_and_cast_shadow(self):
        path, _ = project("npc", GLB, "assets/npc/npc.glb")
        code, _, err = run("set", path, "--param", "materials/extract=2",
                           "--sub", "animations::walk::settings/loop_mode=1",
                           "--sub", "nodes::PATH:Water/Surface::mesh_instance/cast_shadow=0",
                           "--sub", 'materials::Hair::use_external/path="res://m/hair.tres"',
                           "--sub", "materials::Hair::use_external/enabled=true")
        self.assertEqual(code, 0, err)
        info = get(path)
        sub = info["subresources"]
        self.assertEqual(info["params"]["materials/extract"], "2")
        self.assertEqual(sub["animations"]["walk"]["settings/loop_mode"], 1)
        self.assertEqual(sub["nodes"]["PATH:Water/Surface"]["mesh_instance/cast_shadow"], 0)
        self.assertEqual(sub["materials"]["Hair"],
                         {"use_external/path": "res://m/hair.tres", "use_external/enabled": True})
        self.assertEqual(sub["materials"]["Skin"], {"use_external/enabled": False})  # kept
        self.assertIn("gltf/naming_version=2", read(path))

    def test_import_as_animation_library(self):
        path, _ = project("clips", GLB, "assets/npc/clips.glb")
        code, _, err = run("set", path, "--importer", "animation_library")
        self.assertEqual(code, 0, err)
        text = read(path)
        self.assertIn('importer="animation_library"', text)
        self.assertIn('type="AnimationLibrary"', text)

    def test_refuses_what_it_cannot_parse(self):
        odd = GLB.replace('"use_external/enabled": false', '"x": Vector3(0, 1, 0)')
        path, _ = project("odd", odd, "assets/npc/odd.glb")
        code, _, err = run("set", path, "--sub", "animations::a::settings/loop_mode=1")
        self.assertNotEqual(code, 0)
        self.assertIn("Vector3", err)
        self.assertEqual(read(path), odd)

    def test_not_an_import_file(self):
        code, _, err = run("set", "scenes/a.tscn", "--param", "x=1")
        self.assertNotEqual(code, 0)
        self.assertIn(".import", err)


if __name__ == "__main__":
    unittest.main()
