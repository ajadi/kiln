# Changelog

## 0.1.0 — 2026-10-06

First version, for Godot 4 + Blender game projects. 

## 0.1.1 — 2026-10-06

- Scene-first rule: Godot scenes are built as editor nodes through the MCP; scripts only add
  behaviour. Guard rejects scripts that construct scene content with `.new()` (policy
  `scene_first=on`, escape marker `# kiln:runtime-node <reason>`); verifier checks the scene tree.

## 0.2.0 — 2026-10-06

- New `blender-modeling` skill, built from research on code-driven 3D modeling (sources in
  the design notes): measured model sheet and anchor-first part graph, one persistent per-part
  build script, stage round budgets with revert, normalised multi-view review with numbers and
  yes/no checklists, context hygiene.
- Helper scripts: `crop_ref.py`, `ref_setup.py`, `parts_kit.py`, `set_view.py`,
  `contact_check.py`, `mesh_qa.py`.
- modeler and art-director use the new method; art-director and verifier may run only the
  read-only review scripts through `execute_blender_code` (guard-enforced).

## 0.3.0 — 2026-10-06

- Engines: `engine=godot|unity|unreal` with profile skills `engine-godot` (renamed from
  godot-conventions), `engine-unity`, `engine-unreal`, injected into engine-facing roles at spawn;
  guard rules, read-only enforcement and scene-first scans for all three engines.
- 2D: `dimension=3d|2d`, `art-2d` skill with `sprite_qa.py`, `artist-2d` role, 2D sections in
  level design (references/2d-levels.md), feel numbers, animation, lighting and engine profiles.
- New roles: tech-designer, physics-expert, anatomy-expert, creature-expert, lighting-artist,
  artist-2d, composer, music-producer, and acceptors qa-physics, qa-locomotion, qa-feel,
  qa-damage, qa-ai, qa-audio, qa-performance, qa-readability.
- New skills: pipeline (phases, gates, boards, A/B gauntlet, scope contract), acceptance (probe
  recorder + analyzer), tech-design, lighting, rigid-body-physics, human-biomechanics,
  creature-locomotion, image-to-model (prep_image.py, silhouette_iou.py), music; procedural-audio
  gains audio_check.py and reference analysis; research-based rewrites of animation,
  asset-pipeline, destruction-vfx, level-design, playtest.
- Policies `model_generators` and `audio_generators` (off by default, licence lists in skills).
- Token budget: core-only preloads, situational skills via the Skill tool, engine profile skipped
  for roles that do not use the engine, bounded session context, pruned tree walks.
- setup and doctor are engine- and dimension-aware; pipeline gates are written per engine.
- `tests/test_guard.py` regression suite.

## 0.4.0 — 2026-10-06

- OpenAI Codex support in the same plugin: portable `plugin.json` with `extensions.com.openai`,
  `.agents/plugins/marketplace.json`, `hooks/codex-hooks.json`, `scripts/codex_agents.py`
  (26 custom agents), `agents/openai.yaml` for user-only skills, plugin icons.
- Hooks: `--runtime codex`; guard checks Codex `apply_patch` per file; roles recognised as
  `kiln-<role>`; project root found from a subfolder cwd; `KILN_HOOK_TRACE` diagnostics.
- Project rules template is runtime-neutral; `runtimes=` in the manifest; setup and doctor cover
  Codex.
- The main session may write `production/**`, `research/**`, `AGENTS.md`, `.codex/**`,
  `.agents/**`; the Unity MCP port joins the guarded ports.
- `tests/test_codex.py`: hook commands launched the way Codex launches them, apply_patch
  checks, generated agents parsed as TOML.
- MCP check on first connection: `scripts/mcp_check.py` lists the servers, tools, Unreal
  toolsets and probe calls a project needs (engine, dimension, role tool lists) and verifies them;
  setup stops until `.kiln/mcp-check.json` is ready; new Phase 0 gate.
- pipeline.py: check specs may contain spaces (Phase 7 grep gates were silently manual).

## 0.5.0 — 2026-10-07

Every gap from the framework audit closed, with research where knowledge was missing.

- New knowledge skills: ui, accessibility, localization, controls-camera, game-ai, save-system,
  balance, procgen, narrative, llm-npc (opt-in), shaders, optimization, release; 2D effects in
  destruction-vfx; sprite sheets in art-2d.
- New roles: ui-designer, writer, ai-programmer (classic game AI), release-engineer.
- New scripts with tests: sheet.py, readability.py, ui_check.py, subtitle_check.py, loc_check.py,
  camera_probe.py, ai_probe.py, save_check.py, balance_sim.py, procgen_check.py,
  dialogue_lint.py, npc_eval.py, perf_compare.py, build.py, licenses.py; Unity `KilnProbe.cs`,
  Unreal `KilnProbeComponent` + Kiln toolset; analyze.py reads JSON Lines; recorder.gd measures
  real frame time and GPU time.
- Guard: experts are read-only in editors; filesystem_manage write_text cannot bypass the file
  rules; generator policies enforced; roles cannot close user gates; `codex mcp` allowed; Unity
  and Unreal rules corrected against the servers' sources (read actions, validate auto_repair,
  execute_code replay, apply_text_edits/manage_script/batch_execute scans, qualified UE 5.8 tool
  names, unreal-mcp server names).
- Pipeline: gates for dimension, hello build, slice audit/smoke, settings menu, open scope
  promises, complete release checklist, licence registry, soak; scope.py reads manual and
  blocked lines; run/autopilot/status/plan follow the current phase; the Stop hook names open
  gates when the backlog is done.
- Reference preparation found by a live model-from-photo test: flat-backdrop cut-out, gaps
  closed by contact shadows, `crop_ref.py --auto` for sheets whose views touch.
- Templates: decisions table, task types incl. tech/lighting/ai/ui/music/narrative/release,
  complexity field, LFS for fonts/video/binary resources, Unity YAML merge; setup writes
  `.gdignore` for non-shipping folders; doctor runs a Blender review script.


## 0.5.1 — 2026-10-07

Codex hooks did not run in a live Codex 0.160 session (no project context, `apply_patch` on a
`.tscn` not blocked). Two causes, both found in the openai/codex source at rust-v0.160.0:
- A root Agent Plugins `plugin.json` wins manifest discovery, and the loader returns no hook
  sources for that format. The manifest is now `.codex-plugin/plugin.json` with an explicit
  `hooks` entry (without it Codex reads `hooks/hooks.json`, the Claude Code file).
- Hooks run in the session shell (PowerShell on Windows), not only `%COMSPEC% /C`, so
  `%PLUGIN_ROOT%` stayed literal. `commandWindows` is now `python -c` that reads `PLUGIN_ROOT`
  itself and works in PowerShell, cmd and bash.
- `tests/test_codex.py` launches every hook through each shell Codex may pick and checks the
  manifest form. Verified live: project context injected, `.tscn` patch blocked, SubagentStart
  and PreToolUse carry `kiln-<role>`.

## 0.6.0 — 2026-10-11

From the first live run of the whole pipeline in a sandbox project: an armour character modelled
from a turnaround sheet (19 art rounds, TripoSR head on CPU), then a playable memory-corridor demo
on autopilot (rig and 9 clips, controller with jump, crouch and run toggle, endless void, code
strings, Windows build). Every entry below names the live failure it fixes.

- Guard: `mcp_check.py verify --probe <server>=ok` (setup step 8) was denied as a shell call to
  the Godot AI server because the command text contains the server name. `--probe` arguments
  are now ignored by the MCP-server shell rules; a real server call in the same command is
  still denied (`tests/test_guard.py`).
- run: a task's roles are delegated in the foreground and the producer never ends its turn with
  a role agent still running. Live headless run (`claude -p`): the background modeler died with
  the session mid-review.
- setup: the linked Godot AI addon goes to `.gitignore`.
- guard: the bpy rule checks scripts the command runs with a Python interpreter, not every `.py`
  it names. Live run: `head parts.py` and `cat review.py` were denied as if they ran Blender code.
- blender-modeling and art-director: limb lengths from two views (sheets often angle the arms
  forward, so the front view foreshortens them) and a check against human proportions. Live
  run: the armour's arms were built at the foreshortened length; the user spotted it.
- guard: editor locks record their session; a lock left by another session expires after
  `editor_lock_other_session_ttl` (120 s). Live run: a killed headless session's modeler kept
  Blender locked from the next session's modeler.
- image-to-model: TripoSR as the CPU option; frame the generator input with context (a tight
  face crop gave a flat relief, head + neck + collar gave a closed bust in a live run).
- guard: here-document bodies are data — a markdown table naming `parts.py` inside `python - <<EOF`
  was read as a pipeline that ran it (live run).
- image-to-model: `value_bands.py` compares the light/dark pattern band by band (Otsu per image)
  and flags missing plate breakup; the art-director runs it on the whole body from primary forms
  on. Live run: silhouette-only reviews let the cuirass, back plate and legs fail one at a time.
- plan: scale the plan to the ask — a brief for a demo or prototype is the concept; no concept
  interview, style board, art bible or tech-note tasks unless asked (live: a "simple demo scene"
  came out as 10 tasks; the user cut it to 6).
- guard: shell rules look at the programs a command starts (quote-aware segments), not at every
  word — a gate note saying "godot-ai connected" was denied as a server call (live autopilot).
- guard: a role takes the editor over from its own session's main session; the producer's doctor
  probe had locked the animator out of Blender for the TTL (live autopilot).
- engine-godot: capture the mouse on a click, release on focus loss, never in `_ready()`; game
  runs stay in the embedded Game view. Live autopilot: every probe run took the user's cursor
  while they worked in another app.
- setup/doctor: Godot game runs embedded in the Game workspace — the floating mode popped a window
  over the user's apps on every agent run (live autopilot); setup asks for the one click, doctor
  warns from the project metadata.
- run: risk review falls back to `kiln:verifier` when `/code-review` is missing; only `kiln:*`
  roles are delegated to (live autopilot picked a global agent from another tool).
- controls-camera: core moves work with two keys held (keyboard rollover); sprint toggles on
  keyboard by default. Live: the user's keyboard dropped Space under W + Shift.
- Prototype mode: `kind=prototype` in the manifest, set only by the user (setup asks when they
  call the project a prototype or demo). Light review — one acceptance role + verifier, no risk
  review or separate playtester, ≤ 2 rounds per gate; the session context and every report name
  the mode; switching to `kind=game` plans a promotion task that re-runs the full acceptance.
  A one-off relaxation for one task stays in that task file.
- protocol: every role reads that Godot scripts, scenes and resources change only through the MCP
  (live: gameplay-dev and fx-artist tried Edit/Write first and lost turns to guard denials).
