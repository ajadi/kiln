# Engine builds — presets, commands, logs, symbols

Read when setting up or debugging a build for one engine. Commands are the ones `build.py build`
runs; check them with `--dry-run` first.

## Godot 4.6/4.7

**Preset** (`export_presets.cfg`, ConfigFile text, safe to commit). What `build.py audit` expects:

```ini
[preset.0]
name="Windows Desktop"
platform="Windows Desktop"
export_filter="all_resources"
include_filter=""
exclude_filter="tests/*, addons/godot_ai/*, addons/gut/*, addons/gdUnit4/*"
export_path="export/windows/<game>.exe"

[preset.0.options]
binary_format/embed_pck=true
debug/export_console_wrapper=1
shader_baker/enabled=true
```

- Filter modes: `all_resources`, `scenes` / `resources` (selected + dependencies), `exclude`
  (all except selected), `customized`, dedicated server. Include filter adds non-resource files
  (`*.txt, *.json, *.csv`); exclude filter removes files after everything else.
- Matching (Godot source, `EditorExportPlatform::_edit_files_with_filter`): each comma-separated
  pattern is tested against `res://<path>` and `<path>`; `*` matches any run including `/`,
  `?` one character except `.`, case-insensitive. `ref/` alone matches nothing — write `ref/*`.
- Skipped everywhere (`EditorFileSystem::_should_skip_directory`): folders containing
  `.gdignore`, nested folders with their own `project.godot`, `.godot/`; files and folders
  starting with `.` never ship. `.gdignore` content is ignored (no patterns); resources in an
  ignored folder cannot be `load()`ed — so `tests/` is excluded by filter, not ignored.
- `*.ico` and `*.icns` are added from every visible folder regardless of filters.
- `.godot/export_credentials.cfg` holds passwords and encryption keys: never commit.
- Presets are read when the editor starts. The Godot AI MCP (4.3.0) has no preset tool: the user
  adds the first preset in Project → Export (it also offers Manage Export Templates); later edits
  go through `filesystem_manage` on `res://export_presets.cfg` while the Export dialog is closed,
  then restart the editor. The headless export reads the file from disk.
- `.gdignore` files: empty files, created once by setup or through `filesystem_manage`, then
  `filesystem_manage` scan so the editor drops the folder.

**Templates**: exactly the editor's version, in `%APPDATA%\Godot\export_templates\<ver>.stable\`
(`~/.local/share/godot/export_templates/` on Linux, `~/Library/Application Support/Godot/
export_templates/` on macOS), e.g. `4.7.2.stable`. Install from Editor → Manage Export Templates
or a `.tpz` from godotengine.org/download.

**Command**: `godot --headless --path <project> --export-release "<preset>" <abs out>`
(`--export-debug` = debug template; `--export-pack` = `.pck`/`.zip` data only; `--export-patch`
+ `--patches` = changed files only). The output folder must exist; a relative output resolves
against the project folder, not the working directory; a failed export exits with a failure code.
Extensions: Windows `.exe`, Linux `.x86_64`, macOS `.zip` or `.app`, Web `.zip`, Android `.apk`.

**Options worth setting**: `binary_format/embed_pck` (single exe); `debug/export_console_wrapper`
0 No / 1 Debug only / 2 Debug and Release — writes `<name>.console.exe` that shows stdout (the
plain Windows exe is a GUI app); `shader_baker/enabled` (4.5+) bakes pipeline shaders at export —
less first-play stutter; `texture_format/s3tc_bptc` desktop, `etc2_astc` mobile and Apple
Silicon; `codesign/enable`, `codesign/identity`, `codesign/timestamp_server_url` sign the Windows
exe during export (secrets land in `export_credentials.cfg`).

