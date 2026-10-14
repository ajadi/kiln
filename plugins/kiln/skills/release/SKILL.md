---
name: release
description: "Builds, CI and store release for Kiln games - first standalone build from the vertical slice on, versioning, export per engine (Godot presets and --export-release, Unity build method and build profiles, Unreal BuildCookRun), keeping ref/production/tools/tests/design/research out of builds, build audit, smoke and soak with numbers, crash logs, GitHub Actions, Steam (SteamPipe, store assets with exact sizes, reviews, AI disclosure), itch.io, code signing, age ratings, store copy and credits. Use for any export, build, packaging, CI or publishing task."
user-invocable: false
---

# Release

A build is the product: it must launch outside the editor on a machine without the engine.
Judge it by numbers — audit clean, smoke pass, artefact sizes, soak memory — never by "the
export finished". Nothing is uploaded, published, paid for, signed with a paid certificate or
rated without the user's explicit consent for that platform; autopilot never proxies this.

| Script / file | Use |
|---|---|
| `${CLAUDE_SKILL_DIR}/scripts/build.py audit` | engine from `manifest.md`; Godot: presets exist, each keeps the non-shipping folders out, what it would ship; Unity: build method, profiles, scenes, always-shipped folders; Unreal: `.uproject`, packaging, never-cook folders |
| `build.py build --preset <p> [--debug] [--dry-run]` | the engine's documented build command, printed; fails unless the artefact is new and non-empty; sizes, log errors |
| `build.py smoke <exe> --seconds 60 --log <file>` | launch outside the editor; pass = alive or exit 0, 0 error lines in output and fresh log; kills the process tree |
| `build.py smoke <exe> --seconds 3600 --sample-every 900 --warmup 120` | soak: memory samples, `--max-growth 20` |
| `${CLAUDE_SKILL_DIR}/references/engine-builds.md` | presets, templates, Unity build method (C#), BuildCookRun flags, logs, symbols |
| `${CLAUDE_SKILL_DIR}/references/ci.md` | GitHub Actions per engine, caching, secrets, approvals |
| `${CLAUDE_SKILL_DIR}/references/steam.md` | SteamPipe, store assets, reviews and timelines, AI disclosure |
| `${CLAUDE_SKILL_DIR}/references/distribution.md` | itch.io butler, signing, IARC, store copy, credits and licences |

Engine executables: `--machine ~/.kiln/machine.json` (the default; `godot_exe`, `unity_exe`,
`unreal_exe`) or `--engine-exe`. Output: `export/<preset>/` (git-ignored).

## When to build

| Phase | Build duty |
|---|---|
| 3 tech plan | "hello build" per target platform: templates/SDK/toolchain proven, smoke pass |
| 6 vertical slice | gate: release export of the slice passes audit + smoke; the cold playtest runs that build, not the editor |
| 7–8 content, polish | every batch/round ends with audit → build → smoke; CI on pushes to main |
| 9 release | release candidate, soak, clean-machine launch, store material, signing, user decision |

Export-only failures — resources loaded by string path but filtered out, editor-only autoloads,
debug-only code, case-sensitive paths in the pack, shader compile stutter — show only in builds.

## Versioning

- SemVer: `0.x` until launch, `1.0.0` at launch, PATCH for fixes. One source of truth, changed
  through the engine MCP: Godot `application/config/version`, Unity `bundleVersion`, Unreal
  `ProjectVersion`; `audit` reports it.
- Git tag `v<version>` on the built commit; version + short commit in a menu corner and as the
  first log line, so every report names a build.
- Release candidates keep audit/build/smoke JSON in `production/builds/<version>/`; symbols
  (PDB) stay in `export/<version>/`, never in a shipped depot.
- Pipeline gates read fixed files — save the JSON there (`build.py … > <file>`):
  `production/builds/hello/smoke.json` (Phase 3), `production/builds/slice/audit.json` and
  `slice/smoke.json` (Phase 6), `production/builds/release/smoke.json` and `release/soak.json`
  (Phase 9).

## What never ships

`ref/ production/ tools/ tests/ design/ research/`, editor-only addons, `export/` itself.

| Engine | How |
|---|---|
| Godot | empty `.gdignore` in `ref/ production/ tools/ design/ research/ export/` — not imported, unreachable by include filters, not loadable. `tests/` must stay loadable, so every preset's `exclude_filter` has `tests/*, addons/godot_ai/*, addons/gut/*, addons/gdUnit4/*`. Filters: comma-separated, matched against `res://path` and `path`, case-insensitive, `*` spans folders, `?` never matches `.`; `*.ico`/`*.icns` are always added; dot-files never ship |
| Unity | Kiln folders at the project root, outside `Assets/`. Builds take the profile's scenes + references + everything in `Resources/` and `StreamingAssets/`; Editor folders and test assemblies (`UNITY_INCLUDE_TESTS`) stay out |
| Unreal | folders outside `Content/` never cook. List Maps To Cook (else every map cooks); never cook `/Game/Developers` and test maps |

Proof: `audit` passes before every release build; artefact growth > 20% over the previous build
without a named cause is a leak until explained (working).

## Build → smoke → soak

1. `audit` → `build --dry-run` (read the command) → `build`. The guard allows only these headless
   commands — Godot `--export-*`, Unity `-batchmode -executeMethod <...Build...>`, Unreal `RunUAT
   BuildCookRun` (plus Godot probe/test scripts under `tests/` or `.kiln/tmp/` and `--check-only`
   parse checks); presets and settings change in the open editor through the MCP.
2. `smoke` ≥ 60 s (working) with the game's log: Godot `-- --log-file <abs path>` (4.5+, release
   templates too; default `%APPDATA%\Godot\app_userdata\<project>\logs\godot.log`); Unity
   `-- -logFile <path>` (default `%USERPROFILE%\AppData\LocalLow\<Company>\<Product>\Player.log`);
   Unreal: smoke a Development build (`--debug`) — Shipping logs nothing unless
   `bUseLoggingInShipping`. Benign lines go in `--ignore` with a reason in the task file.