- animator, anatomy-expert, qa-locomotion, human-biomechanics: the whole body is animated and
  checked — arm swing range and phase, thorax counter-rotation; a limb frozen in the bind pose
  fails. Live: all 9 demo clips kept the arms in the A-pose and every foot check passed.
- plan: confirm the character's move set with the user (default third-person set offered) and give
  every animation task whole-body acceptance. Live: jump/crouch were missing from the plan and the
  rig task's acceptance covered only the legs.
- human-biomechanics: punch and kick timings from published studies (cross 223 ± 99 ms to
  contact, hooks ~477 ms, front kick ≈ 0.25 s, roundhouse 0.30–0.65 s) and the armour caveat.
- `user_gates=proxy` (default): the agent decides user gates and user decisions — taste included —
  with the recommended option, marks them PROXY and lists them for review; `user_gates=ask` is the
  opt-in strict mode. Never proxied: publishing, money, deleting user work, overriding the user's
  own decisions. The user is often busy and would rather redo a choice later than be blocked.
- `/kiln:setup` starts with a one-round questionnaire (numbered questions with recommended answers,
  "yes" accepts all, detected facts not asked): project, engine, 2D/3D, agent apps, kind,
  `user_gates` (explained with how to switch later), repo access, generators. New
  `/kiln:settings` shows the project's settings and changes one on request; the project rules
  say how.
- Other skill packs: general-purpose packs installed globally whose model-invoked skills overlap
  Kiln (e.g. `mattpocock-skills`: prototype, tdd, code-review, research, grilling,
  domain-modeling) are turned off per project — the settings template sets `enabledPlugins` to
  `false` (verified: a project-scope `false` overrides a user-scope plugin), setup asks about any
  others (§1b item 9), Codex gets `enabled = false` in the project config, doctor warns.
- Rejection memory: `memory/out-of-scope/` in projects and in Kiln's development repository — one file
  per rejected concept with the user's words and reason; plan, run and the retro check it before
  proposing and match by meaning. Seeded with this run's three framework rejections.
- `grilling` (model-invoked): the interview before work — rounds of the whole frontier, numbered
  questions with recommended answers ("yes" accepts), facts looked up by the agent, a confirmation
  gate, PROXY under `user_gates=proxy`, game branches (move set, look, scope, content, feel,
  acceptance); recommendations never favour the easier build. concept, plan and run call it.
  Adapted from mattpocock/skills (MIT) `grilling`.
- blender-modeling: a designed part without a reference gets three structurally different
  blockouts under different constraints; the art-director picks.
- `/kiln:retro`: `retro_scan.py` gathers the evidence (guard denials by rule with repeats, hook
  crashes, tool errors per tool, review rounds per task, the user's mid-task requests and
  corrections, PROXY decisions, non-Kiln agents); the skill turns each real problem into a
  mechanical fix (check, guard rule, test) or a judgement fix (skill text), most costly first,
  checks the out-of-scope files first, writes `production/retro/<date>.md`. Autopilot runs it
  before its report. Adapted from mattpocock/skills (MIT) `retro`. On the demo autopilot log it
  surfaced 29 failed `editor_manage` and 17 failed `script_patch` calls nobody had looked at.
- `kiln-start` plugin (same marketplace), installed user-wide: one command `/kiln-start:here`
  connects any folder to Kiln at project scope and hands over to `/kiln:setup` — the installer
  exists everywhere, Kiln itself only where it is connected (~70 tokens in other projects).
- Install model, both runtimes: Kiln is installed once per machine and is OFF unless a project is
  connected — Claude Code `--scope project`; Codex `enabled = false` in the user config and `true` in
  the project's `.codex/config.toml` (`codex plugin add` turns it on globally, so the installer turns
  it back off). `kiln-start` also ships for Codex (`.codex-plugin`, implicit invocation off).
  Not-connected folders keep other skill packs (e.g. mattpocock-skills) conflict-free.
- Autopilot belongs to one session: the Stop hook pushes only the session that typed
  `/kiln:autopilot` (found in its transcript, latest invocation wins, owner kept in
  `.kiln/autopilot-state.json`). Live: a headless autopilot ran while the user opened a second
  session to ask for status; the hook pushed that session three times to do the autopilot's tasks
  and spent the autopilot's nudge budget. Session start tells other sessions to keep off; Stop and
  session end release only their own session's editor locks (every main session is "main", and
  session end used to delete `locks.json` outright). Test: `tests/test_stop.py`.
- `elements-materials` skill (model-invoked, preloaded by physics-expert and qa-physics): heat,
  cold, fire, water/wetness and electricity changing materials — the BotW elements-vs-materials
  rules, choosing per-object / grid / cellular / fire-entity simulation, one time-compression
  factor with real ordering, exact Newton update and FTCS stability, latent-heat plateaus with
  hysteresis, fire spread with wind/slope/wetness, percolation threshold and hard caps (Far Cry 2
  runaway), conduction graphs and lightning, readability rules, a measured GDScript grid cost
  (~130 ns/cell, Godot 4.7.2), lab gyms and Godot/Unity/Unreal notes. `element_check.py`
  predicts melt/ignite/cool times, stability and fire regimes, and checks recordings against
  exact answers (threshold, cooling τ, conservation, diffusivity, fire spread/burn-out/cap,
  conduction). Researched in three passes. Test:
  `tests/test_element_check.py`.
- Physics split into skills by model (all model-invoked, listed in the protocol table, each with a
  check script that predicts from exact formulas and verifies game recordings, and its tests):
  `fields-forces` (gravity zones and planets, orbits and integrator drift, drag/wind/lift, magnets,
  beams, float precision and floating origin; `field_check.py`), `fluids-granular` (method by need
  and iGPU budget, buoyancy that matches the visual waves, dispersion, virtual-pipe water, CFL,
  angle of repose; `fluid_check.py`), `soft-bodies` (substeps vs iterations, LRA, pinning without
  jitter, what Godot's Jolt SoftBody3D really builds; `soft_check.py`), `vehicles` (arcade vs sim,
  tyres, suspension, weight transfer, assists, what Godot's VehicleBody3D does from its source;
  `vehicle_check.py`), `traversal` (jumps by approach, obstacle moves by height, hanging and grip
  endurance, crawling and openings, capture-point balance, landing tiers, carried load, sitting,
  vehicle entry and driving/riding poses; `traversal_check.py`). physics-expert and qa-physics load
  them by topic (only rigid-body-physics stays preloaded); tech-design, animation, level-design,
  human-biomechanics, controls-camera and anatomy-expert point to them. `analyze.py stance`: slip
  per stance with turning stances reported separately. `tests/test_skill_links.py` checks that
  every skill reference resolves, preloads exist, model-invoked skills allow it, knowledge skills
  are reachable and check scripts are documented and tested.
- Jumps and direction changes (live reports: a standing jump played while running; feet sliding
  when the runner changes direction). animation: jumps are a family chosen by approach speed
  (standing, standing forward, walking, running, sprinting) with left/right starts picked by the
  stance foot, speed kept on running jumps, shallow running takeoff, short countermovement for
  response; "Direction changes without skating": per-step heading limits, lateral-acceleration
  caps, braking before cuts, mesh lagging the capsule with a capped damper, orientation/stride
  warping, distance matching, pivots by stance foot, foot locking with IK, lean and head lead,
  plus a zig-zag/slalom acceptance row (also in qa-locomotion with `analyze.py stance --root`).
  traversal: jump table corrected by research (broad-jump angle, countermovement timing, keep
  speed and add vertical instead of a fixed takeoff angle). human-biomechanics: soft/stiff
  landing knee angles corrected to Devita & Skelly (117°/77° peak flexion).
- Idle that looks alive (live report: a symmetric mannequin idle). human-biomechanics "Quiet
  standing": weight split, contrapposto geometry, stance, arm hang, postural sway computed from a
  public 40-subject dataset, weight shifts and fidgets, breathing, blinks, gaze. animation "Idle
  that looks alive": asymmetric base pose, breathing and sway layers, randomised shifts and
  fidgets, gaze, secondary motion, non-dividing layer lengths, state variants. `analyze.py idle`
  checks sway RMS and frequency, breathing rate and frozen parts; qa-locomotion row.
- `implications` skill (model-invoked; live miss: a removable breathing kit planned without the
  helmet port and its look with the kit off — the user had to point both out). For every new
  thing: job, state table, home when not in use, both sides of every attachment with the
  host-side assets, empty states, transitions with edge cases, a two-ring ripple, a pre-mortem;
  category checklists (handheld, wearable, consumable, vehicle part, environment, ability), real
  gear conventions (carry positions, retention, MOLLE, capped connectors), a scope filter and
  MoSCoW; decided by proxy, not asked. `implications_check.py` validates a task's section (the
  live miss fails it). run and plan write the section before delegating; game-designer specs and
  art-director reviews use it; protocol table row.
- Clothing, armour and held items (user question; live: armour stopped the elbow at 56° and the
  shoulder at 60°, found only during animation). traversal §9: measure the dressed model's joint
  stops before rigging and check them with `traversal_check.py rom --moves …` (needs from functional
  ROM data), how real armour solved joints (lames, sliding rivets, fan wings, besagew, thin padding),
  measured costs of armour, firefighter gear, boots, gloves, goggles, and how held items change the
  whole body (no arm swing with two-handed carry, lean away from one-hand loads, front-carry lean
  back, holster asymmetry, aim sway while walking) with a per-item checklist. blender-modeling:
  joint sweep and relief cuts for worn gear before handoff. 
- Walk hip sway (live: an armoured man walked swaying the hips like a drunk or a catwalk walk): human-biomechanics caps pelvis obliquity and rotation (±5°), lateral shift (±2.5 cm), step width (8–12 cm, no crossing) and says what reads feminine or drunk; animation and qa-locomotion rows. Values marked [U] (no research pass this time — usage limit).
- `pipeline.py status`: inline code no longer counts as an unfilled placeholder (live: the project
  CLAUDE.md template's own `kiln:<skill>` / `git add <paths>` notation held the pipeline at Phase 0
  with all gates done; the real `<machine>` left in GAME.md was hidden behind it).
