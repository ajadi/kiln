# Game-designer layer

At fixed points the game-designer agent invents and the user chooses. Nothing it invents is built
without the user's "yes".

| Phase | What it proposes | How many shown |
|---|---|---|
| 1 Concept | signature hooks — what makes this game this game | up to 4 |
| 5 Mechanics | 2–3 alternative designs of a mechanic that is "okay"/"boring" (one bold); twists | 2–3 |
| 6 Slice | synergies between locked mechanics, ways to deepen the loop | up to 4 |
| 7 Content | each unit's signature moment | one board per batch |
| 8 Polish | moments of delight | up to 4 |

## Generating

`kiln:game-designer` generates 8–12 candidates with techniques such as: start from a verb the
player performs; "like X but also Y"; invert a genre convention; turn a constraint into the hook;
a synergy matrix between existing mechanics; reverse MDA (start from the feeling, derive the
dynamic, then the rule); "a moment the player would retell".

Filter before showing: serves a pillar · a one-line fun hypothesis · testable in a gym · cost
S/M/L · not previously rejected (check the ideas table). Show the best 2–4.

## Showing

One AskUserQuestion multiSelect; each option is a card (5–7 lines in `preview`): the idea in one
sentence, what the player does, why it is fun (hypothesis), which pillar, cost, risk.

## Recording

`design/ideas.md` table: `| id | idea | phase | status | why |` with status `proposed` →
`approved` (gets an M-number in the mechanics table and goes through the normal gym cycle) /
`rejected` / `deferred`. Every idea shown gets a row, so rejected ideas are never pitched again.
