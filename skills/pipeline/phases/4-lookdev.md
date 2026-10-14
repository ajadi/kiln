# Phase 4 — Look-dev

Goal: one scene in the engine that shows exactly how the game will look, approved by the user,
before mass production of assets.

## Contents of the look-dev scene (path per engine: see the gate in `PIPELINE.md`)

- A representative space (a street corner and a piece of interior, or the game's equivalent)
  blocked out at real scale.
- 2–3 hero assets at final quality (the player character or weapon, one enemy, one key prop),
  made by the modeler/2D artist through the art bible.
- Final lighting and post-processing per the art bible (lighting-artist), in the game's renderer.
- A HUD mock-up at native resolution.
- One effect (an impact or explosion) so VFX are judged in context.
- One SFX family (sound designer) and a 30–60 s music sketch (composer → producer) playing in
  the scene, so sound is judged with the picture.

## Steps

1. Build the scene in the editor (scene-first), assets through the normal art pipeline.
2. Capture from the gameplay camera at the bookmarked viewpoints (`contact_sheet.py`).
3. Self-checks before showing anyone:
   - montage of our frames next to the reference frames (`contact_sheet.py sheet`);
   - grayscale value check: player, enemy and background separate (`contact_sheet.py sheet
     --gray`, `values`); every enemy type identifiable at 128 px in grayscale;
   - the lighting skill's acceptance numbers (median lightness, crushed/clipped pixels, enemy and
     weak-point contrast);
   - qa-readability on the scene.
4. Art-director review against the art bible (APPROVED / CHANGES_REQUIRED). For the key frame,
   run the gauntlet against a bar the user respects if the gap is hard to name.
5. Show the user: a board with the look-dev frames, the references and the art bible's signature
   techniques. Question: "Will the game look like this?" — Yes (Recommended) / Close, change one
   thing / No, back to style.
6. If the style does not survive real lighting and assets, reopen Phase 2 — that is what look-dev
   is for.

Exit: the scene exists, value check and montage done, art-director APPROVED, the user approved.
