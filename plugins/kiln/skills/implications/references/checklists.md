# Implication checklists by category

Each category adds keys to the core eight (job, states, home, interfaces, empty, transitions,
ripple, premortem). The checker requires the category keys too; write `n/a — <reason>` when a key
truly doesn't apply. Keep the most critical questions first — long lists lose their middle.

## handheld (weapons, tools, torches, keys)
Extra keys: `grip`, `carry`.
- grip: grip and stow sockets (two), which hand(s), hand pose, off-hand IK point (foregrip).
- carry: position by size — small on belt, chest, boot or thigh; long on a sling or the back
  (a back-draw is a stylisation: real long blades on the back were taken off to draw); draw hand vs
  carry side (cross-draw on the weak side); retention (strap, friction, thumb-break) and whether it
  shows; the empty holster/sheath; first- and third-person models; world/pickup model and icon;
  equip/unequip/pickup/putdown sounds; impact sets; damage states; which locomotion set or
  upper-body overlay it needs while held (traversal skill: held items).

## wearable (armour, helmets, packs, kits, clothing)
Extra keys: `region`, `left_behind`.
- region: body region and what it conflicts with (Team Fortress 2 equip regions exist to stop
  clipping); mounting standard (rail, MOLLE 1 in webbing / 1.5 in spacing, clips); joint range it
  takes away (traversal: clothing and gear).
- left_behind: hardware that stays on the host when it is removed — a port with a cap or a
  self-closing valve, a rail, a mount, belt loops; hose and cable routing (side, length, strain
  relief, swing via spring bones); quick release; stowed position of sub-parts (visor up, goggles
  on the forehead); what the first-person camera sees.

## consumable (ammo, food, medkits, fuel, batteries)
Extra keys: `container`, `after_use`.
- container: pouch or slot, is the count visible on the model, partial state (half full).
- after_use: use animation and duration, what happens to the empty container (dropped, kept,
  refilled), refill source, effect feedback on the HUD and on the model (Dead Space shows health
  on the suit's spine).

## vehicle-part (wheels, doors, turrets, armour panels, engines)
Extra keys: `mount`, `removed`.
- mount: fasteners and mount; mass and collision change; access for maintenance.
- removed: what the mount looks like with the part gone; damaged and detached states; the view
  from the driver's seat.

## environment (doors, switches, containers, ladders, cover)
Extra keys: `signifier`, `persistence`.
- signifier: what tells the player it can be used and where (handle, glow, wear) — affordance vs
  signifier (Norman); used, empty and broken states.
- persistence: saved state; navigation and cover changes; AI awareness.
- doors, gates, hatches, curtains, car doors: clear width vs capsule and navmesh, push/pull side
  and hand, locked/breached states, AI through it — the doors skill.

## ability (powers, gadgets' effects, skills)
Extra keys: `source`, `unavailable`.
- source: where it comes from in the fiction (a device on the body, the body itself) — a device
  is a wearable or handheld and gets that checklist too.
- unavailable: telegraph and feedback, cooldown display, input conflicts, how the character looks
  when it can't be used.

## Conventions worth knowing

- Knife carry: strong-side belt, cross-draw (weak side), chest (MOLLE; easiest seated in a
  vehicle), boot or ankle, neck (handle down, friction or magnet); scabbard parts: throat,
  locket with ring or stud, chape; fighting-knife sheaths tie to the leg with a thong.
- Holsters: belt (dominant side), cross-draw, shoulder, small of back, ankle, chest, thigh (where
  the hand naturally hangs); retention levels I–III; rigid holsters allow one-handed re-holstering.
- Breathing gear: filters screw on directly or via a flexible hose (40 mm threads on newer masks);
  intakes have sealing caps; regulator ports unused → screw-in plugs; quick-connects self-seal when
  disconnected; hoses come to the mouth from the right on diving regulators; rebreather hoses have
  airtight end connections and are kept short; SCBA packs ride on the back and live on a rack.
- Helmets: side rails carry lights and cameras; a front shroud carries night vision with a bayonet
  adapter.
- Every idle connector gets a cap, plug, cover or self-closing valve — the "empty state" of
  physical gear.

## Worked example — removable breathing kit (the live miss)

- job: emergency air in smoke or vacuum; put on fast, taken off when safe.
- states: off (unit on the floor or back mount empty), donning, on, doffing, depleted.
- home: back mount on the suit's back plate (PROXY); world prop when off.
- interfaces: hose ↔ helmet port (bayonet quick-connect, both sides keyed); unit ↔ back mount
  (clamps) — host assets: two helmet ports, back mount.
- empty: ports capped (self-closing shutter with a dark face) and read from the third-person
  camera; back mount visible with the unit off; hose ends capped on the unit.
- transitions: lift, swing on, clamp, plug left then right; reverse to take off; not while
  hanging or swimming.
- ripple: helmet sockets for ports; hose routing clear of the pauldrons in run and arm raise; HUD air
  gauge; save state; breathing sound on/off; AI hears the hiss.
- premortem: hoses clip the pauldrons; port invisible from the game camera; reaching back exceeds
  the shoulder range the armour allows.
- left_behind / region: back plate and both helmet sides.
