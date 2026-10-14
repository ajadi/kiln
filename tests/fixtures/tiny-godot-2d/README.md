# Kiln smoke run (live, ~1 hour)

Copy this folder somewhere outside the repo, open Godot 4.6+ and Blender with their MCP servers
running, start Claude Code there, then:

1. `/kiln:setup` (engine godot, dimension 2d, runtimes claude) — the MCP check must say ready;
   `/kiln:doctor` must pass, including the Blender review-script check.
2. `/kiln:concept brief.md` with short answers → `GAME.md`, mechanics, scope.
3. `/kiln:plan` → at least: a mover gym (gameplay-dev → qa-feel), a coin sprite set
   (artist-2d → sprite_qa), a pickup sound (sound-designer → audio_check), title/pause/win UI
   (ui-designer → qa-readability).
4. `/kiln:run` each task through its acceptor and the verifier.
5. Release check: `release` skill `build.py audit` and `smoke` on an exported build.
6. `pipeline.py status` shows phases advancing; `licenses.py build` passes.

Record what failed in `memory/known-issues.md` of the copy and as issues against Kiln.