- Graceful autopilot stop (live: the autopilot had to be killed at the usage limit, leaving two tasks half-done): /kiln:stop writes `.kiln/stop-after-task`; the Stop hook keeps the run on the task in progress (backlog `[~]`) and lets it end after it; autopilot checks the file before picking the next task, writes `.kiln/resume.md` and turns itself off; a "Resume after an interruption" section continues half-built work from the task log and uncommitted files and reruns interrupted acceptance roles; status shows it. Tests in `tests/test_stop.py`.
- "Reads wrong" catalogue (animation `references/reads-wrong.md`): every live animation complaint as a row with cause, check, threshold and fix — skating on turns, standing jump at run speed, mannequin idle, hip sway, frozen arms, armour-blocked elbows, straight-line skating, weightless strikes, floating jumps; qa-locomotion runs the applicable rows, plan copies them into animation tasks, and a new complaint adds a row. `analyze.py gait`: hip sway (lateral pelvis shift from the travel line, obliquity and rotation from the hip joints, step width and midline-crossing steps with left/right from the travel direction).
- Per-task reasoning effort (live: the headless producer's Agent tool had no `effort` — npm CLI 2.1.281 vs 2.1.296 — so it improvised a project agent copy and a relay process): task field `effort:`; run passes it to the Agent tool; doctor 8a checks the headless CLI version; fallback `scripts/effort_agents.py` generates `<role>-<effort>` project copies before the session starts (`--from-tasks`, `--clean`). Tests: `tests/test_effort_agents.py`.
- `flight` skill: jetpacks and jump kits, gliders and wingsuits, fixed-wing, helicopters, drones, flying creatures, with the weight of fuel, pilot and gadgets (T/W full and empty, take-off check, max gadget mass, hover endurance as fuel burns off: t = c/g·ln(m0/m1)), thrust line through the CoM, lean, stall and turn, glide tables, rotor momentum theory, game patterns (fuel/heat meters, soft ceilings), Godot/Unity/Unreal notes. `flight_check.py` + tests; wired into protocol, physics-expert, qa-physics, tech-design, vehicles and fields-forces.
- playtest: a measured miss is a finding until reproduced elsewhere, never a "test artefact" by
  assertion (live: kick clips ran one tick long, the builder blamed the test buffer; the cause was
  float accumulation in a `timer -= delta` countdown, found by qa-feel with a second driver).
- traversal: wading and swimming (body buoyancy from fat and lungs, what shows above water, armour and wet clothing in water, wading speed by depth, strokes, breath hold, states and clip set) and backpacks (loads, hips vs shoulders, posture, bounce as a mass on a spring, the pack as an inventory system); `traversal_check.py predict float|wade|packbounce|packlean` + tests.
- qa-feel: inputs that share state (combos, buffers, cooldowns) are also tested interleaved, and
  on-screen text passes only when its whole rect is inside the capture (live: jab → kick → wait →
  punch gave a cross, and a clipped F11 help line was reported visible; the verifier caught both).
- `hands` skill: grip per object (pistol, rifle, sword, knife, shield, lantern, ledge, ladder, rope, wheel, handlebars, door handles, small items) from the grasp taxonomy, finger and wrist ranges, resting cascade, hand sizes, handle diameter = 19.7 % of hand length, arm IK to sockets and finger pose libraries, two-handed holds pinned after aim and recoil, climbing hand placement, Godot/Unity/Unreal notes. `hands_check.py` (predict handle/grip; rom, drift, wrist) + tests; wired into protocol, animation, traversal and qa-locomotion.
- retro: `retro_scan.py --subagents <session>/subagents` reports each role run's effort, responses,
  output and measured thinking tokens and wall / tool / model minutes (live: the modeler effort
  A/B was judged from text length — thinking estimated 71 %, measured 36 %).
- engine-godot: no throwaway check scenes. The MCP cannot close a tab, so `project_run` autosave
  re-writes the scene after it is deleted (live: two import-check scenes kept coming back as
  untracked files). Check imports from a gym that already instances the asset, the running tree,
  or the import log.
- `riding` skill: horses first, camels, elephants and large mounts — gaits (speeds, stride frequency and length, footfalls, Froude bands with hysteresis, scaling to other sizes), rider coupled to the saddle (seat per gait, sitting and rising trot, two-point, hands following the bit, IK and phase sync), mounting and dismounting, lean and turning circles by gait, stopping distances, jumps, stamina/bond/panic, load limit (rider + tack ≤ 20 %, Powell 2008; 15 % rider alone, Dyson 2020 pilot), combat, camera, input, AI mounts, reads-wrong table, Godot/Unity/Unreal notes. `riding_check.py` (predict gait/stride/scale/turn/stop/load; seat, follow, hooves, lean, grip) + tests; wired into protocol, animator, creature-expert, qa-locomotion, vehicles and creature-locomotion.
- fluids-granular: wind, sand and snow — saltation thresholds and flux (Bagnold, Kawamura, Lettau; Pomeroy & Gray for snow), lee deposition and dune migration with one time-compression factor per layer (real dunes move metres per year), Werner units, footprint fill by wind, sandstorm visibility and particle overdraw, snowfall and settling (FSM), footprint depth by load (CRREL), Tabler drifts, avalanche stability index and α-β runout, melt; 14 new `predict` cases and `fill`/`accum`/`lee`/`runout`/`release` checks in `fluid_check.py` + tests; `references/wind-sand-snow.md`; protocol, qa-physics and tech-design rows.
- `doors` skill: door types and sizes against the capsule and navmesh, push/pull approach and hand, closers and swing speeds, physics vs animated doors, locks and breaching, AI through doors (links, door state, crowds), curtains (cloth, beads, strips), car doors and getting in and out by vehicle (sedan, SUV, minivan, pickup/truck, sports car, bus) with measured times; `doors_check.py` (predict clear/swing/standoff/strips/car/cardoor; grab, follow, penetration, passage, aipass, swing) + tests; traversal §11 car ingress numbers verified (Xsens study, Bodenmiller 2002, 49 CFR 399.207); wired into protocol, animator, level-designer, gameplay-dev, ai-programmer, sound-designer, qa-ai, qa-locomotion and implications.
- `analyze.py gait` also reports stride length and cadence, and `--ref-stride` / `--ref-cadence`
  fail a fix that moves them more than 3 % (live: a hip-sway fix had to keep the user's stride and
  cadence, and qa-locomotion wrote a one-off script because the gait check could not measure them).
- `weather` skill: one weather state on a global-shader-parameter bus (transitions with hysteresis and minimum dwell, seeded forecasts, regions), wet surfaces and puddles with drying, rain in a camera-local volume with roof occlusion and splashes, snow cover on surfaces (amounts from fluids-granular), wind coupling, fog from visibility (Koschmieder) per engine, photosafe lightning and thunder delay, cloud/sky coupling, audio layers, gameplay effects (traction, climbing, cold, fire, AI sight and hearing), budgets, save state; `weather_check.py` (9 predict cases; smooth, wetness, shelter, visibility, flashes) + tests; wired into protocol, fx-artist, lighting-artist, gameplay-dev, sound-designer, level-designer, ai-programmer, game-designer, tech-designer, qa-readability, qa-performance, and the lighting, elements-materials, fields-forces, accessibility, shaders, tech-design and save-system skills.
- `sky` skill: sun, moon and star motion (NOAA solar position, twilight, moon phase, position and brightness, sidereal star rotation), game time compression and sleep, light, colour and exposure curves over sun elevation, night readability, sun–moon shadow handover, sky models and radiance cost, Godot/Unity/Unreal setup; `sky_check.py` (predict sun/twilight/moon/stars/light/time; sun, curve, handover, clock, stars) tested against JPL Horizons, NOAA tables and Espenak's phase table; wired into protocol, lighting-artist, gameplay-dev, level-designer, tech-designer, qa-performance and the lighting, tech-design and save-system skills.
- animation acceptance: rows for props in free flight (g ± 10 %, no mid-air reversal), catches and
  set-downs (≤ 1.5 m/s at the hand, ≤ 2 g over ≥ 6 frames, the body yields) and load lifts (legs and
  trunk lead the arm). Live: a put-on clip tossed a 12 kg unit at 4.4 g, flew it backward, and stopped
  it dead on a straight arm. The anatomy-expert caught it, but the animator had no rule to catch it first.
- gameplay-dev: a modeled object gets its asset; no silent primitive stand-ins (ask for the export,
  or name it `*_placeholder` and list it as open), and every visible object gets a framed capture
  (live: the set-down breathing unit became grey cylinders, and no capture framed it).
- acceptance: a capture must not change what is measured (live: a camera flip inside a gait
  recording turned the walker and read pelvis rotation 20.7° instead of 4.9°).
- human-biomechanics / `analyze.py gait --foot-width`: the 8–12 cm step width is for ~10 cm shoes;
  wide boots scale it to 0.8–1.25 × foot width (live: 24.7 cm armour boots would overlap at 12 cm).
- animation (Godot): bones a state does not key drift to rest, so a one-shot whose frame 0 holds
  them elsewhere slides them in view during the crossfade. Prop bones get a defined hold pose,
  checked by per-tick bone speed (live: kit_on slid the back unit to the floor at 15 m/s).
- protocol "Do it yourself": agents install, start and use every tool (editors, MCP servers,
  add-ons, engine projects and settings); the user gets a manual step only when no command,
  config file or MCP call can do it, with the reason. Same rule in the project CLAUDE.md template.
  setup: Godot bootstrap `project.godot` and the embedded Game view
  (`.godot/editor/project_metadata.cfg`) are written by Kiln before the first editor start, no
  Project Manager question; Godot installed from godot-builds if missing; Blender started as the
  GUI with the add-on's Auto Start; Unity/Unreal projects created from the command line or a
  template copy (UNVERIFIED), launchers only as fallback; MCP check failures are fixed, not
  listed. Live: setup sent the user to the Project Manager and the Game tab, and the user
  answered that nothing is created by hand.

## 0.7.0 — 2026-10-14

From the g2 test project (a Godot 4.7.2 + Blender 5.2 game built by Kiln 0.6.0 agents): 153
reports, worked off as 28 tasks, then a
design review of that work (milestone V01-V10). Tests: 560+ offline (real headless Godot 4.7.2 and
background Blender 5.2 where a script runs inside them) plus `tests/test_live.py` (`KILN_LIVE=1`,
a real `claude -p --plugin-dir` session).

- **Gates and roles.** Every task declares `touches:` (humanoid, creature, mech, physics,
  movement, npc, damage, audio, scene-growth | none) and carries a `## gates` table: route table
  plus the roles of its touches. `pipeline.py gates` suggests and checks; the Stop hook blocks once
  when a closed task still owes a role or has uncommitted changes. Keyword guesses only suggest
  (whole-text keywords put anatomy-expert on g2's facades and qa-audio on server tooling).
  `pipeline.py row` (numbered tables under a lock), `pipeline.py migrate` (older projects).
- **Guard.** Shell commands judged by what they run (bpy text written to a file, generator names in
  reads, headless Godot probes under `tests/` and `.kiln/tmp`, `--check-only`); no killing by image
  name; write zones follow the protocol (shared memory, notes files, a task's own paths), but a
  role cannot rewrite a task's role/paths/touches/type lines or another role's gates row; acceptor
  probes `probe_qa_*` belong to acceptors; shell writes (redirects, tee, cp/mv, sed -i,
  Set-Content) pass the same rules; `.import` edits go through `import_edit.py`; `on_screen=slot`
  holds windowed game runs; `model_generators=remote` allows generators only through
  `gpu_job.py`; manifest `agent_model` / `agent_effort` filled into every Agent call (seen live).
- **Hooks.** The autopilot waits for running agents instead of nudging; agent heartbeat in
  `pipeline.py status`; a hand-written session handoff is never overwritten; shared state files
  are written under a lock with atomic replace (20 parallel agent starts all recorded; one of 10
  simultaneous callers gets the editor).
- **New roles and skills.** `autoplayer` (plays the game while the user is away: objectives, stuck
  detection, per-frame trace, night loop, morning report with exit-time crashes apart); `tools`
  (per-project tool manifest, machine tools root, `tools_check.py`); `gpu-server` (rented GPUs:
  provider-neutral profiles outside the project, spend cap, provenance, `gpu_job.py`).
- **New scripts.** `import_edit.py`; acceptance `probe_base.gd`, `accepted.py`, `mesh_fit.gd`;
  blender-modeling `silhouette_shot.py`, `silhouette_measure.py`, `card_atlas.py`; playtest
  `autoplay_base.gd`, `presence.py`, `autoplay_loop.py`, `autoplay_report.py`; mesh_qa back faces
  and daylight; readability hex pairs, figure parts, border-safe saliency, clean masks; sprite_qa
  edge/region contrast, clusters, hardware palettes; ui_check focus-diff; analyze sole points,
  contact flag, invisible breathing; dialogue_lint `_max` columns; loc_check expansion filters.
- **Knowledge from measurements.** engine-godot (MCP gaps and routes, false reload error 43, IK
  callback lag, glTF extensions, import facts), acceptance methods, character modelling (measured
  shoulders, SDF figures, garments over joints, hair cards), animation (IK rest bend, swing
  tangents, prop-bone draws, scaled shared clips, reads-wrong 10-14), audio (interactive music,
  3D listener needs a camera), physics (controllers and crowds), level design (edge audit),
  asset pipeline, UI, setup and doctor (exact MCP sources, Blender `--online-mode`, line endings).
- **Settings.** `state_paths`, `notes_files`, `agent_model`, `agent_effort`, `perf_gate`,
  `on_screen`, `model_generators=remote`; machine.json `tools_root`.
- **New in 0.7.0 beyond the fixes.** `/kiln:update` (refresh the installed plugin, migrate the
  project, list what changed since its version; SessionStart says when a project is behind; the
  changelog now ships inside the plugin). Editor queue with a lease: a refused agent waits in
  line, a free editor goes to the head of the queue, a holder past `editor_lease_s` hands over
  (`pipeline.py status` shows holders and waiters). Visual regression `frames.py` (baselines per
  scene, SSIM and changed regions, accept with a reason). `pipeline.py page` writes
  `production/STATUS.html`, one page for the user: phases, tasks and the roles they owe, agents,
  editor queue, decisions taken for the user, the last autoplay night. `asset_budget.py`: what
  each glb costs (triangles, draw calls, bones, textures, VRAM) against `production/budgets.json`.
  Retro role coverage: roles never used, required roles that never ran, skips with reasons.
- **English only.** README, docs, skills, code, comments and test data are English (localisation
  examples and tests use Polish); `tests/test_english.py` keeps it so. Agents still talk to each
  user in their language.
- Known gaps: Unity/Unreal helpers for mesh fits and autoplay (listed in the engine-unity and engine-unreal skills); 3D
  jump-buffer/coyote values stay open (report row 36, needs research).

## 0.7.1 — 2026-10-14

- **Tools found, installed and offered.** One machine config for both plugins and Codex:
  `~/.kiln/machine.json` (the old plugin-data file is merged once). The tools folder
  (`tools_root`) is asked once, at `/kiln-start:here`, and never again unless the user changes it.
  `tools_check.py plan` looks everywhere first (registry, PATH, tools folder, usual install
  places), then setup asks one question. `install` downloads Godot, Blender, uv, git-lfs and
  Ollama from their official sources, checks the published sha256 (nothing is installed on a
  mismatch), unpacks into the tools folder and verifies the version; Godot AI and the Blender
  Lab MCP install through uv, their add-ons are fetched, and the MCP registration commands are
  printed. Unity and Unreal get a short instruction. Every setup run ends with
  `tools_check.py installed`: what Kiln put on the machine, with version, place, size, checksum,
  MCP registrations and add-ons.
- **Generators offered with a comparison.** `tools_check.py offers` compares image-to-3D models
  (TripoSR, TripoSG, SF3D, SPAR3D, Step1X-3D, TRELLIS.2, Pixal3D) and text-to-music models
  (ACE-Step 1.5, DiffRhythm) by GPU memory, licence, commercial use and speed, gated by
  `model_generators` / `audio_generators`; `offer-install` clones a pinned commit into a uv venv
  after the user's yes. Not offered, with the reason: Hunyuan3D, MusicGen, YuE, Stable Audio
  Open, Udio.
- **`llm_npc`** policy (`off` / `local` / `api`): `local` installs Ollama with the user's yes.
- **Problem reports.** Every role and the main session write problems with Kiln itself into
  `kiln-report.md` while they work (project rules; `/kiln:update` adds the rule to older
  projects); `/kiln:report` adds the user's own complaint and can turn it into a GitHub issue
  with their yes. `pipeline.py row kiln-report.md` creates the file with its header.
- **Assets without a game.** `kind=assets` (`engine=none`): no engine, no game pipeline, Blender
  only, gates that judge the asset itself. New commands `/kiln:model` (a 3D model from 1-3
  images), `/kiln:sprites` (sprite sheets, or a 2D map cut into a deduplicated tileset and a
  Tiled map by the new `tiles.py`), `/kiln:track` (a song, instrumental or game loop, composed
  or generated, measured). They also work inside game projects.
- **Cinematics.** New `cinematic` skill (shot list and animatic, camera grammar with numbers,
  Godot AnimationPlayer + Movie Maker, Unity Timeline + Cinemachine + Recorder, Unreal Sequencer
  + Movie Render Queue, Blender 5.x video output, subtitles, pause and skip) with
  `shot_check.py` (timeline gaps, the 180-degree line, the 30-degree rule, subtitle reading
  speed, line length, duration and gaps) and the `cinematic` task type; the animator stages
  cutscenes.

## 0.7.2 — 2026-10-14

- **`/kiln:cinematic <description>`**: a video clip or a cutscene end to end - brief in one
  question, shot list and animatic for the timing, built in Blender (asset mode, or when only a
  video is wanted) or in the engine's sequencer, render time measured on 3 frames and told
  before the full render, MP4 with sound; gates: `shot_check.py`, exact frame count, A/V offset,
  loudness for online video, art-director on frame grabs. The `cinematic` skill is now both the
  command and the knowledge roles load.

## 0.7.3 — 2026-10-14

Fixes from a code review of the whole project, each with a test:

- **Guard.** A `.env` file is refused at `git add`, and `git commit -a` / `git commit <paths>`
  are checked too (before, only files already staged were). "import bpy" counts only in a
  pipeline that starts Python, so `rg "import bpy" && python -m pytest` runs. Generator names
  in git and gh text (commit messages, issue titles) are not runs; `git clone` of a generator
  still is.
- **Stop hook.** A reopened user gate ("- user REOPENED <date>") stays the user's, so the
  autopilot is not pushed to close it. A stopped agent leaves the editor queue at once instead
  of blocking a free editor for 5 minutes. With stop-after-task, TASK-1 no longer matches
  TASK-12.
- **Scripts.** `pipeline.py decide` numbers decisions under the row lock (parallel deciders got
  the same number). `pipeline.py`, `migrate` and `mcp_check.py` read `key = value` manifests
  the way the hooks do (migrate appended `engine=godot` under `engine = unity`).
  `codex_agents.py` picks the newest cached plugin by version number (0.10.0 after 0.9.0).
  `effort_agents.py --from-tasks` accepts `role: kiln:<role>`.

## 0.7.4 — 2026-10-14

- **Update every project from one place.** Every Kiln session records its project in
  `~/.kiln/projects.json`. `/kiln:update all` lists every Kiln project on the computer with its
  version (`--scan <folder>` also finds projects not opened since), asks once and updates all
  that are behind (`kiln_update.py projects` / `apply-all --yes`). A session says when other
  projects are behind. Folders under the system temp dir are not recorded.
- **GUIDE.md**: Kiln in plain words - install, install scopes, updating, every command, every
  knowledge skill and who uses it, who calls whom. A test keeps it naming every skill.

## 0.7.5 — 2026-10-14

- **New versions noticed by themselves.** Once a day the session-start hook starts a background
  check of the latest release on GitHub (`hooks/update_check.py`, repository from the plugin
  manifest); the session never waits for the network, and an offline check is recorded and not
  retried until the next day. The next session start says "Kiln X is out (installed: Y)" with
  `claude plugin marketplace update kiln` and `/kiln:update all`; the project rules tell the
  producer to say it once and update only after the user's yes. `"update_check": "off"` in
  `~/.kiln/machine.json` turns it off.
- Test projects under the system temp dir neither read nor write this machine's Kiln state
  (projects registry, update check); a test had read the real registry.
- **Model tiers for both apps.** The README describes roles by tier (strong, balanced, fast), with
  what each tier is in Claude Code and in Codex. `agent_model` may be a Codex model name: the
  Codex generator writes it as given (it was dropped), and the guard no longer forces it on Claude
  Code's Agent calls.
- Review of the change: the check records every failure (a cut connection or an odd answer no
  longer leaves it retrying at each start), keeps a release already seen through an offline day,
  marks itself started so parallel sessions do not start more, survives a short headless session
  on Windows (breaks away from its job), and gives Codex its own commands. The guard knows Claude
  names with suffixes and cloud ids (`sonnet[1m]`, `us.anthropic.claude-...`) and ignores a
  task's Codex `model:` line; the Codex generator leaves out Claude-only names (`fable`).

## 0.8.0 — 2026-10-15

- **Gemini CLI.** Kiln builds as a Gemini CLI extension (`scripts/gemini_extension.py`; published
  as the `gemini-extension` branch: `gemini extensions install https://github.com/ajadi/kiln
  --ref gemini-extension`). The 31 roles become Gemini subagents `kiln-<role>`, the commands
  `/kiln:<name>`, and the same Python hooks run with `--runtime gemini`: Gemini tool names are
  mapped for the guard, denials and input rewrites use Gemini's contract, AfterAgent keeps the
  autopilot going, and a role is known from the `invoke_agent` call that runs it, so its write
  zone holds. `setup`, `kiln-start` and the MCP register commands know Gemini; on per project with
  `gemini extensions enable kiln --scope workspace`. Checked in gemini-cli 0.64.0 against a local
  fake model API: the extension validates and installs, SessionStart runs, the guard denied
  `git add -A`, a subagent `kiln-art-director` loaded and was denied a write outside its zone.
  The live run found two bugs the docs did not show (a rewritten tool input must carry every
  parameter; a failed `invoke_agent` left its role behind), both fixed with tests. Not yet run
  against a real Gemini model.
- **problem_reports** setting (`on` by default): a crashed Kiln hook writes its own row to
  `kiln-report.md`; `off` stops all problem reports.
- **README rewritten for people**: what Kiln is in a few lines, a collapsible install block per
  agent (Claude Code, Codex, Gemini CLI, any other agent), four first steps, commands by what you
  want to do; the full tables fold away.
- **GitHub Copilot CLI.** The plugin reads in Copilot through `.github/plugin/plugin.json`: the
  roles as agents `kiln:<role>` (`copilot/agents/`, generated by `scripts/copilot_agents.py` with
  Copilot tool names: Claude's `Bash` and `mcp__<server>` gave a role no shell and no MCP tools),
  the skills, and the same Python hooks with `--runtime copilot`. A subagent runs in its own
  session: its start queues the role, its first call takes it, its stop ends it; the agentStop
  of a subagent's session is not the producer's. On per project with `enabledPlugins` in
  `.github/copilot/settings.json`. Checked live in Copilot CLI 1.0.97 (BYOK against a local fake
  model, a fake `blender` MCP server): the guard denied `git add -A`, `kiln:art-director` got
  shell and Blender tools and was denied a write outside its zone, the plugin stayed off in
  another folder.
- **OpenCode.** `scripts/opencode_setup.py --project .` writes the project's
  `.opencode/plugins/kiln.js` (the same Python hooks: a denial throws, a role's start text leads
  its task prompt, the session context goes into the system prompt, the autopilot sends the next
  message on idle), the roles as subagents `kiln-<role>` and links to Kiln's skills. A subagent
  is known by its child session (`parentID`). Checked live in OpenCode 1.19.0 against a local
  fake model: the guard denied `git add -A`, `kiln-art-director` was denied a write outside its
  zone, the Kiln context reached the system prompt, and in `opencode serve` the autopilot
  continued three times and stopped at its nudge limit (a one-shot `opencode run` exits first).
- **Cursor** is not supported beyond its skills: its CLI needs a Cursor account and routes
  every model call through Cursor's servers, so its hooks cannot be checked against a test model.
- **`analyze.py rigid`**: a loop or cycle that is the whole character moved, turned or scaled as
  one piece, or a pose that never moves against its root, fails. Per frame the best similarity
  transform (Umeyama 1991) of frame 0's joints onto frame k's; residual and joint motion as
  fractions of the character height; `--dims 2` for screen traces, `--unit-noise` for
  pixel-snapped ones. In qa-locomotion and the animation acceptance table, for NPC and animal
  loops too.
- **`frames.py anim` and `ramp`**: an effect drawn but frozen (ON vs OFF frame-to-frame change)
  and a state change that sweeps instead of easing (consecutive frames during the change as
  unrelated as frames far apart, the "phase = rate x absolute time" bug). Capture recipes in the
  acceptance skill (Godot Movie Maker first); the bug class in the shaders skill.
- **`ref_compare.py`** (acceptance): fidelity to a reference image in numbers - magnified
  side-by-side regions with rulers, brightness ratio per cell (values, light pools), colours at
  points (delta E), palette coverage with missing and foreign colours, regions ranked by
  mismatch. The art director reports per axis (scale, layout, values, palette, light pools,
  line, density, HUD) in numbers, at most three fidelity rounds before asking the user.
- **`analyze.py pops` and `hits`**: a break in motion on a transition (an isolated one-frame
  step; fast eased moves pass) and attacks that miss (the weapon segment must pass within each
  target's hit radius at its impact frame, targets all round). In qa-locomotion and qa-feel.
- **Scene QA contract** (`qa_contract.gd` + `qa_contract.py`, Godot first): a scene lists named
  QA states (worst UI strings, facing x action, emitter anchors, loops, transitions, attacks,
  effect frames); `qa_contract.py run` records them all and judges each into one `report.json`
  (UI overflow and `ui_check.py layout`, anchor distance, `analyze.py rigid` / `pops` / `hits`,
  `frames.py anim` / `ramp`). Tested with a real headless Godot 4.7.2. Unity and Unreal:
  described only.
- **Pitfall format for defect knowledge.** The animation "reads wrong" catalogue is now one entry
  per defect class: what it looks like (the user's words), why it happens, the principle of the
  fix (for the whole class), what catches it (check and threshold, or `no check yet`), where it
  is taught - all 14 entries kept. `retro_scan.py` lists entries no check catches and the user's
  defect reports from the task logs; the retro writes defect findings in the same format and
  proposes a new check (or an extension of an existing one) as a follow-up task for every defect
  no check caught.


## 0.8.1 — 2026-10-19

- Codex `config.toml` only through `scripts/codex_config.py` (released as a fix on top of 0.8.0;
  details in the 0.9 entry below).

## 0.8.2 — 2026-10-19

- Install fixes released on top of 0.8.1 (launchers for Python, `codex_config.py` gaps,
  `json_config.py`, `text_block.py`, OpenCode keeps user skills, `folder_check.py`, guard lets
  setup register Unity / Unreal) and README "Set up the project" per agent; details in the 0.9
  entry below.

## 0.9.0 — 2026-10-19

- **Guard: generator hosts and secrets.** `audio_generators` now also covers DiffRhythm and
  Stable Audio's API (`api.stability.ai/.../audio`); `model_generators` covers Rodin's new host
  `api.hyper3d.com`, fal, Replicate, Tencent Cloud, Sloyd, 3D AI Studio, Leonardo, Scenario and
  Layer. Staging or committing keys and certificates (`*.key`, `*.pem`, `*.p12`, `*.pfx`),
  `credentials.json`, `client_secret*.json` and anything under a `secrets/` folder is refused,
  like `.env` files already were.
- **`/kiln:update all` registry.** A scan no longer registers the project template or test
  fixtures inside a Kiln checkout, and one folder is one row whatever the drive letter's case
  (older registries with `d:/x` and `D:/x` are merged).
- **OpenCode: `apply_patch` goes through the guard.** OpenCode 1.x gives GPT models
  `apply_patch` instead of write/edit; the plugin passed it through unchecked, so write zones
  and the MCP-only file rules did not apply. Checked live (OpenCode 1.18.18, a fake
  `gpt-5-fake` model): a patch adding a scene file is refused.
- **OpenCode: a role's handoff is checked.** A role that answers without its status line gets
  one more turn (as SubagentStop does in Claude Code), as the same role, and the producer sees
  the second reply. Before, the check never ran in OpenCode. Checked live on OpenCode 1.18.18.
- **OpenCode: `agent_model` reaches the roles.** OpenCode's task tool has no model field, so the
  guard's per-call model never applied there; `opencode_setup.py` now writes `agent_model` in
  OpenCode's `provider/model` form into every role (checked live with `opencode debug agent`).
- **Gemini CLI: roles run up to 3 hours.** Gemini stops a subagent after 10 minutes unless its
  agent file sets `timeout_mins`; every Kiln role now has 180, and the role marker lives as
  long. Checked live: Gemini CLI 0.64.0 loads all 31 roles with it.
- **Gemini CLI: one role at a time, Plan Mode, headless skills.** A second role started while one
  runs is refused until the first returns (Gemini runs one turn's agent calls in parallel and its
  hooks do not name the role, so roles were mixed up). The extension ships
  `user-policy/kiln.toml`; setup copies it to `~/.gemini/policies/` with the user's yes: Kiln's
  skills activate without a question (headless Gemini hid `activate_skill`) and Plan Mode may
  start Kiln's read-only roles. Checked live on Gemini CLI 0.64.0 (both, with and without the
  file).
- **Copilot CLI: role effort and project rules.** The generated roles use Copilot's
  `reasoning-effort` (it ignored `effort`) and `include-custom-instructions: true`, so a role
  reads `CLAUDE.md` / `AGENTS.md` (before it got none). Checked live on Copilot CLI 1.0.98 with a
  fake model API: the role's requests carry its effort (`high` in a `low` session) and the
  project's `CLAUDE.md`; with the old files neither. `/kiln:autopilot` in Copilot runs in
  Copilot's autopilot mode: without it Copilot ends the turn after 8 hook continuations (live:
  9 of 12 checklist items, then a stop; in autopilot mode all 12).
- **Codex: `config.toml` only through `scripts/codex_config.py` (field report).** A user's Codex
  app would not start: the install text had an agent append `[plugins."kiln@kiln"]` /
  `enabled = false` to `~/.codex/config.toml` by hand, without a final newline, and Codex's next
  block was glued to it (`enabled = false[features]`). The new script switches a plugin on or
  off keeping every other line, ends the file with a newline, parses the result before writing,
  keeps `config.toml.kiln-backup`, and `--check` / `--repair` find and fix a value glued to a
  table header. README, GUIDE, `/kiln-start:here` and setup use it; the guard refuses hand edits
  of any `.codex/config.toml`. Checked with Codex 0.163: the broken file fails to load, the
  repaired one loads.
- **Codex: the producer rule is enforced.** Codex's main thread is the hook call without an
  agent id (its subagents always carry one), so "the producer writes only state" is now a guard
  check in Codex too, not only a line in `AGENTS.md`.
- **Codex: hooks have readable names in the review.** Codex's `/hooks` review titled Kiln's hooks
  "Hook 1", "Hook 3"; it titles a hook by its `statusMessage` (tui hooks_browser_view.rs), so each
  has one now: Protect Kiln project tools (PreToolUse, guard.py), Load Kiln project state
  (SessionStart), Add engine rules to Kiln agents (SubagentStart), Save session handoff and
  release locks (SessionEnd), Manage Kiln autopilot and release locks (Stop), Clean up Kiln
  agent state (SubagentStop). Behaviour and permissions unchanged; Codex asks once to trust the
  renamed hooks (the name is part of a hook's trust hash).
- **Hooks find Python on every system.** Claude Code and Gemini CLI started every Kiln hook as
  plain `python`; macOS and many Linux systems have only `python3`, so every hook failed as a
  non-blocking error and nothing was guarded. Claude Code now runs them through `hooks/py.sh`
  (bash; Git Bash on Windows), Gemini through `hooks/py.cjs` (node, which Gemini CLI always
  has): both pick the first working Python 3.10+ (`python`, `python3`, on Windows also
  `py -3`; a Microsoft Store stub is skipped), cache it in `~/.kiln`, and say so when there is
  none. Checked live: Claude Code (a real session: project context at start, a scene write
  refused) and Gemini CLI 0.64.0 on Windows; the stub and no-Python cases by tests.
- **Codex config fix, the gaps (install audit).** `codex_config.py` reads a file saved with a BOM
  (PowerShell 5.1) and writes it back without one, handles the inline form Codex may write
  (`[plugins]` / `"kiln@kiln" = { enabled = ... }`), and says it needs Python 3.11+ instead of a
  traceback. README, GUIDE and `/kiln-start:here` say where `<kiln>` is for a Codex install
  (`~/.codex/plugins/cache/kiln/kiln/<version>`) and to stop rather than edit by hand when the
  script cannot run. The guard also refuses shell writes to a `.codex/config.toml` outside the
  project (the user config). Checked live: Codex 0.163 loads the result.
- **OpenCode setup keeps the user's own skills.** `opencode_setup.py` removed a real
  `.opencode/skills/<name>` folder whose name matched a Kiln skill (release, run, status, ...)
  and linked Kiln's in its place; now such a folder is kept, Kiln's skill of that name is not
  linked, and the report names them. `--project` with forward slashes no longer fails halfway
  (`mklink /J` read `/` as a switch).
- **Setup no longer breaks the project's own text files.** New `scripts/text_block.py`: `block`
  puts Kiln's `.gitignore` / `.gitattributes` part between marker lines (replaced on re-runs,
  the user's lines kept), with a newline before it - appending to a file without a final newline
  turned `*.keystore` + the block into `*.keystore# --- kiln ---`, and that file stopped being
  ignored (checked with real git: ignored again with the script). `include` puts `@AGENTS.md`
  first in `CLAUDE.md` / `GEMINI.md` instead of replacing what the user wrote there. Both keep
  LF or CRLF and drop a BOM. Setup uses it.
- **The guard lets setup register Unity and Unreal.** `claude|codex|gemini|copilot|opencode mcp
  add ... http://localhost:8080/mcp` names the editor's port without connecting to it, but the
  "no direct connections to the editors' MCP ports" rule refused it once `manifest.md` existed,
  which pushed agents towards hand-editing the agents' own config files. A real connection
  (`curl`, a script) is still refused.
- **No Kiln in the home folder or a drive root.** `folder_check.py` (in Kiln and in kiln-start)
  runs first in `/kiln-start:here` and `/kiln:setup` and stops there: in the home folder a
  project install is the user's whole setup (`~/.claude/settings.json`, `~/.codex/config.toml`,
  `~/.codex/agents`), and `git init` would take in the whole profile.
- **Other programs' JSON is merged by a script.** New `scripts/json_config.py merge` (also in
  kiln-start): deep merge, lists joined, BOM and JSONC read, the result parsed before an atomic
  write, the original kept as `.kiln-backup`, a file that does not parse left alone. Setup,
  `/kiln-start:here`, README and GUIDE use it for `.claude/settings.json`,
  `.github/copilot/settings.json`, `opencode.json`, Unity's `Packages/manifest.json`, an Unreal
  `.uproject` and `~/.kiln/machine.json` - all were edited by hand before, and a broken one
  turns Kiln off or stops the program from starting. Kiln's own `~/.kiln/*.json` now read a
  BOM, and a file that does not parse is kept as `<name>.broken-<time>` instead of being
  replaced by a one-key file on the next save.
- **Claude Code background subagents.** Claude Code in fork mode (interactive since 2.1.232) runs
  every subagent in the background and the Agent tool has no `run_in_background`, so the run
  skill's "delegate in the foreground" could not always be obeyed: it now says to wait for the
  role's completion notification and never end the turn while a role runs. Headless autopilot
  (`claude -p`) is started with `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`: by default `-p` drops
  background work after 10 idle minutes (Claude Code docs, env-vars and headless pages).
- **Skill descriptions within the Agent Skills limit.** doors, fluids-granular, riding, sky,
  traversal and weather had descriptions over 1,024 characters (the spec's limit; agents may cut
  or reject them); each is now 820-910 with the same triggers, and a test holds every skill to
  the limit.
- **`asset_budget.py` counts a LOD chain once.** A glb with `<name>_LOD0`, `_LOD1`, ... nodes (or
  meshes) counted every level as drawn, about 1.9x the real cost; now only LOD0 counts towards
  triangles, vertices and draw calls, and each chain's triangles per level are in `lods`.
- **Docs say what the code does.** README: Godot and Blender are checked in real projects, Unity 6
  and Unreal 5.8 are described and tested but not yet run in a real editor. GUIDE: the stop hook
  reminds about a missing required check, it does not block. `model`: TRELLIS.2 takes one image
  (Pixal3D is the multi-view model). `image-to-model`: QuadriFlow is not the final topology of a
  deforming mesh (hand retopology with joint loops). `track`: Suno has no public API and is not
  offered. Setup lists the `remote` generator policy. The Codex plugin description: the guard,
  not permission profiles, enforces role write limits.
- **`image-to-model` generator table updated (2026-10-19):** Tripo API v3 (v2 shuts down
  2026-10-31; ≈$0.10-0.40 per model), Meshy 7.1 (API keys need a paid plan), Rodin Gen-2.5 (API
  only on the $120/month Business plan, ≈$0.75 per model), Pixal3D carries TRELLIS.2's nvdiffrast.
- **Codex: forked sessions get the Kiln context.** The SessionStart matcher also takes `fork`
  (Codex 0.155+); a forked session started without the project state.
- **Paid generators on the user's account (`api-generators`, Meshy first).** `gen_api.py`:
  `services` / `balance` / `estimate` (free calls; prints the question for the user: credits,
  about how many dollars, balance before and after, the output licence on their plan) / `submit`
  (only for a fresh, unchanged estimate, within `gen_spend_cap_usd` and `gen_daily_cap_usd`, a
  service in `gen_services`; a failed create is never resent) / `status --wait` (downloads into
  `art/generated/<asset>/` with `provenance.json`) / `jobs`. Keys only from the environment or
  the user's stored environment, scrubbed from every message. Tested against a local fake
  Meshy API with a sentinel key; checked live on the user's Meshy account: balance 1500, one
  image-to-3D on meshy-6-lite estimated at 15 credits, balance after 1485, a valid GLB that
  `asset_budget.py` reads.
- **Meshy rigging and animations.** `estimate meshy rigging --from <image-to-3d job>` (or
  `--model <humanoid .glb>`; 5 credits) and `estimate meshy animations --from <rigging job> --opt
  actions=92,15` (3 credits per action, up to 10 clips in one file); `actions meshy --search walk`
  lists the animation library for free. `--from` checks the earlier job's kind and that Meshy
  still keeps it (3 days). Results go to `art/generated/<asset>/rig/` and `anim-<ids>/`, each with
  `provenance.json`. Checked live: a humanoid GLB rigged (rigged GLB/FBX, walk, run) and one clip
  applied, 8 credits as estimated.
- **Spend requests under autopilot.** `gen_api.py request <job> --why ...` adds the estimate to
  `production/SPEND_REQUESTS.md` and the run goes on with work that needs no money; the
  autopilot report asks one yes/no per row; `submit` takes a request for 7 days and marks the row
  submitted. A paid generation is no longer a hard stop of autopilot by itself.
- **Guard: the user's yes, vendor MCP servers, library downloads.** `gen_api.py submit` needs a
  user message newer than the estimate (read from the Claude Code transcript; fails open
  elsewhere); `actions` is a free call. A paid vendor's own MCP server (Meshy, fal, Replicate,
  ElevenLabs, ...) follows `model_generators` / `audio_generators` and under autopilot only its
  read calls run. `assets_api.py fetch` is refused with `asset_libraries=off`. Checked live in
  Claude Code 2.1 with the dev plugin: an estimate against a fake Meshy ran, the agent's own
  `submit` in the same turn was refused (nothing spent), and with the policies off both
  `gen_api.py estimate` and `assets_api.py fetch` were refused.
- **More free libraries, imports and CREDITS.md.** `assets_api.py` adds Kenney (pack pages and
  zips; CC0 checked in each pack's `License.txt`), KayKit (GitHub; `--format`, `--only`, git blob
  checksums), game-icons (CC BY 3.0 with the author's credit line, CC0 authors from
  `license.txt`) and Google Fonts (licence and files from `METADATA.pb`, the licence file
  downloaded with the font); kinds `sprite`, `ui`, `audio`, `icon`, `font`. `import <folder>`
  records assets the user downloaded by hand (Quaternius QAL and Sonniss flagged: keep the raw
  files out of a public repository). Downloads are assembled in `<id>.part` and kept only when
  every check passed; `search all` lists a source that is down under `errors`. `licenses.py
  build` also writes `production/CREDITS.md` (required attribution, fonts, courtesy thanks) and
  no longer lists a library font twice. Checked live on all four new sources.
- **Image-to-3D inputs: concept first, views checked.** New `view_consistency.py`
  (image-to-model): opposite views must be mirror images; it compares the top, bottom and side
  outlines (an IoU check passed a 4 % wheelbase error at 0.985) and says pass, warn or fail -
  fail means one image instead of a multi-view run. `silhouette_iou.py` reports the same outline
  disagreement and gates on it with `--max-disagree` (0.08 for hard surface). image-to-model gets
  the input-view rule table, §2a concept first (checklist, pose options, image-model licences)
  and §2b the view check; `model` step 3 and `art-2d` follow; the tools catalogue flags
  nvdiffrast in Pixal3D and lists MeshAnything V2, FastMesh, FLUX.2-dev and FLUX.2-klein-9B as
  not offered (non-commercial).
- **Series style anchor.** New `style_anchor.py` (asset-pipeline; numpy, the glb read
  directly through the new shared `glb_mesh.py`): `extract` the anchor's style statistics,
  `check` a follower (triangle and texel density, edge sharpness for bevels, hard-edge share,
  part sizes, flat-surface share, materials, palette in Lab with CIEDE2000, values, silhouette
  solidity and outline; never silhouette IoU, members are meant to differ in shape), and
  `calibrate` the tolerances on approved members. asset-pipeline gets a "Series" section
  (anchor folder, style sheet, shared parts helpers, the art-director's lineup), `model` and
  `blender-modeling` follow, and `plan` gives asset tasks `series:` and "library first".
- **Authored LOD chains.** blender-modeling `lod_build.py` builds `<name>_LOD1..n` (about 50 %
  triangles per level, at least a 25 % cut, sub-pixel parts left out, skip rules under 256 and
  1,000 triangles) and stores each level's switch size from its measured error (two-sided
  Hausdorff distance, 1 px at the target resolution) as glTF extras; `lod_shots.py` renders LOD0
  and each level at that size. asset-pipeline `lod_check.py` gates the chain: triangle ratio,
  chain length, outline distance in game pixels (p95 ≤ 1, max ≤ 2), boundary shift, shading
  and triangle size (warn until calibrated), materials per level; `asset_budget.py` checks an
  optional `lod_ratio`. engine-godot `kiln_lod_ranges.gd` (an import script) turns the levels
  into visibility ranges. asset-pipeline gets a "LOD chain" section (when to skip, the formula,
  per-engine import); optimization, engine-unity and engine-unreal follow. Checked end to end in
  Blender 5.2 and Godot 4.7.2 (headless): a 4k-triangle rock halves twice, a 3 mm bolt leaves
  at LOD1, the extras survive export and import, the ranges match the formula.
- **Rig by on-screen size, deformation checked.** New animation `deform_check.py` (Blender):
  stress poses from the range-of-motion table with linear blend skinning (Preserve Volume off),
  measuring weight hygiene, joint centres, ring volume, candy-wrapper on forearm twist, shoulder
  collapse, edge stretch, crossings and mesh volume; bones found by name (Mixamo / Meshy,
  Rigify, Unreal, Godot humanoid). The animation skill gets the rig budget by
  `on_screen_height_px` (bones kept only when the move list needs them and they cover ~4 px) and
  the check after every rig; the animator runs it before any clip; the game-designer writes
  `on_screen_height_px` per character and controls-camera gives the formula. Checked in
  Blender 5.2 on a tube rig: smooth weights blend, hard weights have no ring, a plain forearm
  twist shows the candy-wrapper (0.78).
- **Joint topology and the bend test.** New blender-modeling `joint_topology.py` (bmesh): per
  joint found from the bone names, the limb radius, the joint band, quad edge loops walked around
  the limb (closed, 330° coverage, tilt ≤ 30°), poles and triangles in the band, with loop
  targets per mesh class; and `joint_bend.py`: a temporary copy on automatic weights bent at
  elbows and knees (90/120°) and shoulders and hips (90° abduction) with linear blend skinning,
  gated on the cross-section area kept (≥ 0.75 / ≥ 0.60; crossings and stretch warn until
  calibrated). blender-modeling QA, `model`, `image-to-model` route C and `animation` require
  both before rigging a deforming mesh. Checked in Blender 5.2 on an arm tube: rings every 1 cm
  give 7 loops and 0.83 of the area at 90°, rings 12 cm apart none and 0.71, triangles none.
- **`video_generators` policy.** Video models (animation reference clips) get their own
  setting, `off` / `local` / `remote` / `api` (default `off`), so a yes to image-to-3D does not
  cover them: the guard knows local video models (Wan, LTX, CogVideo, HunyuanVideo, FramePack)
  and video APIs (xAI, BytePlus, MiniMax, Kling, Runway, Veo by model name only - the Gemini host
  also serves text). The tools catalogue offers Wan 2.2 TI2V-5B (fits 8 GB through ComfyUI
  offloading), Wan 2.1 FLF2V-14B (first and last frame) and LTX-2 (flagged: a paid licence at
  $10M revenue), lists HunyuanVideo 1.5, FramePack, CogVideoX, Sora 2, Wan 3 and the
  non-commercial pose tools as not offered, and gets an on-request `pose` tool (rtmlib in its
  own venv: a new `venv` source kind, installed only on the user's yes). Settings, setup,
  doctor, the session line, the manifest template and the gpu-server skill follow.
- **Video reference for animation.** New animation `video_ref.py`: `frames` (ffmpeg), `pose`
  (RTMPose through rtmlib, from the on-request `pose` venv), `gate` (confidence, scale and limb
  drift one cycle apart, camera drift, held frames, loop seam), `period` (cycle and loop cut by
  autocorrelation), `keys` (contacts as the ankle reaching the ground band, swing knee peaks),
  `compare` (our render against the reference: circular phase, DTW, sagittal joint angles,
  PCK, period, key timing within one source frame) and `noise` (the estimator measured against
  true joints, widening thresholds to 2 sigma). New reference `video-reference.md` (sources and
  licences, the input render, the prompt, the rule that Kiln's limits win), an animation section
  and acceptance row, the animator's loop, reads-wrong 15 and 16. Checked live on a
  public-domain Muybridge walk: keypoints on all frames, a 1.0 s period at correlation 1.0, and
  `compare` against itself shifted passes; a held-frame mp4 and moving cameras fail their gates.
- **Install audit leftovers.** The `.gitignore` template anchors engine folders to the project
  root (`/export/`, `/Saved/`, `/Binaries/`, ... and Unreal plugins' build folders), so a code
  folder of the same name elsewhere is no longer ignored (checked with `git check-ignore`). A
  `manifest.md` saved in another encoding (cp1251, cp1252) no longer makes every hook crash and
  fail open: it is read with replacement characters (a BOM is fine too) and listed once in
  kiln-report.md; task files, GAME.md, backlog and handoffs are read the same way. The guard
  refuses `Remove-Item -Recurse` over a folder that holds a junction (Windows PowerShell follows
  it into the shared Godot AI addon or the Kiln clone) and names the link to remove first;
  setup says how to remove a link, doctor lists junctions, unanchored ignores and a non-UTF-8
  manifest.
- **Roles preload the new skills.** The modeler, animator, artist-2d, sound-designer and
  music-producer preload `api-generators`; the art-director, modeler, level-designer,
  lighting-artist, sound-designer, ui-designer and artist-2d preload `asset-libraries` (all
  runtimes: the Copilot agents are regenerated, Codex, Gemini CLI and OpenCode read the same
  role files). Doctor checks paid service keys and balances and that the free libraries answer;
  setup's generator step leads to the key page and asks for `asset_libraries`.
- **Hooks: state-file lock on Windows.** A lock file that its holder was deleting
  (`PermissionError`) made a hook go ahead unlocked, so parallel agent starts could be lost
  (1 in 5 runs of the 20-agent test); it is now waited for.
- **Guard for paid generators and keys.** `gen_api.py` commands follow the generator policy
  (`services`, `balance` and `jobs` always; the rest only with `model_generators=api`); `submit` is
  refused while autopilot runs (spending waits for the user). No command may print or pass a key
  variable (`echo $MESHY_API_KEY`, `printenv`, `Get-ChildItem env:`, ...), and no file of the
  project may hold a value that looks like an API key (`msy_`, `tsk_`, `sk-`, ...).
- **Paid generators in `/kiln:settings`.** New settings `gen_services`, `gen_spend_cap_usd`,
  `gen_daily_cap_usd`; a table of the services (key set or not - never the key -, plan, where to
  get a key) from `keys.py status`, the plan (`keys.py plan`, it decides the output licence), a
  free key check (`keys.py check`), and step-by-step instructions for setting the key as an
  environment variable on Windows, macOS and Linux. Kiln never asks for a key in the chat.
- **`/kiln:settings api`: the key page.** `keys.py serve` opens a page on 127.0.0.1 (random token
  path, stops on Done or after 30 minutes): per service where to get a key, a hidden field, the
  user's plan, Check (a free balance call), Save (to the user's environment: Windows user
  variables, elsewhere `~/.kiln/keys.env` mode 600) and Remove; the key never reaches the chat,
  a project or the output. Manual steps for setting the variable stay for users who prefer them.
  Tested against the fake Meshy API (and the reset Windows gives when a request body is left
  unread: the page reads every body first).
- **The key page** stops 10 minutes after its tab is closed; it is in English, like Kiln's other
  pages.
- **Free asset libraries (`asset-libraries`, Poly Haven and ambientCG).** `assets_api.py`
  `sources` / `search` (by words, licence-filtered) / `info` / `fetch` (checksums checked, files
  into `art/library/<source>/<id>/` with `provenance.json` of kind `library` and the item's API
  record as evidence; ambientCG zips extracted safely). The manifest setting `asset_libraries`
  (`off` / `cc0` / `attribution`, default / `sharealike`) is the licence allow-list: anything
  else is refused before a download. `licenses.py` lists library assets by source and page, with
  their credit line. Checked live without keys: a Poly Haven texture and HDRI and an ambientCG
  material.

## 0.10.0 — 2026-10-20

- **Godot lint and the Godot 3 ban.** New engine-godot `godot_lint.py`: GDScript checked for
  Godot 3 API (`yield`, `export var`, `onready`, `setget`, `.instance()`, string `connect`,
  `KinematicBody` and the other renamed classes, `Pool*Array`, `deg2rad`, `File`, ...; each
  with its Godot 4 form), and `.tscn` / `.tres` for what loads wrong without a compile error
  (undefined resource ids, missing parents, duplicate siblings, connections to missing nodes,
  `format=2`, duplicate uids across the project, embedded scripts). The guard refuses
  `script_create` / `script_patch` and `.gd` writes with Godot 3 API and names the Godot 4 form.
  `references/known-good.gd` is a Godot 4 pattern to keep in context. Checked live: no false
  finding on two real projects (70 files), Godot 4.7.2 parses the known-good script and rejects
  `yield`, and a scene the linter fails does not load right in Godot.

- **Levels winnable, both ways.** procgen `procgen_check.py` adds side-view platformer layouts
  (reachability with the controller's jump height and width in tiles, falls, ladders, one-way
  platforms, hazards; a pit deeper than the jump is a softlock), consumed keys in grids (a key
  spent on the wrong door), push-box puzzles (solved by search over pushes with dead squares
  pruned, "unknown" past `--max-states`), softlocks in grids, and `"return": true` (the start
  reachable again from every goal and exit) for graphs, grids and platformers. level-design runs
  it on hand-made levels too. Checked on 400 generated levels: a naive push-box generator made
  152 of 200 unsolvable and a platformer generator 5 of 200 dead, all found in about 2 s each.

- **Feel constants as tested values.** New controls-camera `feel_constants.gd` (one resource
  for coyote time, jump buffer, variable jump, hit-stop and latency limits, each with its source:
  Celeste's Player.cs where it states them) and `feel_windows.gd` for headless probes: the jump
  windows after leaving the ground and before landing, measured in frames, and input latency over
  varied press frames with its jitter. qa-feel checks each window within ±1 frame of the
  resource and jitter ≤ 1 frame. Checked live in Godot 4.7.2: a controller built on the resource
  passes, one without coyote time fails.

- **2D: blob autotiles, real pixel art from AI, reviews at game speed.** New art-2d
  `autotile.py` (`build`: the 47-tile blob set from five source tiles by quarter pieces with
  `terrain.json` neighbour bits; `check`: every seam two tiles can share) and `godot_terrain.gd`
  (the set as a Godot terrain, Match Corners and Sides); `pixelfix.py` (`snap`: finds the pixel
  grid of an upscaled AI image, one colour per block, the palette cut by k-means or mapped to
  the project palette, hard alpha); `sprite_qa.py alpha` catches a painted checkerboard posing
  as transparency; `sheet.py preview` writes a GIF per animation at its game speed and a
  numbered contact sheet. Checked live: Godot 4.7.2 painted a terrain shape and picked the
  matching tile for every cell; the grid is found at block sizes 3 to 32 and refused on photos
  and noise.

- **The agent plays its own game.** New playtest `explorer.gd` (a novelty-seeking bot for an
  autoplay scenario: toward the least-visited cells, stuck steps per cell), `explore_report.py`
  (merged heatmap, worst snags, coverage of a level layout's reachable cells) and
  `input_replay.gd` (input recorded per physics frame, played back exactly with state hashes;
  after a change the first diverging frame is named). playtest makes runs deterministic by
  default (`--fixed-fps`, seeds) and names Movie Maker for review captures. Checked live in
  Godot 4.7.2: the explorer covered at least 90 % of a test maze in 120 game seconds, two replays
  matched the recording, a slower controller diverged.

- **Vision models judge captured frames, two reviewers decide.** acceptance `frames.py review`
  sends only the frames that differ from their baseline: each changed region as one image
  (baseline | new | changed pixels, cropped and enlarged) with fixed questions and a
  `review.json` to answer; `frames.py verdict` merges two independent answers (a glitch both see
  fails, a split is DISPUTED until engine data settles it, an unasked change is UNINTENDED).
  acceptance states the rule that a vision model never plays the game; the verifier uses the
  review for several changed regions.

- **Store checks before a release.** New release `store_check.py`: Steam capsules (exact sizes,
  formats, the library logo's transparent background, screenshots at 1920×1080 16:9) with a
  review pack for the no-extra-text rule and the small capsule at 120×45; Steam Deck text
  (`deck_text.gd` measures every text Control at 1280×800 with the stretch settings, hidden
  menus too; under 9 px fails); Google Play (target API 36 from the APK's binary manifest or the
  AAB's protobuf manifest, 64-bit native libraries aligned to 16 KB, APK zip offsets); web (a
  threaded Godot export needs COOP/COEP on the host, checked on the live page); and a draft of
  Steam's AI disclosure from provenance files, `production/ai-content.csv` and runtime model
  calls. ci.md gains a store-check job and macOS notarisation on a Linux runner. Checked live:
  Godot 4.7.2's Android template passes (API 36, 16 KB), its web exports are single-threaded by
  default, a threaded export fails without the headers and passes with them.

- **README and GUIDE brought up to date.** README: what is new in 0.10, the check scripts grouped
  by area, the hooks list, OpenCode 1.19.0. GUIDE: the skills, commands and touches tables, the
  hooks, and the production files the new checks write.

## Unreleased (fixes after 0.10.0)

A bug hunt by four independent reviewers (2026-10-20); every fix has a test that failed before.

- **Guard: shell bypasses closed.** Line continuations (bash `\`, PowerShell backtick) are joined
  before any check; deleting, moving or renaming framework files (`mv manifest.md`, `rm -rf
  .claude`) is refused and engine files follow the Write rules; PowerShell parameters are read
  by meaning (`Out-File -Encoding utf8 x` writes x), copies into a folder and `cp -t`, `cd` before
  a relative path, `bash -c` / `cmd /c` / `powershell -Command` and `$(...)` are unwrapped;
  `python -X utf8 gen_api.py submit` is a submit; `import os, bpy`, a here-document piped into
  python and `uv run python -` are bpy code; MCP ports by `127.1` and `[::1]`; `Stop-Process
  <pid>` is no longer refused.
- **Guard: git parsed by option.** `git add -vA`, `:/`, `-- .`, `git -C . add -A`, a folder with a
  secret staged and committed in one line, `push -uf`, `+HEAD:main`, `commit -n` are refused; a
  commit message that mentions --no-verify is not.
- **Guard: roles and paths.** Effort copies of roles (`verifier-high`) are their role; built-in
  agents (general-purpose, Codex default) follow the producer's rule and never change framework
  files; the other runtimes' configs (`.opencode/plugins/`, `opencode.json`, Copilot and Gemini
  settings, `.codex/agents/`) are protected; a role cannot create a task file naming itself;
  Windows spellings of a path (`\\?\`, `\\localhost\D$`, `::$DATA`) are the same file; `..` cannot
  leave tests/probes.
- **Paid generators' MCP servers reach the guard in every runtime** (the hook matchers only
  covered the editors' servers, so `model_generators=off` did not stop a Meshy MCP call).
- **Codex / OpenCode apply_patch**: a role's handoff appended to its task file is no longer
  refused (the patch is applied before the spec lines are compared).
- **Hooks**: a manifest with a BOM, spaces around `=` or saved as UTF-16 is read the same from
  every folder; a non-numeric lock time keeps the default instead of opening the editor to two
  roles; the editor queue has one lock.
- **Paid generators: the caps hold.** A spend ledger line that does not parse stops every submit
  (a blank line used to end the count and lift the daily cap); a create is counted before it is
  sent, so a timeout or 5xx that may have been charged counts against the cap (a refusal by the
  service is taken back); `gen_api.py decline <job>` records the user's no and submit refuses a
  spend request that is not waiting; caps that are not a number (`nan`, `-1`) stop the submit;
  `status` of a job never sent answers instead of crashing; `--opt` without `=` is explained.
- **CC BY output names whom to credit.** Meshy free-plan output gets an attribution line in its
  provenance; licenses.py and the Phase 9 gate fail a shipping CC BY item with nobody to credit.
- **No more false passes.** A probe whose script errors after some rows passed is NOT ASSESSED
  (probe_base counts script errors through a Godot Logger), and `check(..., "~", ...)` compares
  vectors by distance; a QA-contract state whose setup errors is not recorded; QA-contract UI
  states fail on ui_check layout problems (an upper-case compare never matched) and are laid out
  at the project's window size, not the 64x64 headless window; `frames.py review` packs a frame
  that fails without a region (size change, SSIM only) as one whole-frame item, and `compare` /
  `review` with no image or no baseline are NOT ASSESSED (exit 2); `autotile.py check` checks
  every pair two tiles can really show (169 each way; 47 were checked); a night run that never
  started counts as a mid-run crash; `asset_budget.py` measures textures embedded in a .gltf and
  is NOT ASSESSED for no file or a broken GLB; a capsule review needs true/false answers and the
  screenshot check before it passes; the AI-disclosure counts no longer count text inside
  "images and textures".
- **Unity and Unreal, checked against their MCP servers' sources** (no live editor yet). Unity:
  a release build with the editor open goes through MCP for Unity `manage_build` (batch mode
  cannot open a project the editor holds; `build.py` says so while `Temp/UnityLockfile` exists);
  headless `-executeMethod` runs only `KilnRelease.KilnBuild.Build` or a method in manifest
  `unity_build_methods` (a name with "build" in it is no longer enough); tool groups persist
  only through the editor's toggle window (setup turns on testing, scripting_ext, profiling, vfx
  and docs; sessions `manage_tools sync`; read-only roles may activate their groups); model
  import settings go through an AssetPostprocessor or `ModelImporter` (manage_asset reaches only
  textures); captures pass `output_folder`; `execute_code` probes that save, change assets or
  create objects are refused, and builder `execute_code` that builds scenes is too; `.anim`,
  `.shadergraph`, `.vfx`, `.spriteatlas`, `.lighting` and other editor assets are protected;
  `FindAnyObjectByType` in KilnProbe. Unreal: the UE 5.6/5.7 fallback server's `action` decides
  read or change; `find_or_create_*` is not a read; PIE through `call_tool` and Unity's Edit/Play
  menu item wait for a screen slot; plugin and subfolder `Config/*.ini` are protected;
  `-ExecCmds="py ..."` and commandlets other than cook are refused; roles accept the
  `unreal-mcp` / `unreal-mcp-proxy` server names Epic's proxy and plugin write; the Kiln toolset
  registers through `unreal.ToolsetRegistry.register_toolset_class` and logs an error when it
  cannot; an Unreal project for Kiln is a C++ project (the probe is a C++ component); Live
  Coding through the toolset is marked unverified, with a fallback.
- **Measurements to the frame.** Godot 4.7 shows a press made inside a physics tick to
  `is_action_just_pressed` one tick late (checked live), which moved coyote time by -1, the jump
  buffer by +2 and made a replay diverge from its own recording. probe_base's `ticks()` now
  resumes at the end of a tick (after every node), so a press lands on the next one;
  feel_windows counts the buffer from 1 tick before landing; frame-counter controllers read
  exactly their C and B; input_replay presses frame N's events at the end of frame N-1 and records
  analog strength changes while held. `analyze.py frames` fails on frames over --max-frame-ms
  (100) and reports 2x spikes instead of failing on them; deck_text keeps scale 1 in integer
  stretch mode below 1 (as Godot does); headless autoplay takes no screenshots and reports no
  hitches; known-good.gd no longer allows a second jump in the air.
- **Smaller fixes.** godot_lint (and the guard) no longer refuse a Godot 4 method chain whose
  lines start with `.`, nor a node under an editable instanced scene; `json_config.py merge`
  replaces program lines (`command`, `args`) instead of joining them, merges `Plugins` entries
  by `Name`, and reads UTF-16 files; procgen platformers pick up keys mid-jump, and a push-box
  level that starts solved is solved; Poly Haven HDRIs fall back to the nearest size at or below
  the request (not 16k) and record the size used; explore_report's reachable cells come from the
  procgen search (void, legend walls and air no longer count); silhouette_iou fits a render on
  another canvas size without stretching it and reads Windows paths in `--pairs`.
- **Every agent gets its own instructions.** README and GUIDE say how to update Kiln in each agent
  (Codex: `codex plugin marketplace upgrade kiln` replaces the installed copy, checked live;
  Gemini CLI, Copilot CLI, OpenCode, skills-only agents); `/kiln:update` refreshes the plugin and
  regenerates the per-project copies (Codex and OpenCode roles) in whichever agent runs it;
  `/kiln:doctor` checks MCP servers and the hooks in Gemini CLI, Copilot CLI and OpenCode too
  (each runtime's guard payload, checked to deny); the new-version notice and the session's
  command hints name each runtime's own commands (Copilot and OpenCode were told slash commands
  they do not have).
- **The Gemini branch explains itself.** The `gemini-extension` branch gets a README (built by
  gemini_extension.py): why Gemini's build lives on its own branch, the `--ref` that installs
  it, turning it on in a project, setup and update. The main README links the branch. Copilot
  CLI's install, disable, enable and update were checked live with 1.0.100 (`kiln` and
  `kiln@kiln` both work).
- **A Codex config broken by an older Kiln is found and repaired.** Field report: the Codex app
  said "Can't verify project trust" on a machine with Kiln 0.7.0, which had agents append to
  `~/.codex/config.toml` by hand (a block glued to the next table header hides the trusted
  projects). `kiln_update.py status` now checks the user's and the project's Codex config and
  names the `codex_config.py --repair` fix; doctor checks both files; setup checks first on a
  machine that had an older Kiln.

