---
name: gpu-server
description: Rented GPU servers for heavy jobs - provider-neutral connection profile outside the project, start on demand and stop after every job, per-run spend cap, environment bootstrap, push / run / pull with provenance, one-job lock, failure handling, and which jobs go remote (open-weight 3D and image generators, Cycles bakes and batch renders, audio/music renders, ML tools) versus local (editor work, frame-time measurements). Load when model_generators or audio_generators is `remote`, or when a job is too heavy for this machine.
user-invocable: false
---

# Rented GPU servers

`scripts/gpu_job.py` runs one job: start the server, push inputs, run under a spend cap, pull the
outputs with a `provenance.json`, stop the server. Everything provider-specific is a command
template in the machine's profile file, so the same script drives RunPod, Vast.ai, a home server
or any SSH box.

## 1. The profile lives outside the project

`${CLAUDE_PLUGIN_DATA}/gpu.json` (else `~/.config/kiln/gpu.json`): host, SSH key **path**,
provider ids, price per hour, start / stop / status commands. Never put a host, key, token or
provider id in the project or in git; API tokens stay in the provider CLI's own login or in an
environment variable. The script's header shows the profile format. Examples to adapt (verify
against your CLI version):

| Provider | start / stop / status | transport |
|---|---|---|
| RunPod (`runpodctl`) | `runpodctl pod start <id>` / `pod stop <id>` / `pod get <id>` (status and SSH details) | ssh + scp to the pod's SSH endpoint |
| Vast.ai (`vastai`) | `vastai start instance <id>` (UNVERIFIED in the current docs) / `vastai stop instance <id>` (compute billing stops, disk storage still bills) / `vastai show instance <id>`; `vastai ssh-url <id>` | `vastai copy local:<src> <id>:<dst>` and back, or ssh + scp |
| Own server | wake-on-LAN or a power script / `ssh host sudo poweroff` / `ssh host true` | ssh + scp |

Ask the user once to create the account, pay and log the CLI in (no automated route: an account
and money); everything after that is yours.

## 2. Lifecycle and money

- Start on demand; stop after every run (`gpu_job.py` does unless `--keep`). `--keep` only when the
  profile's own idle auto-stop exists (provider setting or a server-side idle script).
- Every run has `--max-usd`; the script turns it into a wall-clock limit (`max_usd /
  usd_per_hour`), kills the transport by PID when it is hit, stops the server, and fails with
  "spend cap". Report `cost_usd_est` per run and the night's total to the user. Spending beyond
  what the user approved is a hard stop.
- `gpu_job.py estimate --minutes N` before a batch: tell the user the estimate when it is new.
- One job at a time per profile (`<gpu.json>.lock`); a lock left by a dead process is taken over.

## 3. Environment on the server

- First run: check the driver and CUDA (`nvidia-smi`), make one venv per tool, keep model weights
  in a cache folder on the server's persistent disk (re-downloading TRELLIS-class weights costs
  more than the job), and keep the setup in a `setup_env.sh` the profile's `setup` runs. Record
  peak VRAM (`nvidia-smi --query-gpu=memory.used --format=csv` during the run) in the report.
- Choose the GPU by the model's VRAM need from the image-to-model skill, not by price alone; a job
  that runs out of memory costs the start-up and fails.

## 4. Jobs, outputs, provenance

- `gpu_job.py run --tool <name> --push <inputs> --cmd "<command in the job folder>" --pull <dir>
  --into art/gen/<asset> --max-usd <cap>`: inputs land in `<workdir>/<job id>/` by base name.
- `provenance.json` next to the outputs: tool, profile, GPU, command, input sha256, start/end,
  wall seconds, estimated cost, exit code. Generator outputs then go through the normal pipeline
  (cleanup in Blender through the MCP, gates) like any other source.
- Failures: preemption or disconnect → the run fails, the server is stopped, rerun the same job;
  out of memory → a bigger GPU or a smaller resolution, never a silent downgrade of the asset;
  a job that has to resume writes checkpoints in its job folder.

## 5. What goes remote

| Remote | Local |
|---|---|
| open-weight image-to-3D and image models (`model_generators=remote`), audio/music models (`audio_generators=remote`) | all editor work (Blender and the engine through their MCP) |
| long Cycles bakes and batch renders (export the scene, render headless on the server) | frame-time and input-latency measurements (they measure this machine) |
| ML tools (upscalers, background removal at scale) | short scripts and checks |

With `model_generators=remote` the guard allows generator runs only through `gpu_job.py`; a local
run or a paid API is denied.
