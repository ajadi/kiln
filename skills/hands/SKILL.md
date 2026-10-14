---
name: hands
description: Hands that hold things believably — the grip per object (pistol, rifle, sword, knife, shield, lantern, ledge, ladder, rope, wheel, handlebars, door handles, small items) from the grasp taxonomy, finger and wrist ranges for rigs, the resting finger cascade, handle diameter from hand size, arm IK to grip sockets and finger pose libraries, two-handed holds that do not drift, climbing hand placement, and exact checks (finger range, support-hand drift, wrist deviation, contact and penetration) in hands_check.py, with Godot/Unity/Unreal setup. Use when a character holds, grabs, carries, climbs or operates anything, and when hands look wrong.
user-invocable: false
---

# Hands

A held object reads wrong when the grip is the wrong type, the fingers go through it or float off
it, or the support hand slides along a weapon. Pick the grip from the object, pose the fingers
inside their ranges, pin the hands to sockets on the object, and measure with
`${extensionPath}${/}skills${/}hands/scripts/hands_check.py` (stdlib Python, Bash). Arms, posture and the weight of
what is held are in traversal (carried load, clothing and held items); body joint ranges in
human-biomechanics. Values marked (working) are proposals, not measured standards.

## 1. The grip comes from the object

Power grip clamps the object between flexed fingers and palm with the thumb pressing back; precision
grip pinches it between finger pads and thumb; the task decides which (Napier). The hook grasp
(fingers flexed, no thumb, arm hanging) carries lanterns, buckets and bags. The most common grasp
in daily life is the medium wrap (12.7 % of grasps, 23.8 % of the time; Feix GRASP taxonomy).
`predict grip --object <name>` prints the row.

