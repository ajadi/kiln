# Barks: taxonomy, rule database, cooldowns, checks

Barks are short lines fired by game events. They carry gameplay information first and character
second, and they fail by repetition, overlap and staleness — all measurable from a log.

## Taxonomy

| Type | Purpose | Examples | Priority (1 = highest) |
|---|---|---|---|
| Information | threats and AI state the player must know | "Contact left!", "Reloading!", "Grenade!" | 1 |
| Status | player / companion state | low health, low ammo, objective reminder | 2 |
| Reaction | acknowledge a player action | kill confirmed, item picked up, friendly fire | 3 |
| Hint | nudge a stuck player | after 60–90 s without progress (working) | 3 |
| Commentary | companion remarks on places and story | "That's the hospital roof." | 4 |
| Ambient | world life | chatter, crowds, idle mutters | 5 |
| Efforts | non-verbal | grunts, pain, death | sound-designer's files, same system |

## Rule database (Valve / Left 4 Dead model)

1. Gameplay code raises a **concept** (`ENEMY_SPOTTED`) with a speaker and a **query** of facts
   (speaker, map, health, enemy class, distance, recent events, world flags).
2. Each **rule** = concept + criteria on facts → a response pool. The rule with the most matching
   criteria wins; general rules are the fallbacks ("most specific wins").
3. A line is drawn from the pool without repeats until it is exhausted (shuffle bag), optional
   weights.
4. Responses may **write facts** (memory): `said_roof=1` lets a later rule react, and lets two
   characters hold a short exchange (A's line sets a fact, B's rule answers).
5. Writers add special cases as data; programmers do not change code for new lines.

Kiln bark table (CSV, lintable with `dialogue_lint.py`, which reads `id`, `text`, `max_chars`):

```csv
id,concept,speaker,criteria,text,weight,cooldown_s,once,priority,sets,max_chars
MERC_SPOT_0010,ENEMY_SPOTTED,MERC,enemy_class==heavy,Heavy coming through!,1,,0,1,,40
MERC_SPOT_0020,ENEMY_SPOTTED,MERC,,Contact!,1,,0,1,,40
MERC_ROOF_0010,ENTER_AREA,MERC,area==hospital_roof;said_roof==0,That's the hospital roof.,1,,1,4,said_roof=1,60
```

`criteria`: `;`-separated `fact op value` (`==`, `!=`, `<`, `>`, `<=`, `>=`); empty = fallback.
Fact names live in `memory/registries.md` with the flags.

## Timing (working values; Valve's Response System `defaultdelay` = 2.8–3.2 s post-speech delay)

| Level | Default |
|---|---|
| Global, within earshot | one voice at a time unless a scripted exchange; 2–4 s gap after any bark |
| Per speaker | 4–8 s |
| Per concept | 10–30 s; information concepts 5–10 s |
| Per line | not repeated within 120 s, or until its pool is exhausted |
| Once-only | `once=1` (Valve `speakonce`) |
| Stale | information barks dropped if not started within 1.0 s of the event |
| Interrupt | only by higher priority; a dropped low-priority bark does not consume its cooldown |

Pool size by how often the concept fires: ≥ 3 variants at ≥ 1/min, ≥ 6 at ≥ 3/min, ≥ 10 for
ambient that can loop (working). Speakers beyond the audible radius neither play nor consume
cooldowns. Bark subtitles are their own player toggle (XAG 104), with the speaker name or a
direction arrow when the speaker is off screen.

## Writing

- ≤ 6 words, ≤ 2 s; the information comes first ("Grenade!", "Left side — heavy!").
- Every bark responds to its trigger, gives information and sounds like the character.
- Draft a few dozen per concept, keep the best; variants change words, never the information.
- Avoid facts that can become wrong (counts, directions) unless the query supplies them.
- VO: record per character in batches, with intensity levels (normal / shouted) in the script.

## Bark log and checks

The bark system logs every decision, one line each:

```
BARK t=12.40 speaker=MERC_02 concept=ENEMY_SPOTTED line=MERC_SPOT_0020 result=played dur=1.4
```

`result` ∈ played | cooldown | stale | interrupted | no_rule. Measure over ≥ 10 minutes of combat
from the running game's log (engine MCP log reader):

| Check | Target |
|---|---|
| Same line repeated within 120 s | 0 |
| Overlapping played barks in one earshot (t … t+dur) | 0 unless scripted |
| Information barks played / eligible events (not in cooldown) | ≥ 90% |
| `no_rule` for information concepts | 0 |
| Played barks per minute in combat | ≤ 12 (working) |
| Stale drops | ≤ 10% of information events |

Sources: Elan Ruskin, "AI-driven Dynamic Dialog through Fuzzy Pattern Matching", GDC 2012
(gdcvault.com/play/1015528); Valve Developer Community, Response System (speakonce, norepeat,
respeakdelay, defaultdelay); Xbox Accessibility Guideline 104; "How to Write Video Game Barks"
(howtowriteagame.substack.com).
