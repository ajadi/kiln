# Phase 9 — Release

Goal: builds that run on the target platforms, an honest report, and the user's decision about
publishing. Nothing is published, uploaded or paid for without the user's explicit consent for
that specific platform.

## Steps

1. **Research** `research/release-<platform>.md`: current store requirements (capsule rules,
   ratings, build formats), turned into a checklist in `production/RELEASE.md`.
2. **Ship gates**:
   - grep the project for debug prints, placeholder text, test keys and `TODO` in shipped paths;
   - `build.py audit`, `build.py build`, `build.py smoke` (release skill) — JSON into
     `production/builds/release/`; soak: `smoke --seconds 3600 --sample-every 900` → `soak.json`;
   - release export with the export preset (Godot `--export-release`, a Unity build method through
     `-batchmode -executeMethod <Build...>`, Unreal `RunUAT BuildCookRun` — builds, not editor work) and launch the build outside the editor;
   - soak test: play/idle 60 minutes, sample memory and frame time at T+0/15/30/45/60 — memory
     growth under ~20%, no new errors;
   - saves from earlier builds load (if the game has saves);
   - licence registry and credits: `python scripts/licenses.py build` writes
     `production/LICENSES.md` from reference manifests, generator provenance, music licences,
     fonts, engine add-ons and `production/licenses-extra.csv`; it fails on any shipping item
     with an unknown or non-commercial licence (the Phase 9 gates read the same table).
3. **Store material** from real captures only: screenshots and trailer cut from gameplay
   recordings; capsule art follows the store's rules (game art, name, nothing else).
4. **Final report** to the user, starting with what is NOT done (SKIP/BLOCKED gates), then what
   ships, known issues, and the publishing options with what each needs from them.

Exit: release checklist filled, builds exported and launched, the user decided where and whether
to publish.
