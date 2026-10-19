---
name: asset-libraries
description: Free asset libraries (Poly Haven, ambientCG, Kenney, KayKit, game-icons, Google Fonts) and files the user downloaded by hand (Quaternius, Sonniss, itch.io) — search by what a task needs, read the licence from the item, download only what the project's licence allow-list permits, with provenance and the evidence kept, then the normal asset pipeline, the licence registry and CREDITS.md. Load it when a task needs an HDRI, PBR textures, a prop or kit, sprites, UI art, icons, a font or sound effects that a free library may already have.
user-invocable: false
---

# Free asset libraries (`assets_api.py`)

`scripts/assets_api.py`, run from the project root; no key, no account.

| Source | Kinds | Licence |
|---|---|---|
| `polyhaven` | `hdri`, `texture` (glTF material), `model` (glTF) | CC0 for every asset; Kiln sends its own User-Agent as Poly Haven's API terms ask |
| `ambientcg` | `texture` (PBR material zip), `hdri`, `model` | CC0 1.0; their suggested credit line is recorded |
| `kenney` | `model` (3D), `sprite` (2D), `ui`, `audio`, `texture` — whole packs | CC0, checked in the pack's own `License.txt` before anything is kept |
| `kaykit` | `model` (low-poly packs: dungeon, furniture, characters, hex tiles, ...) | CC0 (free tier), checked in `LICENSE.txt`; `--format gltf\|fbx\|obj`, `--only armchair,bed` |
| `gameicons` | `icon` (SVG, id `author/name`) | CC BY 3.0 ("Icons made by {author}. Available on https://game-icons.net"), a few authors CC0 |
| `googlefonts` | `font` (TTF, id = family folder, e.g. `pressstart2p`) | OFL 1.1 / Apache 2.0 / UFL from the family's `METADATA.pb`; the licence file is downloaded with it |

1. Turn the need into 2-4 short queries (noun, material, style words from `design/ART_BIBLE.md`):
   `python ${CLAUDE_SKILL_DIR}/scripts/assets_api.py search all "stone floor" --kind texture`.
   One source being down does not fail `all`: it is listed under `errors`.
2. Show the candidates' previews to the art-director (or the user in asset mode) with the art
   bible references; prefer one source and one author per set so a set reads as one style
   (Kenney, KayKit and game-icons authors are each one style).
3. `fetch <source> <id>` (`--res 1k|2k|4k` for Poly Haven and ambientCG, 2k by default; 4k only
   for hero surfaces): files with their checksums into `art/library/<source>/<id>/`,
   `provenance.json` (kind `library`, author, licence, page) and `evidence/` (the item's record
   and the pack's licence file - the proof of the licence at download). A download is built in
   `<id>.part` and kept only when every check passed.
4. The normal asset pipeline: import, scale and pivot, texel density, `asset_budget.py`, then
   `licenses.py build`: `production/LICENSES.md` lists library assets with their source, and
   `production/CREDITS.md` has the required attribution lines, the fonts and the courtesy
   thanks for the credits screen and the store page.

Files the user downloaded by hand (sources with no API or with a login):
`import <folder> --source quaternius|sonniss|kenney|kaykit --id <name> --url <page>`, or any
other source with `--licence <id>` (as its page states it, e.g. `CC-BY-4.0`) and `--author`. It
copies the folder into `art/library/<source>/<id>/` with the same provenance; a licence file in
the folder is kept as evidence, and without one the provenance says the licence was declared by
the user. Quaternius (QAL) and Sonniss forbid passing the files on as assets: their raw files
stay out of a public repository.

The manifest setting `asset_libraries` (`/kiln:settings`) is the allow-list: `off` (nothing is
downloaded; the guard refuses `fetch` and `import`), `cc0`, `attribution` (default: CC0, CC BY
and the font licences, credits generated), `sharealike` (also CC BY-SA and custom licences such
as Quaternius QAL: a modified BY-SA asset must be released under BY-SA too; music under a video
makes the video BY-SA). A licence outside it is refused before any download. GitHub sources
(KayKit, game-icons, fonts) use GitHub's 60 calls an hour without a token; listings are cached
for a day in `.kiln/cache/assets_api/`. Library assets are made by people: say where they came
from in the handoff, as with any third-party asset.
