# Kiln in plain words

Kiln turns Claude Code into a small game studio. You talk to one producer (your normal Claude
Code session). It plans the work, hands each piece to a specialist agent (a "role": modeler,
animator, sound designer, ...), has other agents check the result with real measurements, and
reports back to you. It can also just make one asset - a 3D model, a sprite sheet, a music track
or a video clip - without any game.

This guide covers: how to install it, the commands you type, the knowledge skills the agents use
on their own, and how they all call each other.

## 1. Install

### Once per computer

```bash
claude plugin marketplace add ajadi/kiln
claude plugin install kiln-start@kiln --scope user
```

The first line tells Claude Code where Kiln lives (the public GitHub repository). The second
installs a tiny helper that gives you one command, `/kiln-start:here`, in every folder.

### In each project folder

1. Open Claude Code in the folder and run **`/kiln-start:here`**. It connects Kiln to this
   folder only. The first time on a computer it also asks where Kiln may install programs
   (the tools folder, e.g. `~/kiln-tools`); it never asks again.
2. Restart Claude Code in that folder (commands load when a session starts).
3. Run **`/kiln:setup`**. One round of questions, each with a recommended answer you can accept
   with "yes": a game, a prototype or just assets; engine (Godot, Unity, Unreal) or none; 2D or
   3D; whether it may decide small things for you; AI generators allowed or not. Then it looks
   for every program the project needs, asks once to install what is missing (Blender, Godot,
   uv, git-lfs, Ollama, the MCP servers that let agents drive the editors), and ends with a
   table of everything it installed.
4. If setup registered new MCP servers, restart Claude Code and run `/kiln:setup` again; then
   **`/kiln:doctor`** checks that Blender and the engine really answer.
5. Start working: **`/kiln:pipeline`** (or `/kiln:concept` with your idea) for a game; one of
   `/kiln:model`, `/kiln:sprites`, `/kiln:track`, `/kiln:cinematic` for a single asset.

Nothing is installed, published or paid for without your yes.

### Install scopes

`--scope` says where Claude Code records that a plugin is installed, and so who gets it.

| Scope | Who gets the plugin | Where it is written | Use it for |
|---|---|---|---|
| `user` (the default) | you, in every folder you open | your user settings (`~/.claude/settings.json`) | `kiln-start` - one command everywhere |
| `project` | everyone who opens this repository, you included | the project's `.claude/settings.json` (committed) | `kiln` itself (what `/kiln-start:here` does), so teammates get the same rules |
| `local` | only you, only in this folder | the project's `.claude/settings.local.json` (not committed) | trying Kiln in a shared repository without changing it for others |

Kiln is never installed at `user` scope: its rules and safety hooks would then run in every
project, also ones that are not games. Organisations can also push plugins through managed
settings, which users cannot change.

OpenAI Codex works the same way with its own switches: the plugin stays off in your user
`~/.codex/config.toml` and is turned on per project in `.codex/config.toml`.

### Updating

- Get the new Kiln: `claude plugin marketplace update kiln`.
- In one project: **`/kiln:update`** refreshes the project's copy, migrates its task files and
  settings, and lists what changed since that project's version.
- In every project at once: **`/kiln:update all`** from any Kiln project. Kiln knows every
  project on this computer that uses it (each session records its folder in
  `~/.kiln/projects.json`; `/kiln:update all --scan <folder>` also finds old projects that were
  not opened since). It shows one table of projects and versions, asks once, and updates all of
  them. A session also tells you when other projects are behind.
- Kiln notices new versions by itself: once a day, in the background, it looks at the latest
  release on GitHub, and the next session tells you "Kiln X is out" with the two commands above.
  It never updates without your yes, stays quiet offline, and `"update_check": "off"` in
  `~/.kiln/machine.json` turns it off.

## 2. Commands (18)

