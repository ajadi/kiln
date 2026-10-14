---
name: implications
description: Think through the consequences of a new thing before anyone builds it — for every item, weapon, wearable, gadget, consumable, vehicle part, prop or ability the user asks for, work out its job, states, where it lives when not in use, both sides of every attachment and what each looks like when the other is absent, how it is drawn, stowed, put on and taken off, what else it touches (rig sockets, outfit clearance, movement, input, HUD, save, AI, audio, accessibility) and how it could look wrong, then write the decisions into the task as an implications section the roles build from (decided for the user under user_gates=proxy), checked by implications_check.py. Use when a request or design introduces a new thing, before the task is written or delegated; also when reviewing a model or feature for missing pieces.
user-invocable: false
---

# Implications

The user names the thing; the studio thinks of everything the thing implies. "We need a dagger"
already means a sheath, a place on the body, a draw and a stow, an empty sheath when the dagger
is in the hand, sounds, a save state. Live miss: a removable breathing kit was planned without the
helmet port its hoses plug into, and without asking how that port looks when the kit is off — the
user had to point both out. That is this skill's job, not the user's.

Run it when a request or design adds a new thing, before the task file is written or delegated.
Write the result into the task as `## implications` (format in §4) and run
`${CLAUDE_SKILL_DIR}/scripts/implications_check.py tasks/TASK-NNN.md`. Category checklists and
worked examples: `${CLAUDE_SKILL_DIR}/references/checklists.md`.

## 1. Core questions — for every new thing

1. **Job**: what it does and in which circumstances (combat, emergency, calm) — that decides
   which states matter (jobs to be done).
2. **States**: a state table, one state at a time — e.g. absent, stowed, readying, in hand /
   active, stowing, depleted, broken, dropped in the world. For each: look, sound, input, HUD, can
   the character move. Equipment runs as its own state machine beside movement.
3. **Home**: where it is when not in use (body, vehicle, world) — what carries it, the carrier's
   capacity, and which body region it occupies (and what it now conflicts with).
4. **Interfaces, both sides**: every connection has two sides (dagger ↔ sheath ↔ belt; hose ↔
   helmet port). The host side is a new asset someone must build (port, socket, sheath, rail,
   mount, belt loop).
5. **Empty states**: what each side looks like without the other — the empty sheath, the capped
   or self-closing port, the hose end, the bare mount. Real gear caps every idle connector
   (gas-mask intake caps, regulator port plugs, self-sealing quick-connects, remove-before-flight
   covers); a shadow board shows where a tool belongs when it's missing.
6. **Transitions**: draw, stow, put on, take off, pick up, drop, use — which hand, how long, can it
   be interrupted, and the edge cases: running, crouched, climbing, swimming, mounted, hands full.
7. **Ripple** (two rings at most): rig socket and grip/stow sockets, outfit clipping and body
   regions, movement and joint range (clothing-and-gear section of the traversal skill), input,
   icon/HUD, save, AI awareness, sound per transition, VFX, text strings, accessibility (never
   colour- or sound-only).
8. **Pre-mortem**: "it shipped and looked wrong — why?" — the top three ways (clips the thigh in a
   sprint, port invisible from the game camera, draw hand crosses the body armour).

## 2. Keep it small

An implication stays only if: the player sees, hears or does it at the game's camera and scope;
or it blocks or changes another asset or system (an interface); or it is cheap now and expensive
later (socket placement, host-side hardware). Tag each with MoSCoW (must / should / could), keep
about ten per thing, stop at two rings — feature creep and gold-plating are real risks.
"Hammerspace" (items from nowhere) is allowed only as a stated choice.

## 3. Decide, don't ask

Under `user_gates=proxy` the implications are decisions: pick the believable default (references
§ conventions), mark it `(PROXY)`, list it in the report so the user can redo it. Ask only when a
choice changes what the player experiences in a way the brief can't settle (`grilling` skill).

## 4. Task section format (checked by the script)

```markdown
## implications
### dagger (category: handheld)
- job: backup blade for close quarters and cutting ropes; drawn in combat and while climbing
- states: stowed, drawing (0.4 s), in hand, stowing (0.5 s), dropped
- home: cross-draw sheath on the left hip, angled 30° forward, strap retention (PROXY)
- interfaces: dagger↔sheath (friction + strap snap); sheath↔belt (two loops) — host assets: sheath, belt loops
- empty: sheath stays on the belt, strap hangs open, mouth visible from the 3rd-person camera
- transitions: right hand draws across the body; no draw while hanging from a ledge; stow blind by feel
- ripple: sockets hand_r/grip and hip_l/sheath; sheath vs thigh clearance in sprint and crouch; icon; draw/stow sounds; save state; guards notice a drawn blade
- premortem: sheath clips the thigh when sprinting; draw hand passes through the chest plate; empty sheath reads as a pouch
- must: home, empty, transitions · should: AI notice · could: rope-cutting interaction
```

Categories: `handheld`, `wearable`, `consumable`, `vehicle-part`, `environment`, `ability` — each adds
its own keys (checklists reference). Every key needs content or `n/a — <reason>`.

## 5. Who uses it

- **Producer (run, plan)**: when a request or design adds a thing, write the section before the
  task is delegated; the checker must pass. The modeler builds host-side parts and empty states
  as listed; the animator authors the transitions; gameplay wires the states.
- **Game designer / concept**: specs list the implications of each new mechanic or item.
- **Art director / verifier**: every `interfaces` host asset and every `empty` state exists and
  reads from the game camera; the pre-mortem risks were checked.
