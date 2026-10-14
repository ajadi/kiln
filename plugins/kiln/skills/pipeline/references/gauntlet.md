# Gauntlet — blind A/B against a bar

For the parts that decide first impressions — core feel, the look-dev key frame, hero assets,
the first 60 seconds and menu, store capsule and trailer — or whenever the user is unimpressed
and the gap is hard to name.

## Setup

`production/gauntlet/<target>/BAR.md`:
- the bar: a reference image or capture from a game the user respects (frozen — it never changes
  during the run);
- 3–4 lenses, one per round (e.g. silhouette readability, lighting mood, material richness,
  composition; or for feel: response, impact, clarity);
- the capture recipe for ours (scene, camera, input sequence) so every round is comparable.

## A round

1. Capture ours into `rounds/NN/ours.png` with the recipe.
2. `python ab.py prepare rounds/NN --ours rounds/NN/ours.png --bar <bar image>` → `A.png`,
   `B.png` in random order, same size; the key is hidden in `.key.json`. Do not open it.
3. Judge through **one lens only**, reading only the lens, the art bible and the two images —
   not the code, not the task. By default the bar wins; ours must clearly earn a win.
4. Write `rounds/NN/verdict.md`: `WINNER: A|B|TIE` and exactly one `GAP: <sentence>`.
5. `python ab.py reveal rounds/NN --ledger LEDGER.md`.
6. One fix aimed at the gap (owning role), commit, next round.

The judge should be a different agent from the one making the fixes (the art-director or an
acceptance role), so the verdict is not self-graded.

## Stop

After 3–6 rounds; when ours wins under every lens; or after two rounds with no visible
difference. Then show the user the before/after/bar sheet. A longer unattended refinement run
only with the user's consent.
