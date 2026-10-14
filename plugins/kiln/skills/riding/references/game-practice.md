# How games build riding — practice notes

What shipped games did, so a design can copy or reject it on purpose. Sources in
the research notes for this skill (kept in Kiln's development repository); (snippet) = from a search summary only, [U] = unverified.

## Red Dead Redemption 2 (Kleanthous, GDC 2021 AI Summit; Game Developer write-up)

- ~6300 locomotion motions shared by horses, other animals and humans; 19 breeds; four gaits.
- Each gait clip stores a minimum, ideal and maximum speed (tied to exertion, not a fixed speed).
- Blending on linear, angular and lateral velocity plus pitch and lead foot: six 3D blend spaces;
  blend points placed automatically from analysis of each clip, not by hand.
- Speed changes are continuous acceleration and deceleration cycles that watch the speed change over
  a window and switch clips in step with the feet; a custom deceleration cycle keeps stops responsive
  while leaving room to change one's mind.
- Turning in place pivots around the front feet, not the body centre. Moving turns add strafing and
  drift, so the player guides the horse rather than steering a car.
- Slopes: incline, decline and flat clip groups blended by pitch; surface angles read from the
  navmesh along the path; deep water, snow and mud detected; reactions vary with snow depth.
- Collision prediction strafes the horse onto a safer path, toned down so players can still hit a
  tree. Designers tag cliff edges; a speed-penalty system works out the halt from distance, speed and
  foot timing and plays a halting clip.
- Rider sync: horse clips carry rhythm metadata (footfalls, high and low body points); rider clips
  carry matching rhythm tags.
- Motivation (utility AI): agitation (gunfire, a nearby bear), tiredness, injury. High values change
  the available clips and can override the player. Patting lowers agitation.
- Euphoria: a rider whose horse is shot rolls off or is dragged by a stirrup (snippet).
- Controls: tap to raise speed, hold to keep it [U].

## Zelda: Breath of the Wild

- Ridden horses avoid obstacles and follow paths by themselves ("Real horses don't run into trees
  very often").
- Affection 0–100: low → bucks, drifts off course, rebels (soothe to raise it); at maximum the horse
  refuses only impassable terrain.
- Stamina stat = number of speed boosts (spurs), 0–5; damage takes the boosts away; an Endura
  Carrot gives three more.
- Mount from any angle; sneak up on wild horses; jumping off starts slow-motion bow aiming.
- Whistle calls a registered horse if it is in range.

## Others

- **Shadow of the Colossus**: Agro sometimes ignores commands and avoids danger on its own; how often
  was balanced against playability. Base motion hand-keyed, physics and IK adjust posture on uneven
  ground.
- **Ghost of Tsushima** (critic's review): walk and trot blended by stick deflection, no calm canter;
  the tight-turn canter is wrong; mounting and dismounting without stopping; the horse jumps by
  itself.
- **Assassin's Creed**: Origins follows the road or rides to a marker by itself (snippet); Shadows
  shipped without auto-follow and restored it in a patch — players expect it in open worlds.
- **Mount & Blade**: damage depends on speed relative to the target; a couched lance at speed does
  several times normal damage (guide, snippet).

## Design patterns

- **Input**: stick deflection picks walk and trot (analogue); a button raises the gait one step and
  holding keeps it (working); a limited sprint (spurs) costs stamina; auto-follow road and ride to a
  marker with a cinematic camera; call the horse (whistle) with a range; a brake that stops by gait
  distance (`predict stop`), not instantly.
- **Camera** (working, no sourced data): behind and above the rider, pulling back and widening FOV
  by gait; lag the yaw in turns; damp the vertical bounce at the saddle frequency instead of locking
  it (a locked camera hides the gait); keep the horse's head out of the aim line; on auto-travel a
  wider cinematic framing. Rigs and numbers: controls-camera skill.
- **Combat from the saddle**: speed adds to melee damage (relative speed); limit aim arcs per side
  (the horse's head and neck block the front; a right-handed swordsman covers the right side)
  (working); aim sway follows the saddle bounce (working); gunfire raises the horse's agitation
  unless it is trained (RDR2).
- **Stamina and will**: a stamina pool spent by gallop and spurs, refilled at slower gaits; bond
  raised by feeding, patting and calming; low bond → bucks, refusals, drift; panic (rear, bolt) from
  predators, gunfire, fire — a rider can calm it. Decide how often the horse disobeys and keep it
  rare enough to stay playable (SotC).
- **AI mounts and companions**: the horse is an agent with its own navigation agent (bigger radius
  and height, its own navmesh — game-ai skill), its own perception (wide field of view, startles from
  behind), and a motivation layer. A riderless horse waits, grazes, follows or comes when called; NPC
  riders use the same rig, sync and checks as the player.
- **Two riders**: a second seat socket behind the saddle; the passenger's hands go to the rider's
  waist or the cantle (working); two adults on one horse are past the load limit (`predict load`) —
  slow the horse and drain stamina faster. Dromedary two-rider saddles exist (pakra).
- **Falls**: horse shot, rotational fall at a fence, collision at speed, a hard stop above the
  rider's brace → ragdoll with a chance of a foot caught in the stirrup (drag); in eventing one horse
  falls per 63 cross-country starters and rotational falls (horse somersaults over a solid fence)
  caused at least 25 of 37 rider deaths in 1997–2008.
