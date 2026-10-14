---
name: grilling
description: Interview the user about a brief, feature, asset or change before work starts — rounds of numbered questions, each with a recommended answer, until every open choice that changes the result is settled. Use when a new game, demo, feature, asset or scope change comes in, when a brief leaves player-facing choices open, or when the user says "grill me", "ask me", "clarify first" (in any language).
user-invocable: false
---

# Grilling

Work turns out wrong most often because a choice the user cares about was never asked: in a
live run the plan for "a simple walk demo" missed jump, crouch, a helmet, strikes and a gear
prop, each added mid-build. Grilling closes those branches before the work starts.

## The design tree

Map the subject as a tree of decisions: each choice opens the choices that depend on it. Walk
only the branches that change what the player sees, does or feels, or what the user will judge.
For games, look at these branches (skip what the brief or the files already settle):

- **Player and controls** — the move set (offer the default third-person set: idle, walk, run,
  jump + land, crouch + crouch-walk, turn in place; combat and gear only when hinted), camera,
  input devices, key bindings that need three keys at once.
- **Look** — references, what it must resemble, what it must not, the one thing the user will
  check first.
- **Scope** — demo, prototype or game (`kind`), in and out, platforms, frame-rate target.
- **Content** — characters, props, levels; hand-made, generated or found; licences.
- **Feel numbers** — speeds, jump height, timings the user already has in mind.
- **Acceptance** — how the user will decide it is done ("I play the .exe for 5 minutes").

Check `memory/out-of-scope/` first: a rejected idea is not asked again.

## Rounds

The **frontier** is every open decision whose prerequisites are settled. Ask the whole frontier
in one message, then wait:

    ❓ **Q1 — <short title>**: <the choice, with options if any>
    ➡️ <recommended answer>

    ---

Recommend what serves the request, never the option that is easier to build — effort belongs in
the time estimate, not in the recommendation (the user: complexity is not an argument). Word each
question so that "yes" accepts the recommendation; the user may answer by number
("1 yes, 2 the second, 3 skip"). A question that depends on another open one waits for a later
round. Once answered, work out which choices are open now and ask about those. In Claude Code,
AskUserQuestion fits a round of up to four single choices with clear options; anything else is a
text round.

**Facts are your job, decisions are the user's.** What the files, the engine, a measurement or a
search can answer, find out yourself (in parallel, with a subagent for a long lookup) — only the
questions downstream of a running lookup wait.

## Done

The frontier is empty → restate the decisions in a short list and get the user's "yes" before
acting on them. With `user_gates=proxy` (the default) and a user who is away or says "decide
yourself", take the recommended answers, record each with `pipeline.py decide ... --by proxy`, and
list them in the report for redo; with `user_gates=ask`, wait.

Write the answers where they belong — `GAME.md`, the brief, the task's acceptance,
`memory/decisions.md` — and a rejection with a reason as a file in `memory/out-of-scope/`.
