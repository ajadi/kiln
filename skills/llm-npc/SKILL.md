---
name: llm-npc
description: "Optional LLM-driven NPC conversation, off unless the design asks and the user enables the manifest policy — when it helps or hurts, architectures (dev-time drafting, local Ollama, player endpoint, hosted API), the installed open-llm-npc server (API, gaps, licence gate), character cards and memory, guardrails, latency budget with fallback lines, prompt regression sets with npc_eval.py, cost, Steam AI disclosure and ratings, scene-first integration for Godot 4.6/4.7, Unity 6, Unreal 5.8. Use when a design proposes NPCs that talk through a language model."
user-invocable: false
---

# LLM-driven NPCs

**Gate.** Off by default. Work on it only when `GAME.md` asks for it and `manifest.md` has
`llm_npc=local` or `llm_npc=api` — a policy only the user sets. Until then the answer is authored
dialogue (`kiln:narrative`). Values marked (working) are starting points.

## When it helps, when it hurts

Helps: conversation is the mechanic (interrogate, persuade, talk-to-solve); many low-stakes NPCs
where variety matters; typed player input is part of the fantasy; exploring a character's voice
during development.

Hurts: authored beats and quest-critical information (must be deterministic, testable,
localized); voiced games (synthetic voice = latency, voice licence, actor consent); many languages
(quality differs per language, each needs its own test set); young or low rating targets;
competitive fairness; offline or low-end targets (a local model needs GBs of RAM/VRAM).

Rules: LLM text is flavour around authored state — quests, rewards, flags and anything that
changes the game come from game rules, never from parsing model text. Every LLM NPC has authored
fallback lines and the game is fully playable with the server off.

## Architectures

| Option | Runtime cost | Main risks | Fits |
|---|---|---|---|
| A. Dev-time drafting: the writer generates variants, curates, ships authored lines with IDs | none | store disclosure (pre-generated) | default recommendation |
| B. Local sidecar (Ollama + NPC server installed with the game) | player disk/RAM/VRAM, cold load | install size, support, model licence duties | offline PC single-player |
| C. Player-provided endpoint (their Ollama/LM Studio) | none | opt-in only, unsupported setups | enthusiast/mod feature |
| D. Hosted API behind your backend | per-token bills, operations | keys, auth, rate limits, privacy, moderation | online games |

Never ship an API key in the client, and never expose open-llm-npc to the internet: the client
sends the prompts, so anyone reaching it gets a free general-purpose LLM proxy.

## Ollama and the open-llm-npc server

With `llm_npc=local` the tools skill installs Ollama after the user's yes (`tools_check.py install
ollama --yes`, into tools_root, checksum verified) and pulls the model chosen for the NPCs
(`ollama pull <model>`; size and licence go in the same question). Kiln never pipes an install
script into a shell.

open-llm-npc (when the project uses it; record where it lives in machine.json): Flask + waitress,
stateless. `POST /chat`
`{message, configuration{state, prompts, quests, rewards}, context?, state_change?}` →
`{text, context{state, history}, quest, reward}`; `GET /health` → `{"ok": true}`. `.env`:
`LLM_BASE_URL` (any OpenAI-compatible `/v1`), `LLM_MODEL`, `LLM_API_KEY`, `PORT=8100`,
`MAX_CONTEXT_MESSAGES=20`. Without a running Ollama and a pulled model `/chat` answers 502. Behaviour, gaps (binds 0.0.0.0 without auth, no streaming, no
length cap, unescaped `[PLAYER]` tags) and the Ollama Modelfile settings that close them:
`${extensionPath}${/}skills${/}llm-npc/references/open-llm-npc.md`. Do not start, patch or reconfigure the server
without the user; keep it off ports 8000/8080/9500/9876 (editor MCP ports the Kiln guard blocks).

**Licence gate.** The README says MIT, but the repository has no LICENSE file and GitHub reports
no licence, so nothing grants the right to copy, modify or redistribute it — including its engine
client files. Before shipping, bundling or vendoring: an added LICENSE from the author or written
permission. Raise it as an open question for the user; local prototyping is the user's call.

## Character card and memory

Card `design/narrative/npc/<id>.md` (mirrored into a card resource through the engine MCP): role
in the story, voice (3 adjectives, quirks, 3–5 authored sample lines), knows / does not know,
goal, allowed topics and in-character refusal, forbidden content, reply length (≤ 2 sentences,
≤ 160 chars), language, state flags → prompt per flag in priority order, quests/rewards per flag,
≥ 5 fallback line IDs. Each state prompt ≤ ~300 tokens (working; it is resent every turn).
Anything the NPC must never say stays out of the prompt — prompts leak; reveal a secret by
switching to the state prompt when its flag is set. Memory: short-term = server history (20
messages); long-term = facts game code sends as `state_change`; saves store the context
(it contains player-typed text).

## Guardrails (layered — OWASP: no fool-proof prevention of prompt injection)

| Layer | Rule |
|---|---|
| Input | ≤ 200 chars, control chars and `[PLAYER]`/`[/PLAYER]` stripped, ≤ 10 messages/min per NPC (working) |
| Model | narrow prompt with topic limits; temperature 0.6–0.8, `num_predict` ≤ 80, stop sequences (Modelfile); JSON schema output when the game needs an intent enum |
| Output | strip markdown/emoji; cut at a sentence end ≤ 160 chars; blocklist (slurs, sexual content, self-harm, real people, URLs, prompt fragments) → fallback line |
| Privilege | model text never calls game functions; quests/rewards come from flags |
| Logging | count filter hits and failures; no raw player text in telemetry without consent |

Details and the adversarial case list: `${extensionPath}${/}skills${/}llm-npc/references/safety-and-testing.md`.

## Latency budget

Turn gaps in conversation are ~200 ms (Stivers et al. 2009); under 1 s keeps the flow of thought,
10 s loses attention (Nielsen). Targets (working): acknowledgement (look-at, "thinking" animation,
authored filler) ≤ 0.2 s; full reply p95 ≤ 2.5 s on minimum spec (no streaming); hard timeout 8 s
→ fallback line (Godot `HTTPRequest.timeout` defaults to 0 = never); model preloaded at level
load (Ollama unloads after 5 min idle). Measure with `npc_eval.py` and Ollama's `eval_duration`.

## Testing

Replies vary, so assert properties, not strings. `tests/llm_npc/<npc>.jsonl` holds normal talk,
every state flag, quest/reward triggers, out-of-world questions, injection attempts, harmful
bait, other languages and over-long input. Run:

```
python ${extensionPath}${/}skills${/}llm-npc/scripts/npc_eval.py "tests/llm_npc/*.jsonl" --server http://127.0.0.1:8100 \
  --config design/narrative/npc/<id>.config.json --repeat 5 --out production/llm_npc/<id>-eval.json
