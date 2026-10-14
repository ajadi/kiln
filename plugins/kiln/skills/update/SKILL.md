---
name: update
description: Bring this project up to the current Kiln - refresh the installed plugin, migrate the project's task files and manifest, regenerate Codex agents, and tell the user what changed since the project's Kiln version. Use when the user says to update Kiln, after pulling a new Kiln, or when the session context says the project's framework_version is older than the plugin.
argument-hint: "[status]"
allowed-tools: Read, Glob, Grep, Bash, PowerShell, Edit
---

# /kiln:update

`$ARGUMENTS` = `status` → only step 1.

1. `python "${CLAUDE_SKILL_DIR}/scripts/kiln_update.py" status` from the project root: project
   version, plugin version, the changelog entries in between.
2. Refresh the installed plugin when the Kiln repository is newer than the installed copy
   (Claude Code keeps a cache per version; a same-version update does not refresh it):
   `claude plugin marketplace update kiln`, then `claude plugin uninstall kiln@kiln --scope
   project` and `claude plugin install kiln@kiln --scope project`. Codex: `codex plugin remove
   kiln@kiln` and `codex plugin add kiln@kiln`, then keep it off at user scope (setup §6).
   Plugin changes load when a session starts: tell the user to restart the session, and run
   steps 3-5 in the new one.
3. `python "${CLAUDE_SKILL_DIR}/scripts/kiln_update.py" apply`: runs `pipeline.py migrate`
   (touches lines, gates tables, new manifest keys, `framework_version`).
4. Go through every task the migration marked `touches_source: guessed by migrate - confirm`:
   fix the `touches:` line from what the task builds, delete the marker line, re-run
   `pipeline.py gates TASK-NNN --suggest` and fill or `SKIP:` the new gates rows.
5. `runtimes` includes codex → `python "${CLAUDE_PLUGIN_ROOT}/scripts/codex_agents.py"`.
6. `/kiln:doctor`, then report to the user in their language: version before → after, the
   changelog highlights that matter for this project (new settings they may want, new roles,
   checks that will now run), and the guessed touches you confirmed or changed.
