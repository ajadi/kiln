"""Kiln toolset for Epic's Unreal MCP (UE 5.8 ToolsetRegistry): console, input, probes, shots.

UNVERIFIED: written from Epic's create-toolset skill (EpicGames/unreal-engine-skills-for-claude-
code-plugin) and the Epic-authored toolset_registry package as shipped in public plugins
(toolset_registry.tool_call, toolset_registry.registration.Registration); not yet run in a live
UE 5.8 editor. Expected toolset name in list_toolsets: "kiln_toolset.KilnToolset" (Python toolsets
are listed as <module>.<Class>). Python names marked "UNVERIFIED" below are tried with fallbacks.

Install (builder role, once per project):
  1. Plugins enabled: Unreal MCP (ModelContextProtocol), AllToolsets, Python Editor Script Plugin,
     Enhanced Input. KilnProbeComponent compiled into the game module (full build).
  2. Copy this file to <Project>/Content/Python/kiln_toolset.py.
  3. <Project>/Content/Python/init_unreal.py (create it if missing) gets:
         import kiln_toolset
         kiln_toolset.register()
  4. Restart the editor (or run the console command ModelContextProtocol.RefreshTools), then
     list_toolsets -> describe_toolset on the Kiln toolset.

Every tool acts on the running Play-In-Editor world and only reads or drives play: none edits
assets, levels or config. Read-only Kiln roles may call all of them (the guard allows
kiln_probe*, inject_input, highres_shot, and exec_console with the same command allowlist).
"""

import os
import re

import unreal

try:
    import toolset_registry
    from toolset_registry.registration import Registration
except ImportError:  # ToolsetRegistry (Unreal MCP / AllToolsets) not enabled
    toolset_registry = None
    Registration = None

# Same allowlist as the Kiln guard (UNREAL_SAFE_CONSOLE): profiling, tracing and screenshots.
SAFE_CONSOLE = re.compile(r"^\s*(stat\s+\S+|csvprofile\s+\S+|trace\.\S+|highresshot\b|profilegpu\b)",
                          re.I)
RESOLUTION = re.compile(r"^(\d{2,5}x\d{2,5}|[1-9](\.\d+)?)$")
_holds = {}  # action path -> slate tick handle of a running inject_input hold


def _pie_world():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    if world is None:
        raise RuntimeError("Play-In-Editor is not running; start it with EditorAppToolset StartPIE.")
    return world


def _probe_components(world):
    probe_class = getattr(unreal, "KilnProbeComponent", None)
    if probe_class is None:
        raise RuntimeError("KilnProbeComponent is not compiled into this project (see the "
                           "acceptance skill's unreal/ files).")
    found = []
    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        found.extend(actor.get_components_by_class(probe_class))
    if not found:
        raise RuntimeError("No KilnProbeComponent in the PIE world; add one to an actor in the "
                           "test map (ActorTools add_component, SceneTools save_actor).")
    return found


def _probe_root():
    saved = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())
    return os.path.realpath(os.path.join(saved, "Kiln", "Probes"))


def _input_action(name):
    if name.startswith("/"):
        asset = unreal.load_asset(name)
    else:
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        path = unreal.TopLevelAssetPath("/Script/EnhancedInput", "InputAction")
        matches = [a for a in registry.get_assets_by_class(path) if str(a.asset_name) == name]
        if len(matches) > 1:
            raise ValueError(f"Several input actions are named {name}; pass the asset path.")
        asset = matches[0].get_asset() if matches else None
    if not isinstance(asset, unreal.InputAction):
        raise ValueError(f"No input action {name}.")
    return asset


def _input_subsystem(world):
    controller = unreal.GameplayStatics.get_player_controller(world, 0)
    if controller is None:
        raise RuntimeError("The PIE world has no player controller.")
    library = unreal.SubsystemBlueprintLibrary
    # UNVERIFIED: Python spelling of GetLocalPlayerSubSystemFromPlayerController.
    for name in ("get_local_player_subsystem_from_player_controller",
                 "get_local_player_sub_system_from_player_controller"):
        getter = getattr(library, name, None)
        if getter:
            subsystem = getter(controller, unreal.EnhancedInputLocalPlayerSubsystem)
            if subsystem:
                return subsystem
    raise RuntimeError("Enhanced Input local player subsystem not found.")


def _inject(subsystem, action, value):
    # IEnhancedInputSubsystemInterface::InjectInputVectorForAction (BlueprintCallable).
    subsystem.inject_input_vector_for_action(action, value, [], [])


def _stop_hold(key):
    handle = _holds.pop(key, None)
    if handle is not None:
        unreal.unregister_slate_post_tick_callback(handle)


