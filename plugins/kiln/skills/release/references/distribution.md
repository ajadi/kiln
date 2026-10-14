# Distribution — itch.io, signing, ratings, store copy, credits

Read when publishing outside Steam, signing builds, rating the game, writing store text or
building the credits. Every account, payment, upload and questionnaire answer is the user's.

## itch.io (butler)

```
butler login                                   # once per machine; CI uses BUTLER_API_KEY
butler push export/windows <user>/<game>:windows --userversion 0.9.0 --if-changed
butler push export/linux   <user>/<game>:linux   --userversion-file export/VERSION
butler push export/windows <user>/<game>:windows-beta --hidden --dry-run
```

- `push <dir|zip> user/game:channel`; one channel per platform/variant. Channel names tag the
  upload: `win`/`windows`, `linux`, `mac`/`osx`, `android`; combine (`win-linux-mac-stable`),
  kebab-case.
- `--userversion` / `--userversion-file` (one UTF-8 line, no BOM); itch orders builds by upload
  order, not by version text. `--if-changed` skips identical content; `--dry-run` lists files;
  `--ignore '*.pdb'` (repeatable); `--hidden` keeps a new channel off the page;
  `--no-auto-unzip` uploads a .zip as-is.
- butler sends only patches after the first push. CI: secret `BUTLER_API_KEY` (from the API keys
  page, source `wharf`); a leaked key is revoked there. `-i <creds file>` selects another account.
- Web builds: upload a zip with `index.html` at its root, mark it playable in the browser on the
  game page (Godot web exports need the page's SharedArrayBuffer option when threads are on —
  UNVERIFIED for 4.7 defaults).

## Windows code signing

Steam does not require Authenticode for games it launches; direct downloads (itch.io, website)
without a signature get a strong SmartScreen block.

| Option | Cost | Availability | SmartScreen |
|---|---|---|---|
| Azure Artifact Signing (formerly Trusted Signing) | ~$9.99/month | organisations: USA, Canada, EU, UK; individuals: USA, Canada | reputation builds over time |
| OV certificate (DigiCert, Sectigo, ...) | $150–300/year | worldwide; key on HSM/USB token since June 2023 | same as above |
| EV certificate | $400+/year | worldwide | same as OV since 2024 — no instant bypass |
| Microsoft Store MSIX | free (Store re-signs) | worldwide | no warnings |

```
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f cert.pfx /p <pwd> game.exe
signtool sign /fd SHA256 /tr <tsa> /td SHA256 /sha1 <thumbprint> game.exe     # cert in the store/token
signtool verify /pa /v game.exe
```

`/fd` is mandatory in current SignTool; always timestamp (`/tr` + `/td`) so the signature
outlives the certificate. Sign every shipped `.exe` and `.dll` you built, with one consistent
identity so reputation accumulates across releases. Godot can sign during export
(`codesign/*` preset options); `osslsigncode` signs from Linux.

## macOS signing and notarization

Downloaded apps that are not signed and notarized are blocked by Gatekeeper. Needs an Apple
Developer account (Developer ID Application certificate).

```
codesign --force --options runtime --timestamp --sign "Developer ID Application: <Team>" Game.app
ditto -c -k --keepParent Game.app Game.zip
xcrun notarytool store-credentials <profile> --apple-id <id> --team-id <team>
xcrun notarytool submit Game.zip --keychain-profile <profile> --wait
xcrun notarytool log <submission-id> --keychain-profile <profile>    # when rejected
xcrun stapler staple Game.app
```

Godot exports can sign and notarize from any OS with `rcodesign` (Windows/Linux exports should
be `.zip`; an `.app` exported on Windows loses the executable bit). Without a Developer ID,
Godot's "Built-in (ad-hoc only)" signing lets Apple Silicon run the app after the user approves
it. Steam macOS depots prefer the `.app` bundle.

## Age ratings

- **IARC** (free questionnaire, one certificate ID reused across participating stores, ratings
  per region from the boards' rules): Epic Games, Google Play, Microsoft, Nintendo, Sony
  PlayStation, Meta Horizon, Amazon Luna, ONE Store, Pico, Facebook Gaming, YouTube Playables
  (globalratings.com/storefronts, Oct 2026). The questionnaire runs inside each store's
  submission flow; answer from the real content (violence, blood, language, gambling, user
  interaction, purchases, location sharing).
- **Steam**: not an IARC storefront; the content survey produces the ratings it shows.
- **itch.io**: no rating; mark adult content in the page settings.
- Consoles: through the platform holder's process (IARC on Nintendo eShop, PlayStation Store and
  Microsoft Store; physical releases need ESRB/PEGI directly — UNVERIFIED scope).
- Changing content after rating (blood, gambling-like mechanics, online chat) means updating the
  questionnaire before shipping that update.

## Store copy (Kiln rules)

Source: `GAME.md` pitch, pillars and the mechanics actually in the build.

1. First sentence: who the player is and what they do, in verbs ("Pilot a salvaged mech and tear
   enemy machines apart piece by piece").
2. Second: the hook that differs from neighbours in the genre.
3. Features: 4–6 bullets, each a player verb plus a concrete number or detail; only features in
   the build (Steam's build review checks).
4. No superlatives without proof, no review quotes or awards on capsules, no links to other
   stores or sites, no prices or dates in images.
5. Tags/genres: from the mechanics table, most specific first.
6. Localised pages only when the build has that language.
7. The user approves the final text; record it in `production/store/<platform>.md`.

## Credits and licences

The integrator's registry `production/LICENSES.md` lists every third-party or generated item that
ships: fonts, asset packs, music, sounds, shaders, plugins, AI-generated assets (with their
provenance files), tools whose output carries terms. Rules:

- No registry row (name, source, licence, attribution text, where used) → the item does not ship.
  `audit` + a grep of the export file list against the registry before every release candidate.
- Credits screen and a `CREDITS.txt`/`LICENSES.txt` next to the executable are generated from the
  registry, not hand-written; CC-BY items show the attribution text exactly as the licence asks.
- Engine notices:
  - **Godot** (MIT): include the Godot licence text ("This game uses Godot Engine, available
    under the following license: ...") in the credits, a licences screen, or a file shipped with
    the game, plus third-party notices (FreeType, ENet, mbedTLS, ...) — `Engine.get_license_text()`,
    `Engine.get_license_info()`, `Engine.get_copyright_info()` or Godot's `COPYRIGHT.txt`.
  - **Unreal**: the EULA requires in the credits "[Product] uses the Unreal® Engine. Unreal® is a
    trademark or registered trademark of Epic Games, Inc. in the United States of America and
    elsewhere." and "Unreal® Engine, Copyright 1998 – <year>, Epic Games, Inc. All rights
    reserved." Royalty applies above $1,000,000 lifetime gross per product (rate and Epic Games
    Store exclusions: read the current EULA — UNVERIFIED here).
  - **Unity 6**: the "Made with Unity" splash is optional, Personal included; Personal is for
    under $200K revenue and funding in the last 12 months.
