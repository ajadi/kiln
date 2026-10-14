# 2D levels (dimension=2d)

Read with the level-design skill; the method (metrics → beat chart → blockout → encounters → art
pass) is the same, the numbers differ.

## Metrics sheet in tiles

- From the movement numbers (feel-numbers § 2D movement): jump height in tiles, max gap
  ≈ 2·tₕ·vₓ, max climb, run speed in tiles/s. Comfortable jumps use 70–80% of the max; the
  maximum is reserved for deliberate challenge beats.
- Write the sheet in `design/levels/metrics.md` before drawing: tile size, screen in tiles
  (320×180 with 16 px tiles = 20×11.25), jump/gap/climb limits, enemy sizes, door/corridor
  widths for top-down (character width + 1 tile).

## Structure

- Platformers: teach → test → twist per mechanic (kishōtenketsu: introduce, develop, twist,
  conclude); one new idea per screen or room; checkpoints before every hard beat.
- Metroidvania: gate by ability (an ability changes what geometry means — double jump turns a
  high ledge into a path); one-way shortcuts back to hubs; the map shows unexplored exits.
- Top-down: rooms with clear exits, landmarks every screen, Y-sorted props; sight lines for
  ranged enemies drawn on the blockout.

## Building it in the editor

- Separate TileMapLayers: decoration, terrain (collision), hazards, foreground; one tileset with
  terrains per biome. Blockout with a plain tileset first, art tiles later on the same grid.
- Hazards use one visual language with an animated tell; spikes, pits and crushers read at a
  glance on every background.
- Camera limits per room; parallax layers per art-2d §4; foreground never hides the player or a
  hazard.
- Playtest checks: every intended jump made at 80% skill, every gap in the metrics, no blind
  drops onto hazards, no tile seams while the camera moves.