if toolset_registry is not None and hasattr(unreal, "ToolsetDefinition"):

    @unreal.uclass()
    class KilnToolset(unreal.ToolsetDefinition):
        """Drives and observes a running Play-In-Editor session for acceptance checks: profiling
        console commands, Enhanced Input injection, Kiln probe recording and high-resolution
        screenshots. Does not edit assets, levels or settings."""

        @toolset_registry.tool_call
        @staticmethod
        def exec_console(command: str) -> str:
            """Runs a console command on the PIE world. Allowed: stat <name>, csvprofile <args>,
            trace.<cmd>, HighResShot, profilegpu.

            Args:
                command: One console command.

            Returns:
                Name of the world the command ran on.
            """
            if not SAFE_CONSOLE.match(command) or re.search(r"[|;\n]", command):
                raise ValueError("Command not allowed; use stat, csvprofile, trace., HighResShot "
                                 "or profilegpu, one command per call.")
            world = _pie_world()
            unreal.SystemLibrary.execute_console_command(world, command.strip(), None)
            return world.get_name()

        @toolset_registry.tool_call
        @staticmethod
        def inject_input(action: str, x: float, y: float, z: float, duration_s: float) -> None:
            """Injects an Enhanced Input action value for player 0, as if the mapped key or stick
            were used. Returns at once; a hold keeps injecting every frame until it ends.

            Args:
                action: Input action asset path (/Game/Input/IA_Move) or asset name (IA_Move).
                x: Value X (1 for a pressed digital action; stick X for Axis2D).
                y: Value Y (stick Y for Axis2D; else 0).
                z: Value Z (Axis3D only; else 0).
                duration_s: Hold time in game seconds. 0 injects one frame and stops any hold.
            """
            world = _pie_world()
            asset = _input_action(action)
            subsystem = _input_subsystem(world)
            key = asset.get_path_name()
            value = unreal.Vector(x, y, z)
            _stop_hold(key)
            _inject(subsystem, asset, value)
            if duration_s <= 0:
                return
            end = unreal.GameplayStatics.get_time_seconds(world) + duration_s

            def tick(_delta):
                try:
                    if unreal.GameplayStatics.get_time_seconds(world) >= end:
                        _stop_hold(key)
                    else:
                        _inject(subsystem, asset, value)
                except Exception:  # PIE ended: the world and subsystem are gone
                    _stop_hold(key)

            _holds[key] = unreal.register_slate_post_tick_callback(tick)

        @toolset_registry.tool_call
        @staticmethod
        def kiln_probe_start(task: str, run: str) -> list[str]:
            """Starts recording on every Kiln probe component in the PIE world.

            Args:
                task: Folder under Saved/Kiln/Probes, usually the task id. Empty keeps each
                    component's Task.
                run: Run name used in file names. Empty uses a UTC timestamp.

            Returns:
                Absolute paths of the JSON Lines files being written.
            """
            return [str(c.start_recording(task, run)) for c in _probe_components(_pie_world())]

        @toolset_registry.tool_call
        @staticmethod
        def kiln_probe_stop() -> list[str]:
            """Stops every recording Kiln probe component in the PIE world and flushes its file.

            Returns:
                Absolute paths of the finished JSON Lines files.
            """
            return [str(c.stop_recording()) for c in _probe_components(_pie_world())
                    if c.is_recording()]

        @toolset_registry.tool_call
        @staticmethod
        def kiln_probe_read(file: str, tail_lines: int) -> str:
            """Returns the end of a probe recording under Saved/Kiln/Probes.

            Args:
                file: Path returned by kiln_probe_stop, or a path relative to Saved/Kiln/Probes.
                    Empty reads the newest recording.
                tail_lines: Number of last lines to return. 0 returns the whole file.

            Returns:
                JSON Lines text.
            """
            root = _probe_root()
            if file:
                path = os.path.realpath(file if os.path.isabs(file) else os.path.join(root, file))
            else:
                found = [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs
                         if f.endswith(".jsonl")]
                if not found:
                    raise FileNotFoundError(f"No recordings under {root}.")
                path = max(found, key=os.path.getmtime)
            if os.path.commonpath([root, path]) != root:
                raise ValueError("Only files under Saved/Kiln/Probes can be read.")
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()
            return "".join(lines[-tail_lines:] if tail_lines > 0 else lines)

        @toolset_registry.tool_call
        @staticmethod
        def highres_shot(resolution: str) -> str:
            """Captures the PIE viewport with HighResShot. The file appears a frame later.

            Args:
                resolution: WIDTHxHEIGHT (1920x1080) or a size multiplier (2).

            Returns:
                Folder the screenshot is written to.
            """
            if not RESOLUTION.match(resolution):
                raise ValueError("resolution must look like 1920x1080 or 2.")
            unreal.SystemLibrary.execute_console_command(_pie_world(), f"HighResShot {resolution}",
                                                         None)
            # UNVERIFIED: BlueprintPathsLibrary.ScreenShotDir; falls back to Saved/Screenshots.
            shot_dir = getattr(unreal.Paths, "screen_shot_dir", None)
            folder = shot_dir() if shot_dir else os.path.join(unreal.Paths.project_saved_dir(),
                                                              "Screenshots")
            return unreal.Paths.convert_relative_path_to_full(folder)

    _registration = Registration([KilnToolset])
else:
    KilnToolset = None
    _registration = None


def register():
    """Registers the Kiln toolset; False when the ToolsetRegistry is unavailable."""
    if _registration is None:
        unreal.log_warning("Kiln toolset not registered: ToolsetRegistry is not enabled.")
        return False
    return _registration.register()


def unregister():
    for key in list(_holds):
        _stop_hold(key)
    if _registration is not None:
        _registration.unregister()
