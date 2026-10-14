# Game AI techniques

Values marked (working) are starting points; [U] = not confirmed in a primary source.

## 1. Architectures

**FSM / HFSM.** Each state: `enter(prev)`, `exit()`, `think(dt) -> next state or none`,
`physics(dt)`. The parent state handles transitions shared by its children once (death, stun,
target lost); a history state resumes the last child after an interruption. Log every
transition with tick and reason — qa-ai reads it. DOOM 2016 used HFSMs; programmers owned their
construction.

**Behaviour trees.** Nodes return Success, Failure or Running. Selector = priority list,
sequence = steps, decorators = conditions/limits, services = periodic data updates (0.2–0.5 s).
Re-evaluate on events (blackboard change, observer aborts) instead of ticking the whole tree
every frame. Halo 2 (Isla): prioritised behaviour tree, behaviours declare their own relevance,
"impulses" for reactive behaviours, tags to skip irrelevant subtrees, styles set by designer orders.
Halo's spatial model: designers give AI "playgrounds" (zones, areas, firing positions) and move
the fight from one to the next.

**Utility (IAUS, Mark & Lewis).** Each consideration maps an input through bookends (a clamped
input range) to 0–1, then through a response curve (linear, quadratic, logistic); scores of a
decision multiply, times a weight (weights 1–4 separate priority tiers). Many multiplied
considerations sink the score (0.9⁹ = 0.39): use Mark's compensation factor or the geometric mean.
Against ping-pong: a commitment bonus for the current choice (10–25%, working), runtime and
cooldown considerations. Pick the best, or weighted-random among those within 5–10% of the best
for variety.

**GOAP (Orkin, F.E.A.R.).** The FSM has three states — Goto, Animate, UseSmartObject — and an A*
planner chains actions (preconditions, effects, costs) over a symbolic world state to satisfy the
highest-priority goal; agents re-plan when an action fails or knowledge changes. Sensors keep
working memory current (e.g. nearby valid cover). Squad behaviours were ad hoc, and much of the
apparent tactics (flanking) emerged from individual goals plus barks.

**HTN.** Compound tasks decompose into primitive tasks by designer-written methods — more control
than GOAP, still a planner (Guerrilla: Killzone 2 bots, Decima engine). Choose a planner only when plans
exceed ~3 steps and the world changes mid-plan.

## 2. Perception model

```
awareness += dt * rate * f_dist * f_angle * f_light * f_stance * f_motion   # while seen
awareness -= dt * decay                                                      # while not seen
0.3 → suspicious (turn, investigate), 1.0 → detected (combat)                # (working)
f_dist = clamp(1 - d / range, 0, 1)   f_angle = 1 in focus, 0.3–0.5 in periphery
```

- Check cheap first: distance → angle → budgeted LOS rays → light.
- LOS rays from the eyes to 2–3 body points with a world-only mask (no hurtboxes, no allies'
  capsules unless they should block).
- `lose sight` range larger than `sight` range (Unreal's LoseSightRadius) — hysteresis.
- Hearing: noise events {position, radius, kind, instigator} go to listeners within radius;
  attenuate −50% per blocking wall (ray count) or compare navmesh path length with the radius;
  investigate at the position + error of 1–3 m scaled by distance.
- Memory per target: last seen position/time, velocity, confidence; predict ≤ 1–2 s; then search
  around the last known position (hiding spots, occupancy map — Isla); give up after 10–30 s.
- Sharing: an agent that sees the player shares the position with its squad within a radius
  after 0.5–1 s and a bark ("contact") — honest and readable.

## 3. Accuracy and fairness

- Hit chance = base × f(range) × f(player speed) × f(exposure time) × difficulty (working);
  misses land visibly near the player (0.5–1.5 m) so the threat reads.
- First 1–2 shots at a newly exposed or unaware player miss on purpose if the design says so;
  accuracy ramps over 1–2 s of exposure (working).
- DOOM 2016: demon accuracy drops the faster the player moves; enemies seek open positions near
  cover with a view of the player rather than hiding.
- No fire without LOS; limit off-screen attackers (tokens favour on-screen enemies); show a
  directional damage indicator for every off-screen hit.

## 4. Cover and flank scoring

```
for p in cover markers within R (15–25 m) + navmesh samples every 2 m:
    skip if reserved(p) or not reachable(agent, p)
    skip if threat_eye sees p + up * 0.9          # must hide a crouched body
    d_t = distance(p, threat); skip if d_t outside [min_range, max_range] of the weapon
    score = 1.0 * (1 - path_len(agent, p) / R)
          + 0.8 * range_fit(d_t)                     # 1 at the weapon's preferred range
          + 0.5 * flank(angle(threat_forward, p - threat))   # 0 in front, 1 at >= 90°
          + 0.3 * height_advantage(p)
          - 1.0 * path_exposure(agent -> p)          # share of path samples the threat sees
          + 0.3 * can_peek(p)                        # stand/lean height sees the threat
reserve the best until 2 s after leaving it; re-score at 1–2 Hz or when the threat moves > 3 m
```

Weights are (working). When the player flanks a cover point it stops blocking and the agent
re-chooses — F.E.A.R.'s "flanking" largely emerged this way. Flank routes: an influence grid of
1–2 m cells marking what the player sees (updated ~2 Hz with budgeted rays) multiplies path cost
×3–10 (navigation area costs or a custom A* cost).

## 5. Attack tokens

```
request(type): if pool[type] > 0: pool[type] -= 1; grant
               elif requester on screen and some holder of type is off screen and has not
                    started its wind-up: cancel the holder, transfer the token
               else: deny → reposition / strafe / take cover / taunt
release(type): on attack end, interrupt or death; agent cooldown 0.5–2 s; pool grant spacing
               0.2–0.5 s so attacks do not land in the same frame (working)
```

Melee crowds: a ring of waiting enemies at 3–5 m, 1–2 attackers at once (working). Pool size per
difficulty lives in the difficulty resource.

## 6. Pacing

Spawn out of view with a visible or audible cue (level-design §4). A director that tracks
player stress may thin spawns after damage spikes and build up again (Left 4 Dead's build-up,
peak, relax).

## 7. Common failures and their fixes

| Symptom | Cause | Fix |
|---|---|---|
| agents pile into one cover | no reservation | reserve points; spacing ≥ 2–3 m |
| state flicker | no hysteresis | minimum state time, commitment bonus |
| shots through walls or allies | LOS mask wrong | world-only ray; friendly-fire check before firing |
| stuck at a ledge or door | link not handled, agent radius > gap | handle link traversal; agent sizes per map |
| feet skate while chasing | speed above the clip's stride | speeds from the stride table (animation) |
| everyone shoots at once | no tokens | token pool per attack type |
| enemy "knows" where the player is | perception bypassed | route every target update through a sense event |

## Sources

Orkin, "Three States and a Plan: The A.I. of F.E.A.R." (GDC 2006); Isla, "Handling Complexity
in the Halo 2 AI" (GDC 2005) and "Dude, where's my Warthog?" spatial competence notes; Butcher &
Griesemer, "The Illusion of Intelligence" (GDC 2002); Mark & Lewis, "Building a Better Centaur"
(GDC 2015); Lewis, "Choosing Effective Utility-Based Considerations" (Game AI Pro 3, ch. 13);
Campbell, "Bringing Hell to Life" (GDC 2017) and the DOOM 2016 AI write-up (Game Developer);
Walsh, "Modeling AI Perception and Awareness in Splinter Cell: Blacklist" (GDC 2014); Booth,
"The AI Systems of Left 4 Dead" (2009).