You type these. Everything else happens through them or through plain requests ("make the door
open slower").

**Setting up and looking around**

| Command | What it does |
|---|---|
| `/kiln:setup` | first setup of a project: the questions, the programs, the editor connections |
| `/kiln:settings` | show or change a setting, e.g. `/kiln:settings user_gates=ask` |
| `/kiln:doctor` | check that Blender, the engine editor and Kiln's hooks really work |
| `/kiln:update` | bring this project (or `all` projects) up to the installed Kiln |
| `/kiln:status` | where the project stands: phase, tasks, who still has to check what |

**Making a game**

| Command | What it does |
|---|---|
| `/kiln:pipeline` | the whole production, phase by phase: concept, style, tech plan, look-dev, mechanics, vertical slice, content, polish, release |
| `/kiln:concept` | turns your idea or briefs into `GAME.md` and design notes, asking what it must |
| `/kiln:plan` | breaks the next part of the work into task files |
| `/kiln:run` | does the next task: hands it to the right role, gets it checked, closes it |
| `/kiln:autopilot` | keeps running tasks one after another without waiting for you |
| `/kiln:stop` | lets the autopilot finish the current task and stop cleanly |
| `/kiln:gym` | a small test scene for one mechanic, to tune and measure it |

**Single assets, no game needed** (inside a game project they deliver into its folders)

| Command | What it does |
|---|---|
| `/kiln:model <images>` | a 3D model from 1-3 photos, concept art or sketches: modelled in Blender, generated by an AI model you allowed, or both; checked against every view |
| `/kiln:sprites <image>` | a sprite sheet with animations and directions, or a 2D map cut into a tileset and a Tiled map |
| `/kiln:track <description>` | a song, an instrumental or a game loop: composed or generated, loudness and tempo measured |
| `/kiln:cinematic <description>` | a short video clip (rendered in Blender) or a cutscene in the game, with a shot list and a timing draft first |

**Feedback**

| Command | What it does |
|---|---|
| `/kiln:report <what went wrong>` | writes your complaint about Kiln into `kiln-report.md` (and, if you want, a GitHub issue) |
| `/kiln:retro` | reviews the session and fixes Kiln and the project where they failed |

## 3. Knowledge skills (49)

These have no command. They are reference books: an agent reads the one it needs. Each role
starts with its own few (listed below), and loads others from the table in `protocol` when a
task touches them.

**Base, used by many**

| Skill | What it knows | Used by |
|---|---|---|
| `protocol` | how agents work together: task files, handoffs, who writes where, which skill to load | every role |
| `grilling` | asking you the questions that matter before building | concept, plan, run, setup |
| `implications` | what a new item or ability touches elsewhere | plan, run |
| `tech-design` | choosing how to build a mechanic | tech-designer, plan |
| `acceptance` | measuring a result with numbers instead of opinions | every QA role, physics-expert, autoplayer |
| `playtest` | playing the build and reporting what a player feels | playtester, verifier, most builders |

**Engines and tools**

| Skill | What it knows | Used by |
|---|---|---|
| `engine-godot`, `engine-unity`, `engine-unreal` | the rules of that engine and its MCP | added to every engine-facing role at its start |
| `tools` | finding, installing and checking programs | setup, settings, doctor |
| `gpu-server` | renting a GPU for heavy jobs with a spending cap | model, track (when generators run remotely) |
| `release` | builds, CI, store pages | release-engineer |

**3D, 2D and look**

| Skill | Used by |
|---|---|
| `blender-modeling` (modelling in Blender with checks) | modeler, art-director |
| `image-to-model` (a model from photos, generators) | modeler, `/kiln:model`, `/kiln:sprites` |
| `asset-pipeline` (export, import, budgets) | modeler, animator |
| `art-2d` (pixel art, sprites, tiles) | artist-2d, `/kiln:sprites` |
| `lighting` | lighting-artist, qa-readability |
| `shaders` | fx-artist, lighting-artist (on demand) |
| `optimization` | qa-performance, any role over budget (on demand) |
| `destruction-vfx` (breaking things, effects) | fx-artist, qa-damage |

**Bodies and movement**

| Skill | Used by |
|---|---|
| `animation` | animator, qa-locomotion |
| `human-biomechanics` | anatomy-expert |
| `creature-locomotion` | creature-expert |
| `hands`, `riding`, `traversal` (grips, mounts, climbing and vaulting) | animator, gameplay-dev (on demand) |

**Physics and the world**

| Skill | Used by |
|---|---|
| `rigid-body-physics` | physics-expert, qa-physics |
| `soft-bodies`, `fluids-granular`, `fields-forces`, `elements-materials` (cloth, water, sand, wind, fire, materials) | physics-expert, fx-artist, gameplay-dev (on demand) |
| `doors`, `vehicles`, `flight` | gameplay-dev, level-designer, animator (on demand) |
| `sky`, `weather` | lighting-artist, fx-artist (on demand) |

**Gameplay**

| Skill | Used by |
|---|---|
| `controls-camera` | gameplay-dev, qa-feel (on demand) |
| `game-ai` (enemies and NPCs) | ai-programmer, qa-ai |
| `level-design` | level-designer |
| `procgen` (generated levels and maps) | level-designer, `/kiln:sprites` |
| `balance`, `save-system` | game-designer, gameplay-dev (on demand) |
| `ui`, `accessibility`, `localization` | ui-designer, writer, qa-readability |

**Story and sound**

| Skill | Used by |
|---|---|
| `narrative` (story, quests, dialogue, cutscene scripts) | writer |
| `llm-npc` (NPCs that talk through a language model, opt-in) | writer, ai-programmer |
| `music` | composer, music-producer, `/kiln:track` |
| `procedural-audio` (sound effects, loudness checks) | sound-designer, qa-audio |

`cinematic` is both a command (`/kiln:cinematic`) and the knowledge the animator loads for any
cutscene task.

## 4. Who calls whom, and when

### The command chain

```
/kiln-start:here -> /kiln:setup -> /kiln:doctor -> /kiln:pipeline
                    (tools, grilling)                    |
        /kiln:concept -> /kiln:plan -> /kiln:run  <- repeated by /kiln:autopilot
         (grilling)     (grilling,       |              (ended by /kiln:stop,
                         implications,   v               reviewed by /kiln:retro)
                         tech-design)   roles -> checkers -> verifier closes the task
```

`/kiln:update` runs the migration and then `/kiln:doctor`. `/kiln:status` only reads.
`/kiln:report` and the agents themselves write problems with Kiln into `kiln-report.md`.

### Inside one task

1. The producer (your session) writes a task file and hands it to a role.
2. The role starts with its own skills; the hook adds the engine's rules; it loads other skills
   from `protocol`'s table when the task needs them.
3. The task's `touches:` line decides who else must look at it:

   | touches | extra roles |
   |---|---|
   | humanoid | anatomy-expert |
   | creature, mech | creature-expert |
   | physics | physics-expert, qa-physics |
   | movement | qa-feel |
   | npc | qa-ai |
   | damage | qa-damage |
   | audio | qa-audio |

4. Checkers measure the result (`acceptance`, `playtest`); the art-director judges the look; the
   verifier closes the task. The builder never grades its own work; whether it is fun is your
   call.
5. Kiln's hooks watch everything: the guard checks every action (editors only through MCP, no
   secrets in commits, one agent per editor), and the stop hook will not let a task close while
   a required check is missing.