```

Safety expectations 100% of runs, style ≥ 90%, latency p95 within budget. Re-run after any change
of model, quantization, prompt, server or Ollama version.

## Cost, disclosure, rating

- **Cost**: API cost per session = Σ turns (input tokens × input price + output × output price);
  input grows with history. Take token counts from the eval report and prices from the provider
  page on the decision date; write the numbers into `memory/decisions.md`. Local: no per-token
  cost, but download size, RAM/VRAM and a higher minimum spec.
- **Steam**: the content survey requires disclosing live-generated AI content and the guardrails
  against illegal content; live-generated Adult Only sexual content is not allowed; players can
  report it through the overlay. AI-drafted lines that ship are pre-generated AI content, also
  disclosed (AI used only as an efficiency tool is not the survey's focus).
- **Ratings**: how IARC/ESRB/PEGI questionnaires treat live-generated text is UNVERIFIED — answer
  for the worst content the guarded system plausibly produces, keep the adversarial report as
  evidence, ask the rating body when unsure.
- **Model and voice licences**: e.g. Llama 3.2 requires a licence copy and "Built with Llama" when
  distributed; synthetic voices fall under `audio_generators` and actor consent.

## Runtime integration (scene_first)

The NPC scene is built in the editor through the MCP; the script only adds behaviour.
- **Godot 4.6/4.7**: an `LlmNpc` node with a typed client script, a child `HTTPRequest` built in
  the editor (timeout 8 s, threads on) referenced by `@export`, a card `.tres`, fallback IDs from
  the line table, one request in flight (input disabled while waiting), `base_url` exported
  (`http://127.0.0.1:8100`). The repository's `OpenLlmNpc.gd` creates an HTTPRequest per call, is
  untyped, has no timeout and lets overlapping replies overwrite the context — write a Kiln client
  against the documented API instead (sketch in the open-llm-npc reference).
- **Unity 6 / Unreal 5.8**: a component on the NPC prefab / Blueprint, card ScriptableObject /
  DataAsset, `UnityWebRequest.timeout` / HTTP module timeout, one request in flight.
The dialogue UI scene belongs to the ui-designer.

## Checks

| Check | Target |
|---|---|
| Policy and licence | `llm_npc` set by the user; licence question closed before shipping |
| `npc_eval.py` | safety 100%, style ≥ 90%, quest/reward exact, p95 ≤ 2.5 s |
| Server stopped / timeout | fallback line ≤ 8 s, no error text shown, game continues |
| Reply after filter | ≤ 160 chars, no markdown, no prompt fragments |
| Disclosure | Steam AI content text drafted from the guardrails actually built |
