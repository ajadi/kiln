# Steam — SteamPipe, store page, reviews, disclosure

Read when preparing a Steam release. Numbers are from partner.steamgames.com as fetched on
2026-10-06; re-check the asset page before producing art (Valve changed sizes in Aug 2024 and no
longer accepts the old ones). Every upload and every money step needs the user's consent.

## Timeline (work backwards from the release date)

| Step | Rule |
|---|---|
| Steam Direct fee | $100 per product, recouped after $1,000 adjusted gross revenue |
| Waiting period | release no earlier than 30 days after paying the fee |
| Coming Soon page | publicly visible ≥ 2 weeks before release |
| Store page review | 3–5 business days; submit ≥ 7 business days before it should go live |
| Build review | 3–5 business days; plan ≥ 7; adult content takes longer |
| After approval | no re-review for later updates |
| Release | the "Release App" button on the app landing page, by the user |

Build review checks: the game launches on every supported OS, every advertised feature is in the
build, in-game purchases use the Steam Wallet. Store review checks: only launch-ready features,
readable title/logo on capsules, gameplay-only screenshots, coherent description without
external links. The release build must be "mostly final" on the default branch.

## Store graphical assets (PNG unless noted)

| Asset | Size (px) | Rules |
|---|---|---|
| Header capsule | 920×430 | logo legible; no text beyond the title, no quotes or awards |
| Small capsule | 462×174 | logo nearly fills it, readable at 120×45 |
| Main capsule | 1232×706 | as header |
| Vertical capsule | 748×896 | as header (sales pages) |
| Page background | 1438×810 | optional, ambient; else made from a screenshot |
| Library capsule | 600×900 | key art + logo, no extra text |
| Library header | 920×430 | branding, logo legible |
| Library hero | 3840×1240 | no text; key content inside the centre 860×380 safe area |
| Library logo | 1280 wide and/or 720 tall | logo only, transparent background |
| Shortcut icon | 256×256 or 512×512 | ICO or PNG; macOS separate ICNS |
| App icon | 184×184 | JPG |
| Bundle header | 707×232 | bundles only |

`store_check.py capsules store/steam --screenshots store/steam/screenshots` checks the sizes,
formats and the library logo's transparency (files named after the asset: `header.png`,
`small.png`, `main.png`, `vertical.png`, `library_capsule.png`, `library_header.png`,
`library_hero.png`, `library_logo.png`) and writes a review pack for the text rules (the small
capsule also at 120×45); a reviewer answers per image and `--answers` gives the verdict.

Screenshots: ≥ 5, ≥ 1920×1080, 16:9, gameplay only (no concept art, pre-rendered cinematics,
awards or marketing text; UI is fine); ≥ 4 marked suitable for all ages. Trailer: up to
1920×1080 at 30 or 60 fps, ≥ 5,000 kbps, H.264 + AAC in .mp4/.mov, stereo; the first trailer
should be mostly gameplay; custom thumbnails are frames of the video. A game cannot release while
a trailer is encoding. Description: short description is a few hundred characters; GIFs and
images in "About This Game" ≤ 5 MB each, ≤ 15 MB total; no links to other sites, no ads for
other products, no fake buttons.

Kiln rule: capsules and key art are art tasks (art-director, artist-2d) made from the game's own
assets; screenshots and trailer come from real captures of the build (`production/captures/`).

## SteamPipe upload

Depots: one per OS (leave "All OSes"/"All languages" unless the depot is OS- or
language-specific), added to the store and dev-comp packages. Scripts live in
`tools/release/steam/` (non-shipping); paths are relative to the script.

```
"AppBuild"
{
  "AppID" "<appid>"
  "Desc" "v0.10.1 <commit>"
  "ContentRoot" "..\\..\\..\\export\\"
  "BuildOutput" "..\\..\\..\\export\\steam-output\\"
  "Preview" "0"
  "SetLive" "beta"
  "Depots"
  {
    "<depotid>" "depot_build_<depotid>.vdf"
  }
}
```

```
"DepotBuild"
{
  "DepotID" "<depotid>"
  "ContentRoot" "..\\..\\..\\export\\windows"
  "FileMapping"
  {
    "LocalPath" "*"
    "DepotPath" "."
    "Recursive" "1"
  }
  "FileExclusion" "*.pdb"
  "FileExclusion" "*_BurstDebugInformation_DoNotShip*"
  "FileExclusion" "*_BackUpThisFolder_ButDontShipItWithYourGame*"
}
```

Backslashes are doubled as in Valve's examples. Confirm the exclusions in a Preview build's file
list — how wildcards match folder names is not documented (UNVERIFIED).

Upload: `steamcmd +login <builder_account> +run_app_build <abs path>\app_build_<appid>.vdf +quit`.

- `"Preview" "1"` writes only logs and a manifest into BuildOutput — use it first and compare the
  file list with `build.py audit`.
- `SetLive` works for beta branches only; the default branch is set live in the Steamworks web UI
  (the user). Beta branches can carry a password for testers.
- Builder account: a separate Steam account with only "Edit App Metadata" and "Publish App
  Changes To Steam" for this app. First `steamcmd +login <user>` on the build machine asks for the
  password and Steam Guard code once; keep `<steamcmd>/config/config.vdf` between runs. Setting a
  released app's build live needs a phone number or the Steam Mobile app on that account.
- SteamPipe diffs files in ~1 MB chunks: keep pack files stable between patches. Unreal pak
  alignment for small patches: `-patchpaddingalign=1048576 -blocksize=1048576` (Steamworks
  upload docs).
- `"Local" "<path>\ContentServer\htdocs"` in the app build tests installs from a local content
  server before the real upload.
- macOS depots: prefer the `.app` bundle format.

## Content survey and AI disclosure

The content survey (required before release) generates the ratings shown for several regional
rating boards, and records mature content (all adult content in the builds, even unreachable)
and AI use:

- **Pre-generated**: any content that ships and players consume, made with AI tools during
  development (art, sound, narrative, localisation). Disclose it.
- **Live-generated**: content made by AI while the game runs; also describe the guardrails that
  stop illegal output. Live-generated adult sexual content is not allowed.
- "Efficiency gains through the use of these tools is not the focus of this section" — AI coding
  assistants and tools built into editors that leave nothing player-facing are out of scope
  (clarified by Valve in January 2026).

Kiln projects: `store_check.py ai-disclosure` drafts `production/release/AI_DISCLOSURE.md` from
every generated asset's `provenance.json` (library assets and non-shipping folders left out),
`production/ai-content.csv` (item,category,tool,ships,notes — AI-made text, voices and
translations that have no provenance file) and shipping code that calls a model at runtime
(live-generated candidates). The user answers the survey; the agent prepares the list and fills
in how people reviewed or changed the output only from what the task files record.

## Steam Deck

Deck Verified: the smallest on-screen character is never below 9 px tall at 1280×800 (Valve
recommends 12 px); text readable at 30 cm; supported resolution (1280×800 preferred); a default
config at 30 fps; full controller access without changing settings, glyphs that match the active
input, controller text entry (Steam's on-screen keyboard API or your own); launchers navigable by
controller. `store_check.py deck --scene <ui scenes>` (Godot) measures every text Control at
1280×800 with the project's stretch settings — hidden menus too; "character height" is
ambiguous, so a font size below 9 px fails and capital letters below 9 px warn.

Steam is not an IARC storefront: the survey is its rating path (see `distribution.md` for IARC).