**Runtime flags in release templates** (marked "release" in the 4.6 command-line table):
`--headless` (no window, dummy audio — CI smoke without GPU), `--quit-after <frames>`,
`--log-file <path>` (4.5+). Default log: `user://logs/godot.log`, i.e.
`%APPDATA%\Godot\app_userdata\<project>\logs\` (custom user dir: `%APPDATA%\<name>\logs\`).

**Pitfalls**: the PCK is case-sensitive while Windows is not — use `snake_case` paths;
`load("res://" + name)` of a filtered file fails only in the build; editor-only autoloads fail
to instantiate (Godot AI's export plugin strips its `_mcp_game_helper` autoload, so excluding
`addons/godot_ai/*` is safe).

## Unity 6

**Build method** — C# in an Editor folder, written directly, checked with `validate_script` and
`read_console` before use. The guard runs headless only `KilnRelease.KilnBuild.Build` or a method
listed in manifest `unity_build_methods=Ns.Class.Method,...` (a name that merely contains "build"
is not enough). Batch mode cannot open a project the editor has open (Unity command-line docs,
6000.2), and Kiln keeps the editor open for the MCP: in the open editor build with MCP for Unity
`manage_build {action: build, profile: <Build Profile asset>, output_path}` and poll `{action:
status, job_id}`; `build.py build` (batch mode) is for CI and a closed editor, and refuses while
`Temp/UnityLockfile` exists. Arguments come from `build.py build` (`-kilnPreset`, `-kilnOut`,
`-kilnDevelopment`):

```csharp
// Assets/_Project/Scripts/Editor/KilnBuild.cs
using System;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Profile;
using UnityEditor.Build.Reporting;
using UnityEngine;

// Namespace is not Kiln.Editor: a namespace named Editor shadows UnityEditor.Editor.
namespace KilnRelease
{
    public static class KilnBuild
    {
        public static void Build()
        {
            string preset = Arg("-kilnPreset") ?? "StandaloneWindows64";
            string output = Arg("-kilnOut") ?? "export/windows/game.exe";
            var options = Flag("-kilnDevelopment") ? BuildOptions.Development : BuildOptions.None;
            BuildReport report;
            if (preset.EndsWith(".asset", StringComparison.OrdinalIgnoreCase))
            {
                var profile = AssetDatabase.LoadAssetAtPath<BuildProfile>(preset);
                if (profile == null) { Fail("build profile not found: " + preset); return; }
                report = BuildPipeline.BuildPlayer(new BuildPlayerWithProfileOptions
                    { buildProfile = profile, locationPathName = output, options = options });
            }
            else
            {
                if (!Enum.TryParse(preset, out BuildTarget target)) { Fail("unknown target " + preset); return; }
                report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
                {
                    scenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray(),
                    target = target, locationPathName = output, options = options,
                });
            }
            var s = report.summary;
            Debug.Log($"KILN_BUILD result={s.result} bytes={s.totalSize} errors={s.totalErrors} " +
                      $"warnings={s.totalWarnings} seconds={(int)s.totalTime.TotalSeconds}");
            if (s.result != BuildResult.Succeeded) EditorApplication.Exit(1);
        }

        static string Arg(string name)
        {
            var a = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }

        static bool Flag(string name) => Environment.GetCommandLineArgs().Contains(name);

        static void Fail(string message)
        {
            Debug.LogError("KILN_BUILD " + message);
            EditorApplication.Exit(1);
        }
    }
}
```

`build.py build` runs `Unity.exe -batchmode -quit -projectPath <root> -logFile
export/logs/unity-<preset>-<time>.log -executeMethod KilnRelease.KilnBuild.Build -kilnPreset
<profile.asset | BuildTarget> -kilnOut <out>`. An exception or `EditorApplication.Exit(non-zero)`
gives the process exit code 1. Alternative documented in Unity 6.2 docs:
`-activeBuildProfile "<path>.asset" -build <out>` (UNVERIFIED for 6.0/6.1).

- Build profiles: File → Build Profiles; assets usually under `Assets/Settings/Build Profiles/`.
  Changed in the editor through MCP for Unity, never by editing the `.asset` YAML (guard).
- `BuildReport.summary`: `result`, `totalSize` (bytes), `totalErrors`, `totalWarnings`,
  `totalTime` — the `KILN_BUILD` line is the build evidence.
- Windows output: `<name>.exe`, `<name>_Data/`, `UnityPlayer.dll`, plus folders that must not
  ship: `<name>_BurstDebugInformation_DoNotShip/` and, with IL2CPP,
  `<name>_BackUpThisFolder_ButDontShipItWithYourGame/` — exclude them from depots and butler.
- Player log: `%USERPROFILE%\AppData\LocalLow\<Company>\<Product>\Player.log`; player flag
  `-logFile <path>` (`-` = console); `-batchmode -nographics` for a GPU-less smoke.
- Unity 6 Personal: splash screen optional; Personal limit $200K revenue/funding in 12 months.

## Unreal 5.8

**Command** (`build.py build --preset Win64`, `--debug` = Development):

```
<UE>/Engine/Build/BatchFiles/RunUAT.bat BuildCookRun -project="<abs>/<Game>.uproject" -noP4
  -utf8output -unattended -platform=Win64 -clientconfig=Shipping -build -cook -stage -pak
  -iostore -package -archive -archivedirectory="<abs>/export/win64-shipping" -prereqs
```

Stages (Epic docs): build → cook → stage → package → deploy → run. Flags as printed by the
editor's own packaging log and Epic forum examples — Epic's docs do not list them; confirm with
`RunUAT BuildCookRun -help` on the installed engine (UNVERIFIED: `-installed` may be needed for
launcher engines; `-nodebuginfo` drops PDBs from staging — keep them archived anyway).

**Packaging settings** (`Config/DefaultGame.ini`,
`[/Script/UnrealEd.ProjectPackagingSettings]`; set in Project Settings → Packaging through the
Unreal MCP or by the user — the guard blocks `Config/*.ini` text edits):
`BuildConfiguration=PPBC_Shipping`, `ForDistribution`, `IncludeDebugFiles`, `UsePakFile`,
`bUseIoStore`, `IncludePrerequisites`, `IncludeCrashReporter`,
`+MapsToCook=(FilePath="/Game/<Project>/Maps/<Map>")`,
`+DirectoriesToNeverCook=(Path="/Game/Developers")`. Version:
`[/Script/EngineSettings.GeneralProjectSettings] ProjectVersion=`. (Setting these through
ObjectTools on the packaging-settings default object: UNVERIFIED.)

- Shipping disables console commands, stats and profiling; logs only with
  `bUseLoggingInShipping = true` in the game `*.Target.cs` (launcher engines also need
  `bOverrideBuildEnvironment = true` — forum, UNVERIFIED for 5.8). Smoke Development builds.
- Log of a packaged Development build: `<Project>/Saved/Logs/<Project>.log` beside the game or
  `%LOCALAPPDATA%\<Project>\Saved\Logs\` (UNVERIFIED which in 5.8 — pass a glob covering both
  to `smoke --log`); `-abslog=<path>` sets it explicitly (UNVERIFIED).
- Crashes: `Saved/Crashes/`; keep the PDBs of every shipped build.
- Credits notice required by the EULA (see `distribution.md`).
