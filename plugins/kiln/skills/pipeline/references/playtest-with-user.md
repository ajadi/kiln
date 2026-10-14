# Playtests with the user

The user's play is the only judge of fun. The studio's job is to make each session cheap for
them and to turn what they say into precise work.

## Handing over a build

1. Start the scene in the editor through its MCP (Godot `project_run`, Unity `manage_editor`
   play, Unreal `StartPIE`) — gym, level or the full game.
2. Send one short message (user's language), then end the turn and wait:
   - what this build is testing (the hypothesis, one line);
   - controls (only the ones needed);
   - 3–5 concrete things to try ("walk up the stairs, then sprint across the rubble";
     "shoot only the left gun of the light mech");
   - "When you're done, tell me how it felt — I'll ask a couple of questions."
3. While they play, read the game log (Godot `logs_read` source game, Unity `read_console`,
   Unreal `GetLogEntries`) — errors are data; so is where they stop.

## Feedback questions (one AskUserQuestion call)

- **Fun?** — Yes, want more / Okay / Boring / Annoying. No recommended option here.
- **What's off?** (multiSelect, from the mechanic's feel profile) — e.g. for movement: too slow /
  too floaty / stops too abruptly / camera sickness / feet look wrong / hard to aim; for combat:
  weak hits / can't tell what I hit / enemies unfair / too easy / too hard / too long to kill.
- **Next?** — Tune this / Try an alternative design / Lock it and move on.

For the vertical slice and later, add open questions instead: what was the game about, what were
you trying to do, where were you confused, would you continue?

## Recording

Append to `production/PLAYTESTS.md`:

```markdown
## PT-07 — M03 heavy mech weak points — 2026-10-06
build: <scene or build that was played> @ <commit>
tried: <what the user did>
said (verbatim): "<their words>"
fun: Okay · off: can't tell what I hit, too long to kill
observed: <logs, where they hesitated, numbers sampled during the session>
actions: data → weakpoint_hp 120→80 · design → add hit flash per part · bug → none
```

Quote the user's words exactly — paraphrase loses what they meant.

## Routing findings

| Finding | Goes to |
|---|---|
| design ("boring", wrong rule) | spec in `design/<id>.md` + game-designer alternatives |
| balance / tuning | the mechanic's data resource |
| feel ("floaty", "weak") | translated into numbers (`feel-numbers.md`), then tuning |
| bug | task file / backlog "now" |
| polish wish | `production/POLISH.md` candidate list |

Watch silently: confusion is data. Do not explain the game during a cold test; note what needed
explaining instead.
