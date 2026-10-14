# CI — GitHub Actions per engine

Read when adding or fixing a workflow under `.github/workflows/`. CI runs the same three steps as
a local release: audit → build → smoke, then uploads the artefact. Copy `build.py` into the
project as `tools/release/build.py` (non-shipping folder) so CI does not need the plugin; note the
Kiln version it came from in its first comment line and refresh it when Kiln updates.

Action versions below are the latest majors as of Oct 2026 (checkout v7, cache v6,
upload-artifact v7, download-artifact v8); pin third-party actions to a commit SHA.

## Rules for every workflow

- Triggers: `push` to `main` and `pull_request` build and smoke; anything that uploads to a
  store runs only on `workflow_dispatch`, in a job with `environment: <store>` whose required
  reviewer is the user (GitHub environment protection). Publishing is the user's decision.
- `actions/checkout` with `lfs: true` when the project uses Git LFS; cache LFS objects keyed on
  `git lfs ls-files -l` output if checkouts are slow.
- Secrets only in repository/environment secrets; never echoed, never written into files that
  are uploaded as artifacts. Rotate any secret that appears in a log.
- `actions/upload-artifact` with `retention-days: 14` for builds; keep symbols as a separate
  artifact (or in release storage), never inside the shipped folder.
- The workflow fails when `build.py` prints `"verdict": "fail"` (exit code 1).
- GitHub-hosted runners have no GPU: smoke there is headless (logic, autoloads, script errors);
  the rendering smoke and the soak run on a real machine before release.

## Godot

The `barichello/godot-ci:<version>` image (MIT; tags follow Godot releases, e.g. `4.7.2`) holds
the editor at `/usr/local/bin/godot`, export templates under
`/root/.local/share/godot/export_templates/<ver>.stable`, butler and `osslsigncode`; it has no
Python, so the audit runs in its own job. For C# projects use `chickensoft-games/setup-godot`.

```yaml
name: build
on:
  push: { branches: [main] }
  pull_request:
  workflow_dispatch:
jobs:
  audit:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      - run: python3 tools/release/build.py audit --engine godot
  export:
    needs: audit
    runs-on: ubuntu-24.04
    container: barichello/godot-ci:4.7.2          # exactly the project's editor version
    steps:
      - uses: actions/checkout@v7
        with: { lfs: true }
      - uses: actions/cache@v6
        with:
          path: .godot/imported
          key: godot-import-${{ hashFiles('**/*.import') }}
      - name: Export Windows and Linux
        run: |
          mkdir -p export/windows export/linux && touch export/.gdignore
          godot --headless --path . --export-release "Windows Desktop" "$PWD/export/windows/game.exe"
          godot --headless --path . --export-release "Linux" "$PWD/export/linux/game.x86_64"
      - name: Headless smoke (Linux build, 600 frames)
        shell: bash
        run: |
          set -o pipefail
          chmod +x export/linux/game.x86_64
          export/linux/game.x86_64 --headless --quit-after 600 2>&1 | tee smoke.log
          if grep -E "^(USER |USER SCRIPT |SCRIPT )?ERROR:" smoke.log; then exit 1; fi
      - uses: actions/upload-artifact@v7
        with: { name: windows, path: export/windows, retention-days: 14 }
```

The container runs as root; if the export cannot find templates, copy them to
`$HOME/.local/share/godot/export_templates/` as godot-ci's own example workflow does.
`--headless` is required where there is no GPU (Godot command-line docs). Preset names
(`"Windows Desktop"`, `"Linux"`) are whatever `export_presets.cfg` says.

## Unity

`game-ci/unity-builder` (MIT; latest v6.0.0, Sept 2026, a wrapper over the game-ci CLI; GameCI
docs still show `@v4` examples). Personal licence: `UNITY_LICENSE` (contents of the activated
`.ulf`), `UNITY_EMAIL`, `UNITY_PASSWORD`; Pro adds `UNITY_SERIAL`. Builds land in `build/` by
default.

