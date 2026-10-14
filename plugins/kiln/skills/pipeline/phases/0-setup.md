# Phase 0 — Setup

Goal: the studio can work — editors connected for real, project files in place.

1. `/kiln:setup`: project files, engine and dimension chosen with the user, the engine project
   and its MCP plugin, Blender MCP, the Kiln plugin enabled for this project.
2. Restart the session, then `/kiln:doctor`: real calls to Blender and the engine editor, hooks
   active.
3. `python pipeline.py init` (writes the engine's gates), then `status`.
4. Show the user the engine editor with the project open and Blender with the MCP server running;
   ask them to confirm they see both (user gate).
5. Record machine facts that later phases rely on (engine version, renderer, GPU, target
   resolution and frame rate) in `GAME.md` → Platform and budgets.

Exit: all Phase 0 gates closed. Problems here are blockers — do not start design work on a
broken setup.