### The asset commands

| Command | Skills | Built by | Checked by |
|---|---|---|---|
| `/kiln:model` | `image-to-model`, `blender-modeling`, `asset-pipeline`; generators through `tools` or `gpu-server` | modeler | art-director, verifier |
| `/kiln:sprites` | `art-2d`, `image-to-model`, `animation`, `procgen` | artist-2d, or modeler + animator for pre-rendered sprites | art-director, verifier |
| `/kiln:track` | `music`, `procedural-audio` | composer + music-producer | qa-audio, verifier |
| `/kiln:cinematic` | `cinematic`, plus `lighting`, `narrative` (script from the writer), `music` | animator | art-director, qa-readability, qa-performance, verifier |

## 5. Where things are

| File or folder | What is in it |
|---|---|
| `manifest.md` | the project's Kiln settings (`/kiln:settings` changes them) |
| `GAME.md`, `design/`, `backlog.md`, `tasks/` | what the game is, the plan, one file per task |
| `production/STATUS.html` | a page showing where things stand |
| `out/<asset>/` | finished assets in asset mode, each with a README of its numbers and licences |
| `kiln-report.md` | problems with Kiln, written by agents and by `/kiln:report` |
| `~/.kiln/machine.json` | this computer's tools folder and the programs Kiln found or installed |
| `~/.kiln/projects.json` | every Kiln project on this computer, for `/kiln:update all` |
| `~/.kiln/update-check.json` | the latest Kiln release seen by the daily check |