```yaml
jobs:
  build:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
        with: { lfs: true }
      - uses: actions/cache@v6
        with:
          path: Library
          key: Library-Win64-${{ hashFiles('Assets/**', 'Packages/**', 'ProjectSettings/**') }}
          restore-keys: Library-Win64-
      - uses: game-ci/unity-builder@v6
        env:
          UNITY_LICENSE: ${{ secrets.UNITY_LICENSE }}
          UNITY_EMAIL: ${{ secrets.UNITY_EMAIL }}
          UNITY_PASSWORD: ${{ secrets.UNITY_PASSWORD }}
        with:
          targetPlatform: StandaloneWindows64
          buildMethod: KilnRelease.KilnBuild.Build
          customParameters: -kilnPreset StandaloneWindows64 -kilnOut build/StandaloneWindows64/game.exe
      - uses: actions/upload-artifact@v7
        with: { name: windows, path: build/StandaloneWindows64, retention-days: 14 }
```

Inputs worth knowing: `buildProfile` (path to a build profile), `projectPath`, `versioning`,
`manualExit` (drops `-quit`; the method must call `EditorApplication.Exit`), `enableGpu`
(otherwise `-nographics`). Unity tests: `game-ci/unity-test-runner` (v4). Exclude
`*_BurstDebugInformation_DoNotShip` and `*_BackUpThisFolder_ButDontShipItWithYourGame` from
uploads.

## Unreal

No maintained public action builds Unreal on GitHub-hosted runners (the engine is tens of GB and C++
projects need Visual Studio). Use a self-hosted Windows runner with the engine installed; Epic's Linux
container images need an Epic account linked to the GitHub organisation (UNVERIFIED for 5.8
availability).

```yaml
jobs:
  package:
    runs-on: [self-hosted, windows, unreal-5.8]
    steps:
      - uses: actions/checkout@v7
        with: { lfs: true, clean: false }        # keep Intermediate/ and DerivedDataCache/
      - run: python tools/release/build.py audit
      - run: python tools/release/build.py build --preset Win64 --engine-exe "${{ vars.UE_ROOT }}/Engine/Build/BatchFiles/RunUAT.bat"
      - uses: actions/upload-artifact@v7
        with: { name: win64, path: export/win64-shipping, retention-days: 14 }
```

Keep the derived-data cache on the runner disk between runs (`clean: false` or a shared DDC
folder); a cold cook of a mid-size project takes much longer than a warm one.

## Store deploy jobs (manual, approved)

```yaml
  steam:
    needs: export
    if: github.event_name == 'workflow_dispatch'
    environment: steam                      # required reviewer: the user
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/download-artifact@v8
        with: { name: windows, path: build/windows }
      - uses: game-ci/steam-deploy@v3
        with:
          username: ${{ secrets.STEAM_USERNAME }}
          password: ${{ secrets.STEAM_PASSWORD }}
          configVdf: ${{ secrets.STEAM_CONFIG_VDF }}   # base64 config.vdf after one Steam Guard login
          appId: 1234560
          buildDescription: v${{ github.ref_name }}
          rootPath: build
          depot1Path: windows
          releaseBranch: beta                      # never the default branch from CI
  itch:
    needs: export
    if: github.event_name == 'workflow_dispatch'
    environment: itch
    runs-on: ubuntu-24.04
    container: barichello/godot-ci:4.7.2           # has butler on PATH
    steps:
      - uses: actions/download-artifact@v8
        with: { name: windows, path: build/windows }
      - run: butler push build/windows user/game:windows --userversion "${{ github.ref_name }}" --if-changed
        env: { BUTLER_API_KEY: "${{ secrets.BUTLER_API_KEY }}" }
```

`game-ci/steam-deploy` (MIT, v3.2.1) now shells out to the game-ci CLI and requires `password`
in every mode; authentication is either a base64 `config.vdf` from a machine that passed Steam
Guard once, or a TOTP from the builder account's shared secret. Use a dedicated builder account
with only "Edit App Metadata" and "Publish App Changes To Steam" for this app.

Windows signing in CI: `azure/artifact-signing-action@v2` (formerly trusted-signing-action;
OIDC login through `azure/login`), inputs `endpoint`, `signing-account-name`,
`certificate-profile-name`, `files-folder`, `files-folder-filter: exe,dll`, `file-digest:
SHA256`, `timestamp-rfc3161: http://timestamp.acs.microsoft.com`, `timestamp-digest: SHA256`.
Sign before the store upload, verify with `signtool verify /pa /v`.