3. Playtester and qa-performance then measure on the build, not in the editor.
4. Release soak: 60 min in gameplay, memory growth ≤ 20%, 0 crashes, 0 new error lines;
   frame-time budget from GAME.md measured on the build.
5. Clean-machine launch before store review: no engine, SDKs or redistributables, install path
   with spaces (Unreal: `-prereqs`).

## Crashes and logs

Make logs findable: path in the README/FAQ, an "open log folder" button in settings. Godot:
rotating logs in `user://logs`, backtrace on crash (official templates have no symbols); Unity:
`Player.log` + `Crashes`; Unreal: `Saved/Logs`, `Saved/Crashes` (Include Crash Reporter). Keep
every shipped build's symbols.

## CI (`references/ci.md`)

Godot: container `barichello/godot-ci:<exact version>`. Unity: `game-ci/unity-builder@v6` with
`buildMethod`. Unreal: self-hosted Windows runner with the engine. Each workflow: checkout with
LFS → cache → audit → build → smoke (headless without GPU) → upload artifact. Secrets only in
GitHub secrets; store uploads only from manual `workflow_dispatch` behind required reviewers.

## Stores

- **Steam**: $100 fee, release ≥ 30 days after paying; Coming Soon ≥ 2 weeks; store and build
  reviews 3–5 business days each (submit ≥ 7 ahead). Capsules header 920×430, small 462×174,
  main 1232×706, vertical 748×896; library 600×900, hero 3840×1240, logo PNG 1280 w / 720 h;
  ≥ 5 gameplay screenshots 1920×1080. steamcmd uploads to a beta branch; default goes live in the
  web UI only. Content survey: disclose AI-generated content players consume.
- **itch.io**: `butler push export/windows <user>/<game>:windows --userversion <v> --if-changed`.
- **Signing**: Windows Azure Artifact Signing or OV (EV no longer skips SmartScreen); macOS
  Developer ID + hardened runtime + notarytool + stapler.
- **Ratings**: IARC (free) for Epic, Google Play, Microsoft, Nintendo, PlayStation, Meta; Steam
  is not in IARC — its content survey yields its ratings.
- **Copy and media** from the build only: first line = what the player does; only features in
  the build; screenshots and trailer from real captures.
- **Credits** from `production/LICENSES.md` plus the engine notice; no licence row, no ship.

## Engines

- **Godot 4.6/4.7**: Godot AI 4.3.0 has no export-preset tool — the user adds presets once in
  Project → Export (templates download there); later edits via `filesystem_manage` on
  `res://export_presets.cfg` with the dialog closed, then restart the editor (presets load at
  start). Never commit `.godot/export_credentials.cfg`. Godot AI strips its game-helper autoload
  from exports.
- **Unity 6**: build profiles through MCP for Unity; the build method is C# in an Editor folder,
  checked with `validate_script`, exits 1 unless `BuildReport.summary.result` is `Succeeded`.
- **Unreal 5.8**: packaging settings through the Unreal MCP, never `Config/*.ini` as text.
