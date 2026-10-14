---
name: tools
description: Find, install, verify, update and remove the tools a Kiln project needs - the engine at the exact version, Blender, MCP servers and editor add-ons, Python runtimes and venvs, uv, git-lfs, CUDA or compilers when a tool needs them, generators and audio tools - from a committed per-project tool manifest and a per-machine registry with a user tools root, with tools_check.py detect / verify. Setup and doctor call it. Load when a tool is missing, a version must change, or before the first run on a new machine.
user-invocable: false
---

# Tools: one manifest per project, one registry per machine

On g2 every tool was found or installed by hand: Godot and Blender sat in a tools folder setup did
not look in, PyPI `blender_mcp` was a different server with the same name and version, the Godot
AI addon had no download source, Blender's add-on needed `--online-mode`, and a 3D generator
needed prebuilt Windows wheels instead of MSVC + CUDA.

## 1. Files

- `production/tools.json` (committed): what the project needs — per tool `name`, exact `version`,
  `find` (executable names), `verify` (command with `{path}`), `expect` (text the verify output
  must contain: the version, or the MCP tool names a probe prints), `source` (official release URL
  for that version), `install` (one line: method and target folder), `licence`. No machine paths.
- `${CLAUDE_PLUGIN_DATA}/machine.json` (per machine, outside every project): `tools_root` (the
  user's tools folder, asked once in setup), and `tools: {name: path}` for what you found or
  installed. Venvs, caches and downloads go under `<tools_root>` (`venvs/<name>`, `cache/`,
  `downloads/`), or `~/.local/share/kiln/` when there is no tools root.

## 2. Detect, install, verify

1. `python scripts/tools_check.py detect production/tools.json --tools-root <tools_root>`: PATH,
   then the tools root, then the machine registry.
2. Missing or wrong version → install it yourself (protocol: do it yourself), into
   `<tools_root>/<Tool>/<version>/`, without admin rights when there is a portable build:
   - download from the manifest `source` only (the official release page of that version;
     check the published checksum when there is one); never a same-named package from another
     index (the PyPI `blender_mcp` trap);
   - prefer prebuilt binaries and wheels over building (a CUDA extension without a wheel for this
     Python means another Python version, not installing MSVC + CUDA);
   - Python tools: a venv per tool under `<tools_root>/venvs/`; record the interpreter version.
3. Record the path in `machine.json` `tools`.
4. `python scripts/tools_check.py verify production/tools.json --tools-root <tools_root>`: every
   tool runs and prints the expected version. MCP servers: verify = a real probe (setup step 8,
   `mcp_check.py`), not "Connected".
5. Report a table: tool · version · where · status · licence.

## 3. Update and remove

- Update = install the new version next to the old one, switch the manifest version and the
  registry path, verify, then remove the old folder. An engine update is the user's decision (it
  changes project files); a patch release of a tool the project already pins is yours.
- Remove only what Kiln installed (its path in `machine.json` under the tools root). Never kill
  processes by image name to free a file; stop the PID you started.

## 4. Known sources (verify the version you need)

| Tool | Source | Note |
|---|---|---|
| Godot | `github.com/godotengine/godot-builds/releases` (tag `<version>-stable`) | portable zip; the console exe for headless runs |
| Godot AI | server: PyPI `godot-ai`; addon: release asset `godot-ai-v4-plugin.zip` of `hi-godot/godot-ai` tag `v<version>` | `godot-ai-plugin.zip` is the Migration plugin |
| Blender Lab MCP | `projects.blender.org/lab/blender_mcp` releases | server `uv tool install <checkout>/mcp`; add-on via `blender --command extension install-file -r user_default -e <zip>`; Blender needs `--online-mode` |
| uv | `github.com/astral-sh/uv/releases` | standalone binary |
| git-lfs | `github.com/git-lfs/git-lfs/releases` | `git lfs install --local` per repo |
