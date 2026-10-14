---
name: tools
description: Find, install, verify and offer the tools a Kiln project needs - engines, Blender, uv, git-lfs, Ollama, the MCP servers and add-ons, AI generators - from a catalog of official sources with checksums, into the machine's tools folder (tools_root), with one confirmation from the user; Unity and Unreal get a short instruction. Setup, doctor and kiln-start use it. Load when a tool is missing, a version must change, a generator is wanted, or before the first run on a new machine.
user-invocable: false
---

# Tools: find everything, install with one yes, offer what helps

`scripts/tools_check.py` (stdlib) and `catalog.json` (official sources, checked versions). The
machine config is `~/.kiln/machine.json`: `tools_root` (the folder every tool, venv, download and
cache goes to) and what was found or installed. Both Kiln plugins and Codex read the same file.

## 1. tools_root first

`tools_check.py root` shows it. Set → use it, never ask again; it changes only when the user asks.
Not set → ask the user once (kiln-start does this at the first install; setup asks if it is still
missing): a folder
they already keep tools in, or the suggested `~/kiln-tools`. Then `tools_check.py root --set
<folder>`. Never install anything before it is set.

## 2. Plan: look everywhere, then one question

`tools_check.py plan --project .` reads the manifest (engine, dimension, `llm_npc`,
`model_generators`) and, for every tool the project needs, searches the machine registry, PATH,
the tools root and the usual install folders before calling it missing. Each row gets an action:

| action | What you do |
|---|---|
| none | found: it is used as it is (an installed version is never replaced without the user) |
| install | Kiln installs it: Godot, Blender, uv, git-lfs, Ollama (`llm_npc=local`), the Godot AI server and addon, the Blender Lab MCP server and add-on |
| project | written into the project by setup: MCP for Unity (Packages/manifest.json), Unreal MCP (.uproject plugins) |
| manual | Unity and Unreal: accounts and licences; give the user the row's short instruction and wait |

Ask the user **once**, with the plan's `confirm` line and a table (tool, size, licence, where it
goes): "Install these into <tools_root>?" Installing software, MCP servers and editor plug-ins is
always the user's yes, also on autopilot with `user_gates=proxy` (run skill hard stops).

## 3. Install, register, verify

After the yes, per tool: `tools_check.py install <tool> --yes`. It downloads from the catalog's
source, checks the published sha256 (GitHub asset digests, Blender's `.sha256` file), unpacks into
`<tools_root>/<tool>/<version>/`, finds the executable, verifies its version and records it. A
checksum mismatch installs nothing. uv-based tools (Godot AI, Blender MCP) go to
`<tools_root>/uv-tools` with launchers in `<tools_root>/bin`; install uv first.
For MCP servers the result has `register`: run the Claude Code command (and the Codex one when
`runtimes` includes codex), then the `after` step (Blender add-on install with
`--command extension install-file`, the Godot addon link, Ollama's model pull), and record each
with `tools_check.py mark <tool> --mcp claude|codex` / `--addon "<what, where>"`. MCP tools load at
session start: tell the user to restart the session, then `/kiln:doctor`.
`tools_check.py installed` lists everything Kiln put on this machine (version, place, size, check,
MCP registrations, add-ons, generators); setup ends with it.

## 4. AI generators: explain, compare, install on a yes

Only when `model_generators` is `local` or `remote`. `tools_check.py offers --project .` compares
the catalog's generators against this machine's GPU (nvidia-smi) and the policy: what each makes,
GPU memory, licence (commercial or not), size, quality, speed, and whether it fits. Show the user
that table with one recommendation (the best one that fits, licence first), say why a generator
helps this project (organic props, statues, crowds from photos; hard-surface and damageable parts
are modelled by hand anyway, image-to-model skill), and what it costs (disk, GPU minutes, clean-up
work). On a yes: `tools_check.py offer-install <offer> --yes` (pinned commit, a uv venv, its
requirements; weights download on the first run). `remote`: nothing is installed here; the
gpu-server skill sets up the rented server and runs it through `gpu_job.py`. Never offer what
the catalog lists under `not_offered` (licence traps).

## 5. Project pins (optional)

A project may pin versions in `production/tools.json` (`{"tools": [{"name", "version", "find",
"verify", "expect", "source", "install", "licence"}]}`); `tools_check.py detect` / `verify` check
them, and `install <tool> --version <v>` installs a pinned version.

## 6. Update and remove

Install the new version next to the old one, switch the registry with the user's yes, verify, then
remove the old folder. Remove only what Kiln installed (paths under tools_root in machine.json).
Never kill processes by image name to free a file; stop the PID you started.