| Object | Grip |
|---|---|
| Pistol | strong hand high on the grip; support heel fills the gap, support thumb forward along the slide, fingers over the strong fingers ("c-clamp"); trigger finger straight on the frame when not firing |
| Rifle | strong hand power grip on the pistol grip; support hand on the handguard or foregrip (working); measured aim: trigger wrist 21 ± 9° ulnar, support wrist 47 ± 11° ulnar, elbows 118° / 103° |
| Sword | two hands: close together, lead hand under the guard, rear hand at or just above the pommel, last three fingers grip, index and thumb relaxed; one hand: hammer grip (working) |
| Knife | hammer (full wrap), saber (thumb on top or on the spine), reverse / icepick (blade down) |
| Axe, hammer, torch | cylindrical power grip sized by the handle diameter (working) |
| Shield | forearm through the enarmes straps, hand on the grip strap; guige sling to carry — not a centre grip |
| Lantern, bucket, bag | hook grasp, fingers lightly flexed, arm hanging; a narrow handle cuts grip strength |
| Ledge | crimp: PIP 87 ± 12°, DIP hyperextended −11 to −28°, MCP 23–44°; half-crimp PIP 70°; open hand PIP 39°, MCP 4–13° |
| Ladder | at least one hand grasping, three points of contact, rungs before rails |
| Rope | both hands overhand above the head, power grip; the legs do the work through a foot lock |
| Steering wheel | hands at 9 and 3 (8–9 and 3–4 o'clock), push-pull steering |
| Motorbike bars | four fingers on the throttle, thumb under, wrist straight; 1–2 fingers may cover the brake |
| Door handle | levers and pull handles: no tight grasp or wrist twist; round knobs need a twist |
| Small items | tip pinch, palmar pinch, tripod or lateral pinch by size and task |

The grip also sets the item's sockets: where each hand goes, the palm direction, and which fingers
close. Put them on the item (implications: both sides of every attachment).

## 2. Hand numbers for rigs

| Joint | Flexion | Extension |
|---|---|---|
| Finger MCP | 85–90° | 30–45° |
| Finger PIP | 100–115° | 0° |
| Finger DIP | 80–90° | 20° (to 28° only in a crimp) |
| Thumb CMC | 45–50° | — |
| Thumb MCP | 50–55° | 0° |
| Thumb IP | 85–90° | 0–5° |
| Wrist | 80–90° | 70–90°; radial deviation 15°, ulnar 30–45° |

- **Everyday use sits in the middle**: MCP 19–71°, PIP 23–87°, DIP 10–64°; wrist tasks fit inside
  extension 60°, flexion 54°, ulnar 40°, radial 17°. A pose near the ends of the range reads
  strained.
- **Resting hand is a cascade, not flat**: PIP index 39°, middle 41°, ring 45°, little 43°, wrist
  15–20° extended; summed finger flexion ~80–89°, index least. Workers who grip all day rest more
  closed (sums 123–130°). A flat open hand on an idle character reads dead (animation: idle).
- **Hand length** (wrist crease to middle fingertip), 5th / 50th / 95th: men 175 / 191 / 205 mm,
  women 160 / 175 / 190 mm; breadth men 80 / 90 / 100, women 65 / 75 / 85 mm.
- **Handle diameter** for a power grip ≈ 19.7 % of hand length (comfort peak 30–40 mm; finger force
  falls as it grows): women 5th 31.5 mm, men 50th 37.6 mm, men 95th 40.4 mm. `predict handle
  --hand-length <mm>`. A handle much thicker than this needs an open hand pose, not a closed fist
  through the mesh.

## 3. Building it

1. **Arm to a socket**: two-bone IK from the shoulder to a grip socket on the object, with a pole
   (elbow) target so the elbow points the natural way (out and down for a rifle support arm, out
   of the wall when climbing).
2. **Fingers from a pose library**: author one pose per grip (open, hook, wrap per diameter, crimp,
   pinch, trigger-off / trigger-on) and blend between them per finger; IK on fingers only to close
   the last millimetres onto the surface.
3. **Two-handed items**: the strong hand drives the item; the support hand is IK-pinned to a socket
   on the item every frame, after aim offsets and recoil — otherwise it slides along the weapon.
4. **Climbing and grabbing**: ray from the animated hand toward the surface, use the hit point and
   normal as the IK target, blend the weight in near contact, and keep the elbow out of the wall.
5. **Hand-offs**: an item passed between hands or onto a socket on the body (holster, back) switches
   parent on one frame, with both hands on it for the overlap.

## 4. Checks

| Check | Command | Gate |
|---|---|---|
| Finger range | `rom <dump> --joints name=mcp,...` | every joint inside §2 (DIP to −28° only with `--crimp`) |
| Support hand stays on | `drift <dump> --hand H --grip G [--when held]` | ≤ 5 mm (working) while held, also through aim, recoil and locomotion |
| Wrist | `wrist <dump> --radial R --ulnar U [--support]` | radial ≤ 15°, ulnar ≤ 45° (support hand on a rifle ≤ 58°) |
| Contact | probe the distance from each specified contact point to the surface | ≤ 5 mm (working; grasp research counts < 5 mm as touching) |
| Penetration | deepest hand vertex inside the object | ≤ 2 mm (working) |
| Handle | `predict handle --hand-length L` | handle within ±5 mm of the result, or an open pose authored for it |

Capture a close-up of each grip from two sides in the running game; hands are judged up close.

## 5. Engines

- **Godot 4.6/4.7**: `TwoBoneIK3D` (needs a pole not colinear with the forward axis) for arms;
  `IterateIK3D` with `JointLimitationCone3D` per joint for fingers — defaults `max_iterations` 4
  and `angular_delta_limit` 2° cap a finger at 8° per frame (~480°/s at 60 fps), so raise them or
  set `deterministic` for fast closes; `BoneTwistDisperser3D` spreads wrist twist up the forearm
  (twist past 180° flips); `LimitAngularVelocityModifier3D` (default 360°/s) smooths large
  deterministic IK jumps; `BoneAttachment3D` in follow-only mode for item sockets (its
  `override_pose` path misbehaves next to modifiers). Modifiers run after the AnimationMixer, in
  tree order.
- **Unity 6**: Animation Rigging Two Bone IK (target + hint) for arms, Chain IK for fingers,
  Multi-Parent for hand-offs; Final IK InteractionTarget + HandPoser match fingers to a posed copy
  of the hand; Animator `OnAnimatorIK` weights 0–1.
- **Unreal 5.6–5.8**: Pose Assets for finger poses (Pose Blender); Hand IK Retargeting for weapon
  hands; the IK Retargeter Weapon Goals op uses `ik_hand_gun` as the parent of `ik_hand_l/r`;
  virtual bones as weightless IK targets keep a support hand on a rifle.

## 6. Reads wrong

| What the viewer sees | Usual cause | Fix |
|---|---|---|
| Support hand slides along the weapon | IK target set before aim offset or recoil | pin to the item socket last, every frame |
| Fingers through the handle | one closed-fist pose for every diameter | pose per diameter (§2) |
| Fingers hover off the handle | pose made for a thinner grip | close with finger IK to the surface |
| Stiff flat hand at rest | no cascade | resting pose §2 |
| Wrist snapped sideways | target forces deviation past range | move the socket or rotate the item in the hand |
| Lantern held like a sword | power grip where a hook grasp belongs | grip table §1 |
