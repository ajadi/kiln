---
name: update
description: Bring this project, or every Kiln project on this machine (`all`), up to the current Kiln - refresh the installed plugin (Claude Code, Codex, Gemini CLI, Copilot CLI or OpenCode), migrate task files and manifests, regenerate the Codex and OpenCode roles, and tell the user what changed since each project's Kiln version. Projects are found by themselves (every Kiln session records its project in ~/.kiln/projects.json; `--scan <folder>` finds ones never opened). Use when the user says to update Kiln (here or everywhere), after pulling a new Kiln, or when the session context says this or other projects are older than the plugin.
argument-hint: "[status | all [--scan <folder>]]"
allowed-tools: Read, Glob, Grep, Bash, PowerShell, Edit
---

# /kiln:update

`$ARGUMENTS` = `status` → only step 1. `all` → the "Every project" section instead.

1. `python "${extensionPath}${/}skills${/}update/scripts/kiln_update.py" status` from the project root: project
   version, plugin version, the changelog entries in between.
2. Refresh the installed plugin when the Kiln repository is newer than the installed copy, in
   the agent this session runs in:

   | Agent | Refresh |
   |---|---|
   | Claude Code | `claude plugin marketplace update kiln`, then `claude plugin uninstall kiln@kiln --scope project` and `claude plugin install kiln@kiln --scope project` (a cache per version; a same-version update does not refresh it) |
   | Codex | `codex plugin marketplace upgrade kiln` replaces the installed copy with the new version (checked live, Codex 0.163); a same-version change needs `codex plugin remove kiln@kiln` + `codex plugin add kiln@kiln`; keep it off at user scope (setup §6) |
   | Gemini CLI | `gemini extensions update kiln` |
   | Copilot CLI | `copilot plugin marketplace update kiln`, then `copilot plugin update kiln` (GitHub's CLI plugin reference; not run live yet) |
   | OpenCode | `git -C <kiln clone> pull` (the clone `opencode_setup.py` was run from) |

   Plugin changes load when a session starts: tell the user to restart the session, and run
   steps 3-5 in the new one.
3. `python "${extensionPath}${/}skills${/}update/scripts/kiln_update.py" apply`: runs `pipeline.py migrate`
   (touches lines, gates tables, new manifest keys, `framework_version`).
4. Go through every task the migration marked `touches_source: guessed by migrate - confirm`:
   fix the `touches:` line from what the task builds, delete the marker line, re-run
   `pipeline.py gates TASK-NNN --suggest` and fill or `SKIP:` the new gates rows.
5. Regenerate what the other runtimes keep as copies: `runtimes` includes codex → `python
   "${extensionPath}/scripts/codex_agents.py"` (roles in `.codex/agents/`); opencode →
   `python "${extensionPath}/scripts/opencode_setup.py" --project .` (the plugin file and the
   roles in `.opencode/`; the skills are links and follow the clone). Gemini CLI and Copilot CLI
   keep nothing per project: their roles come with the extension / plugin.
6. `/kiln:doctor`, then report to the user in their language: version before → after, the
   changelog highlights that matter for this project (new settings they may want, new roles,
   checks that will now run), and the guessed touches you confirmed or changed.

## Every project (`/kiln:update all`)

1. Refresh the plugin once (step 2's marketplace update).
2. `python "${extensionPath}${/}skills${/}update/scripts/kiln_update.py" projects [--scan <folder>]`: every Kiln
   project this machine knows (sessions record their project; `--scan` a projects folder to find
   ones never opened since 0.7.4), with its version and whether it is behind. Folders that are
   gone are forgotten.
3. Show the user one table (project, path, version → new version) and ask once.
4. On the yes: `kiln_update.py apply-all --yes` migrates every project behind in its own folder;
   then in each of them, by its `runtimes`: claude → `claude plugin install kiln@kiln --scope
   project` (the project's installed copy; uninstall first when the same version is cached);
   codex → `scripts/codex_agents.py`; opencode → `scripts/opencode_setup.py --project .`;
   gemini and copilot need nothing per project.
5. Report: updated, failed (with the migrate output), the guessed `touches:` lines each project
   must confirm in its next session. Nothing is committed in the other projects: say so, and
   that their next session shows the changes.

