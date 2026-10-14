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

