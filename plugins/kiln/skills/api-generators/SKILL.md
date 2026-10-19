---
name: api-generators
description: Paid AI generators on the user's own account (Meshy first) — the free estimate, the user's yes before any credit is spent, submit, wait, download into art/generated/<asset>/ with provenance, keys only from the environment, spend caps per generation and per day, and what each service's terms mean for the output. Load it when model_generators or audio_generators is api and a task would use a paid service.
user-invocable: false
---

# Paid generators (`gen_api.py`)

`scripts/gen_api.py`, run from the project root. One flow for every service:

1. `python ${CLAUDE_SKILL_DIR}/scripts/gen_api.py services` — which services have a key (never
   the key). No key → `/kiln:settings api` opens the key page for the user; never ask for it in
   the chat. A key pasted into the chat: do not use it; say it is now in the
   conversation log and how to revoke it on the service's site.
2. `estimate <service> <task> --asset <name> --image <file> [--opt k=v ...]` — free calls only.
   It prints `ask_the_user`: the credits, about how many dollars, the balance before and after,
   the licence of the output on the user's plan, retention and training notes.
3. Ask the user exactly that, in their language, and wait. Spending money is never decided for
   the user, in either `user_gates` mode, and never under autopilot: there, `request <job> --why
   "..."` adds the estimate to `production/SPEND_REQUESTS.md` and the run goes on with work that
   needs no money; the autopilot report asks one yes/no per row. A no: mark the row declined.
4. On the user's yes: `submit <job>`. The guard lets it through only after a user message newer
   than the estimate. It refuses a stale estimate (1 h; a spend request 7 days) or a changed one, a service
   outside `gen_services`, and anything over `gen_spend_cap_usd` (default 5) or the day's
   `gen_daily_cap_usd` (default 20). A failed create is never resent: the service may have
   charged it — send the user to the service's dashboard instead.
5. `status <job> --wait` — polls with backoff and downloads on success (results expire:
   Meshy keeps API outputs 3 days). `fetch <job>` downloads again if needed.
6. The files land in `art/generated/<asset>/` with `provenance.json` (service, task id,
   settings, input hashes, cost, licence, `ai_generated`). Then the normal gates: for 3D the
   image-to-model cleanup, `silhouette_iou.py`, `mesh_qa.py`, `asset_budget.py`; the
   art-director compares with the reference. The handoff says the asset is AI-generated
   (Steam disclosure; purely generated output is not copyrightable in the US).

| Service | Tasks | Key variable | Notes |
|---|---|---|---|
| Meshy | `image-to-3d` (`ai_model` meshy-7.1 default, meshy-6-lite / meshy-t2.5 cheaper; `texture=false`, `topology=quad`, `target_polycount`, `pose_mode`); `rigging` (5 credits; `--from <image-to-3d job>` or `--model <textured humanoid .glb facing +Z>`, `height_meters`); `animations` (3 credits per action; `--from <rigging job>`, `actions=92,15` up to 10 into one file with a clip each, `fps=24/25/30/60`) | `MESHY_API_KEY` | API keys need a paid plan; free-plan output is CC BY 4.0 and Meshy's |

Characters: generate with `pose_mode=t-pose` (or a-pose), rig, then animate. `actions meshy
--search walk` lists the animation library with preview GIFs (free); pick ids with the
animator against `design/` (the moves the game needs), not by name alone. `--from` works only
while Meshy still keeps the earlier task (3 days); later, `--model` sends the fetched `.glb`.
Rigging lands in `art/generated/<asset>/rig/` (`rigged.glb`/`.fbx`, `walk.glb`, `run.glb`),
animations in `art/generated/<asset>/anim-<ids>/`, each with its own `provenance.json`. Auto-rig
is for humanoids only; the animator checks the deformation (elbows, knees, shoulders in the
extreme poses) before it goes into the game.

The output licence depends on the user's plan, which most APIs do not report: the user states
it once through `/kiln:settings` (`keys.py plan meshy pro`, stored in `~/.kiln/gen.json`); unknown
means the free-plan licence is recorded and the release check flags it.

A vendor's own MCP server (Meshy, fal, ElevenLabs, ...) follows the same policy: the guard
refuses its tools unless the matching `*_generators` is `api`, and under autopilot allows only
its read calls (balance, status, lists). Prefer `gen_api.py`: only it shows the cost first and
records provenance.

`KILN_GEN_FAKE=http://127.0.0.1:<port>` sends every call to a local fake API with a dummy key
(tests).
