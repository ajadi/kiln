"""Paid AI generators on the user's own account: estimate, the user's yes, submit, wait, fetch.
Stdlib only.

  python gen_api.py services                                   # adapters, key set or not (never the value)
  python gen_api.py balance <service>                          # free call: remaining credit
  python gen_api.py estimate <service> <task> --asset <name> [--image f ...] [--prompt "..."] [--opt k=v ...]
                    [--from <earlier job>] [--model <file.glb>]  # rigging / animations build on a job
  python gen_api.py actions <service> [--search s] [--category c]  # free: the animation library
  python gen_api.py request <job> --why "..."                  # autopilot: production/SPEND_REQUESTS.md
  python gen_api.py submit <job>                               # only after the user said yes
  python gen_api.py decline <job>                              # the user said no to a request
  python gen_api.py status <job> [--wait] [--timeout 1800]
  python gen_api.py fetch <job> [--out <folder>]               # download + provenance.json
  python gen_api.py jobs                                       # this project's jobs

Run from the project root. Keys come only from the environment (MESHY_API_KEY, ...), or the
user's environment as /kiln:settings stores it (Windows: HKCU\\Environment; elsewhere
~/.kiln/keys.env); never from a flag, never written anywhere, and scrubbed from every message.
`estimate` makes free calls only and writes .kiln/gen/jobs/<job>.json; `submit` spends credits and
refuses unless the estimate is fresh (1 h), unchanged, within the project's caps
(manifest gen_spend_cap_usd, default 5; gen_daily_cap_usd, default 20) and the service is allowed
(gen_services). A create request is never resent automatically: the service may have charged it;
it is counted in .kiln/gen/ledger.jsonl before it is sent (a refusal by the service is
taken back), and a ledger line that does not parse stops every submit.
Submits are one at a time per project (.kiln/gen/spend.lock): the checks, the job claim and
the reservation happen together, so parallel submits cannot pass a cap or send a job twice.
KILN_GEN_FAKE=http://127.0.0.1:<port> sends every call to a local fake API with a dummy key.
"""

import argparse
import base64
import contextlib
import datetime
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

FAKE = os.environ.get("KILN_GEN_FAKE", "")
FAKE_KEY = "kiln-fake-key"
JOB_TTL_S = 3600
REQUEST_TTL_S = 7 * 86400


# --- keys ---------------------------------------------------------------------------------------

def user_env(name):
    """A variable stored for the user but not yet in this process (no restart needed)."""
    if os.name == "nt" and os.environ.get("KILN_KEYS_STORE") != "file":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return str(winreg.QueryValueEx(key, name)[0])
        except OSError:
            return ""
    path = os.path.join(os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln"),
                        "keys.env")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                k, _, v = line.strip().partition("=")
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def key_for(adapter):
    if FAKE:
        return FAKE_KEY
    return os.environ.get(adapter.key_env) or user_env(adapter.key_env)


SECRETS = []


def scrub(text):
    text = str(text)
    for s in SECRETS:
        if s:
            text = text.replace(s, "***")
    return re.sub(r"(Bearer\s+)\S+", r"\1***", text)


# --- http ---------------------------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(scrub(message))
        self.status = status


def request(method, url, key=None, body=None, timeout=60):
    if FAKE:
        url = re.sub(r"^https://[^/]+", FAKE.rstrip("/"), url)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, raw, dict(r.headers)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, f"{method} {url.split('?')[0]} -> HTTP {e.code}: {e.read()[:400]!r}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ApiError(0, f"{method} {url.split('?')[0]} -> {e}")


def get_json(url, key):
    return json.loads(request("GET", url, key)[1] or b"{}")


# --- adapters -----------------------------------------------------------------------------------

class Meshy:
    """docs.meshy.ai (llms-full.txt, read 2026-10-19). Credits from the pricing page; ~USD from the
    Pro plan ($20 / 1,000 credits; UNVERIFIED, localized pricing pages)."""
    name, category, key_env = "meshy", "model", "MESHY_API_KEY"
    base = "https://api.meshy.ai/openapi/v1"
    usd_per_credit = 0.02
    price_source = "https://docs.meshy.ai/api/pricing (2026-10-19)"
    licence = {"free": "CC BY 4.0, Meshy owns the output (Meshy terms 3.2)",
               "paid": "owned by the user (Meshy terms 3.3)"}
    notes = ["API outputs are deleted by Meshy after 3 days (fetch right away)",
             "Meshy may train on inputs and outputs of non-Enterprise accounts"]
    tasks = ("image-to-3d", "rigging", "animations")
    # what each task can start from (--from <kiln job>); Meshy keeps task outputs 3 days
    chains = {"rigging": ("image-to-3d",), "animations": ("rigging",)}
    keep_days = 3

    def balance(self, key):
        data = get_json(f"{self.base}/balance", key)
        return {"credits": data.get("balance"), "raw": data}

    def actions(self, key, search="", category=""):
        """The animation library (free call): every action_id the animations task accepts."""
        query = urllib.parse.urlencode({k: v for k, v in (("search", search),
                                                           ("category", category)) if v})
        rows = get_json(f"{self.base}/animations/library" + ("?" + query if query else ""), key)
        return [{k: r.get(k) for k in ("action_id", "name", "category", "sub_category",
                                       "preview_url")} for r in rows]

    def check(self, task, inputs, opts):
        """Refuse a request the service would refuse, before any money is involved."""
        if task == "rigging" and not (inputs["from_remote"] or inputs["model"]):
            raise SystemExit("rigging needs --from <image-to-3d job> or --model <textured "
                             "humanoid .glb facing +Z>")
        if task == "animations":
            if not inputs["from_remote"]:
                raise SystemExit("animations need --from <rigging job>")
            ids = action_ids(opts)
            if not 1 <= len(ids) <= 10:
                raise SystemExit("--opt actions=<id,id,...> takes 1 to 10 action ids "
                                 "(gen_api.py actions meshy lists them)")
            if len(set(ids)) != len(ids):
                raise SystemExit("an action id is listed twice")

    def estimate(self, task, opts):
        """Image to 3D credits (pricing page): meshy-7.1 / meshy-6 mesh 20, textured 30, 8K 35,
        Ultra geometry +5 (7.1 only); meshy-6-lite and meshy-t2 / t2.5 mesh 5, textured 15,
        8K 20 (t2 models; 6-lite has no 4K/8K). Rigging 5; animations 3 per action."""
        if task == "rigging":
            return 5
        if task == "animations":
            return 3 * len(action_ids(opts))
        model = str(opts.get("ai_model", "meshy-7.1"))
        texture = str(opts.get("texture", "true")).lower() != "false"
        eight_k = str(opts.get("texture_resolution", "2k")) == "8k"
        if model in ("meshy-6-lite", "meshy-t2", "meshy-t2.5"):
            return (20 if eight_k else 15) if texture else 5
        credits = (35 if eight_k else 30) if texture else 20
        if opts.get("geometry_resolution") in ("2k", "4k") and model in ("meshy-7.1", "latest"):
            credits += 5
        return credits

    def subfolder(self, task, opts):
        return {"rigging": "rig",
                "animations": "anim-" + "-".join(map(str, action_ids(opts)))}.get(task, "")

    def body(self, task, inputs, opts):
        if task == "rigging":
            body = ({"input_task_id": inputs["from_remote"]} if inputs["from_remote"]
                    else {"model_url": data_uri(inputs["model"])})
            for k in ("height_meters",):
                if k in opts:
                    body[k] = float(opts[k])
            return body
        if task == "animations":
            body = {"rig_task_id": inputs["from_remote"], "action_ids": action_ids(opts)}
            if "fps" in opts:
                body["post_process"] = {"operation_type": "change_fps", "fps": int(opts["fps"])}
            return body
        if len(inputs["images"]) != 1:
            raise SystemExit("meshy image-to-3d takes one --image (multi-view: not in this version)")
        body = {"image_url": data_uri(inputs["images"][0]), "ai_model": opts.get("ai_model", "meshy-7.1"),
                "should_texture": str(opts.get("texture", "true")).lower() != "false",
                "target_formats": ["glb"]}
        for k in ("enable_pbr", "texture_resolution", "geometry_resolution", "topology",
                  "target_polycount", "pose_mode", "should_remesh", "origin_at"):
            if k in opts:
                body[k] = typed(opts[k])
        return body

    def submit(self, task, body, key):
        status, raw, _ = request("POST", f"{self.base}/{task}", key, body, timeout=120)
        return json.loads(raw)["result"]

    def status(self, task, remote_id, key):
        data = get_json(f"{self.base}/{task}/{remote_id}", key)
        state = {"PENDING": "queued", "IN_PROGRESS": "running", "SUCCEEDED": "succeeded",
                 "FAILED": "failed", "CANCELED": "cancelled"}.get(data.get("status"), "running")
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        basic = result.get("basic_animations") or {}
        if task == "rigging":
            pairs = ((result.get("rigged_character_glb_url"), "rigged.glb"),
                     (result.get("rigged_character_fbx_url"), "rigged.fbx"),
                     (basic.get("walking_glb_url"), "walk.glb"),
                     (basic.get("running_glb_url"), "run.glb"))
        elif task == "animations":
            pairs = ((result.get("animation_glb_url"), "animation.glb"),
                     (result.get("animation_fbx_url"), "animation.fbx"),
                     (result.get("processed_animation_fps_fbx_url"), "animation-fps.fbx"))
        else:
            pairs = (((data.get("model_urls") or {}).get("glb"), "model.glb"),
                     (data.get("thumbnail_url"), "preview.png"))
        outputs = [(url, name) for url, name in pairs if url]
        return {"state": state, "progress": data.get("progress"), "outputs": outputs,
                "error": (data.get("task_error") or {}).get("message", ""),
                "credits": data.get("consumed_credits")}


ADAPTERS = {a.name: a for a in (Meshy(),)}


# --- helpers ------------------------------------------------------------------------------------

def typed(value):
    v = str(value)
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def action_ids(opts):
    return [int(x) for x in re.split(r"[,\s]+", str(opts.get("actions", ""))) if x.strip()]


def data_uri(path):
    mime = ("model/gltf-binary" if path.lower().endswith(".glb")
            else mimetypes.guess_type(path)[0] or "image/png")
    with open(path, "rb") as fh:
        return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest(root):
    out = {}
    try:
        with open(os.path.join(root, "manifest.md"), encoding="utf-8-sig") as fh:
            for line in fh:
                k, sep, v = line.strip().partition("=")
                if sep:
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def plans():
    path = os.path.join(os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln"),
                        "gen.json")
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def jobs_dir(root):
    return os.path.join(root, ".kiln", "gen", "jobs")


def load_job(root, job):
    path = os.path.join(jobs_dir(root), job + ".json")
    if not os.path.isfile(path):
        raise SystemExit(f"no job {job} (gen_api.py jobs lists them)")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_job(root, data):
    os.makedirs(jobs_dir(root), exist_ok=True)
    path = os.path.join(jobs_dir(root), data["job"] + ".json")
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(path + ".tmp", path)


def ledger_path(root):
    return os.path.join(root, ".kiln", "gen", "ledger.jsonl")


def ledger_today(root):
    """Today's estimated spend. A line that does not parse stops spending instead of being
    skipped (bug hunt 2026-10-20: a blank line ended the count and lifted the daily cap)."""
    today, total = datetime.date.today().isoformat(), 0.0
    try:
        with open(ledger_path(root), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return total
    except OSError as e:
        raise SystemExit(f"the spend ledger cannot be read ({e}); nothing is submitted until it can")
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            usd = float(row.get("usd_est") or 0)
        except (ValueError, TypeError, AttributeError):
            raise SystemExit(f"{ledger_path(root)} line {number} does not parse; nothing is "
                             "submitted until it is fixed (the daily cap is counted from it)")
        if str(row.get("date", "")).startswith(today):
            total += usd
    return total


def add_ledger(root, data, usd, note):
    os.makedirs(os.path.dirname(ledger_path(root)), exist_ok=True)
    with open(ledger_path(root), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"date": datetime.datetime.now().isoformat(timespec="seconds"),
                             "job": data["job"], "service": data["service"],
                             "credits": data["credits"] if usd >= 0 else -data["credits"],
                             "usd_est": usd, "note": note}) + "\n")


def money(m, key, default):
    """A cap from manifest.md: a finite number >= 0, else the submit stops (`nan` once turned
    both caps off, `5$` crashed)."""
    raw = str(m.get(key, default)).strip().lstrip("$").rstrip("$").strip()
    try:
        value = float(raw)
    except ValueError:
        raise SystemExit(f"{key}={m.get(key)} in manifest.md is not a number of dollars")
    if value != value or value < 0 or value == float("inf"):
        raise SystemExit(f"{key}={m.get(key)} in manifest.md is not a usable cap")
    return value


def adapter_or_exit(name):
    if name not in ADAPTERS:
        raise SystemExit(f"unknown service {name}; known: {', '.join(ADAPTERS)}")
    return ADAPTERS[name]


def need_key(adapter):
    key = key_for(adapter)
    if not key:
        raise SystemExit(f"{adapter.key_env} is not set. /kiln:settings api opens the key page "
                         "or as a user environment variable - never paste it into the chat.")
    SECRETS.append(key)
    return key


# --- commands -----------------------------------------------------------------------------------

def cmd_services(a, root):
    return {"services": [{"service": n, "category": ad.category, "key_env": ad.key_env,
                          "key_set": bool(key_for(ad)), "tasks": list(ad.tasks),
                          "plan": plans().get(n, {}).get("plan", "unknown")}
                         for n, ad in ADAPTERS.items()]}


def cmd_balance(a, root):
    ad = adapter_or_exit(a.service)
    return {"service": ad.name, **{k: v for k, v in ad.balance(need_key(ad)).items() if k != "raw"}}


def request_hash(data):
    """What the user said yes to: the task, its options and the exact input files."""
    return hashlib.sha256(json.dumps(
        {"task": data["task"], "opts": data["opts"], "images": [sha256(p) for p in data["images"]],
         "prompt": data["prompt"], "model": sha256(data["model"]) if data.get("model") else "",
         "from": data.get("from_remote", "")}, sort_keys=True).encode()).hexdigest()


def source_job(root, ad, task, job):
    """The earlier job a task builds on (--from): same service, the right kind, still kept."""
    if not job:
        return {}
    src = load_job(root, job)
    allowed = getattr(ad, "chains", {}).get(task, ())
    if src["service"] != ad.name or src["task"] not in allowed:
        need = " or ".join(f"{t} job" for t in allowed) or "nothing"
        raise SystemExit(f"{ad.name} {task} starts from a {need}; {job} is {src['service']} "
                         f"{src['task']}")
    if src["state"] not in ("succeeded", "fetched"):
        raise SystemExit(f"{job} is {src['state']}; it has to succeed first")
    age_days = (time.time() - src.get("submitted_at", 0)) / 86400
    if age_days > getattr(ad, "keep_days", 1e9):
        raise SystemExit(f"{job} is {age_days:.0f} days old and {ad.name} keeps outputs "
                         f"{ad.keep_days} days: start from --model <the fetched .glb> instead")
    return src


def cmd_estimate(a, root):
    ad = adapter_or_exit(a.service)
    if a.task not in ad.tasks:
        raise SystemExit(f"{ad.name} tasks: {', '.join(ad.tasks)}")
    bad = [o for o in a.opt if "=" not in o]
    if bad:
        raise SystemExit(f"--opt takes key=value: {', '.join(bad)}")
    opts = dict(o.split("=", 1) for o in a.opt)
    images = [os.path.abspath(p) for p in a.image]
    for p in images + ([os.path.abspath(a.model)] if a.model else []):
        if not os.path.isfile(p):
            raise SystemExit(f"no such file: {p}")
    src = source_job(root, ad, a.task, a.from_job)
    model = os.path.abspath(a.model) if a.model else ""
    if hasattr(ad, "check"):
        ad.check(a.task, {"images": images, "model": model,
                          "from_remote": src.get("remote_id", "")}, opts)
    key = need_key(ad)
    credits = ad.estimate(a.task, opts)
    usd = round(credits * ad.usd_per_credit, 2)
    try:
        before = ad.balance(key)["credits"]
    except ApiError as e:
        raise SystemExit(f"balance check failed: {e}")
    plan = plans().get(ad.name, {}).get("plan", "unknown")
    licence = ad.licence["paid" if plan not in ("unknown", "free") else "free"]
    job = f"{ad.name}-{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(2).hex()}"
    data = {"job": job, "service": ad.name, "task": a.task, "asset": a.asset, "state": "estimated",
            "estimated_at": time.time(), "opts": opts, "images": images, "prompt": a.prompt,
            "model": model, "from_job": a.from_job or "", "from_remote": src.get("remote_id", ""),
            "credits": credits, "usd_est": usd,
            "price_source": ad.price_source, "balance_before": before, "plan": plan,
            "licence": licence, "notes": ad.notes}
    data["request_hash"] = request_hash(data)
    save_job(root, data)
    after = before - credits if isinstance(before, (int, float)) else None
    return {"job": job, "ask_the_user": (
        f"{ad.name} {a.task} for '{a.asset}': {credits} credits (about ${usd}); balance "
        f"{before} -> {after}. Output licence on your plan ({plan}): {licence}. "
        + "; ".join(ad.notes) + ". Generate? (yes/no)"), **{k: data[k] for k in (
            "credits", "usd_est", "balance_before", "plan", "licence")}}


SPEND_FILE = os.path.join("production", "SPEND_REQUESTS.md")
SPEND_HEAD = ("# Spend requests\n\nPaid generations waiting for the user's yes (written under "
              "autopilot; nothing here is spent until the user answers). On a yes the agent runs "
              "`gen_api.py submit <job>`; on a no, the row is marked declined.\n\n"
              "| Job | Asset | Service | Task | Credits | ~USD | Why | State |\n"
              "|---|---|---|---|---|---|---|---|\n")


def spend_row(data, why, state):
    return (f"| {data['job']} | {data['asset']} | {data['service']} | {data['task']} | "
            f"{data['credits']} | {data['usd_est']} | {why.replace('|', '/')} | {state} |")


def mark_spend_request(root, job, state):
    path = os.path.join(root, SPEND_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return
    for i, line in enumerate(lines):
        if line.startswith(f"| {job} |"):
            cells = line.split(" | ")
            cells[-1] = state + " |"
            lines[i] = " | ".join(cells)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def cmd_request(a, root):
    """Under autopilot: keep the estimate for the user's yes instead of spending."""
    data = load_job(root, a.job)
    if data["state"] != "estimated":
        raise SystemExit(f"job {a.job} is {data['state']}; one request per estimate")
    path = os.path.join(root, SPEND_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.isfile(path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write((SPEND_HEAD if new else "") + spend_row(data, a.why, "waiting") + "\n")
    data.update(state="requested", why=a.why)
    save_job(root, data)
    return {"job": a.job, "state": "requested", "file": SPEND_FILE.replace("\\", "/"),
            "ask_the_user": "In the next report: " + spend_row(data, a.why, "yes/no?")}


@contextlib.contextmanager
def spend_lock(root, timeout=30.0, stale=120.0):
    """One submit at a time per project: the job's state, the daily cap and the reservation are
    read and written under it (review 2026-10-21, KILN-REV-03: two submits at once both passed
    a cap, and one job could be sent twice). A lock older than `stale` seconds is a crashed
    process's and is taken over."""
    path = os.path.join(root, ".kiln", "gen", "spend.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) > stale:
                    os.remove(path)
                    continue
            except OSError:
                continue
            if time.time() > deadline:
                raise SystemExit("another submit holds .kiln/gen/spend.lock; try again shortly")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def cmd_submit(a, root):
    with spend_lock(root):
        data, ad, key, body = claim_submit(a, root)
    return send_submit(a, root, data, ad, key, body)


def claim_submit(a, root):
    """Under the spend lock: every check on a fresh read of the job and the ledger, then the
    job marked submitting and its cost reserved - the network call comes after the lock."""
    data = load_job(root, a.job)
    ad = adapter_or_exit(data["service"])
    if data["state"] not in ("estimated", "requested"):
        raise SystemExit(f"job {a.job} is {data['state']}; make a new estimate to generate again")
    ttl = REQUEST_TTL_S if data["state"] == "requested" else JOB_TTL_S
    if time.time() - data["estimated_at"] > ttl:
        raise SystemExit("the estimate is too old (1 h; a spend request 7 days): make a new one "
                         "and ask again")
    if data.get("from_job"):
        source_job(root, ad, data["task"], data["from_job"])   # still kept by the service
    if request_hash(data) != data["request_hash"]:
        raise SystemExit("the inputs changed since the estimate: make a new one and ask again")
    m = manifest(root)
    allowed = [s.strip() for s in m.get("gen_services", "").split(",") if s.strip()]
    if allowed and ad.name not in allowed:
        raise SystemExit(f"{ad.name} is not in gen_services ({', '.join(allowed)}) in manifest.md")
    if data["state"] == "requested":
        row = spend_state(root, a.job)
        if row is not None and row != "waiting":
            raise SystemExit(f"the spend request for {a.job} is '{row}' in {SPEND_FILE}: only a "
                             "waiting request the user said yes to is submitted")
    cap = money(m, "gen_spend_cap_usd", 5)
    daily = money(m, "gen_daily_cap_usd", 20)
    if data["usd_est"] > cap:
        raise SystemExit(f"about ${data['usd_est']} is over gen_spend_cap_usd={cap}; the user can "
                         "raise it with /kiln:settings")
    if ledger_today(root) + data["usd_est"] > daily:
        raise SystemExit(f"today's spend would pass gen_daily_cap_usd={daily}")
    key = need_key(ad)
    body = ad.body(data["task"], {"images": data["images"], "prompt": data["prompt"],
                                  "model": data.get("model", ""),
                                  "from_remote": data.get("from_remote", "")}, data["opts"])
    data["state"] = "submitting"
    data["claimed_by"] = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    save_job(root, data)
    # counted before the request leaves: a timeout or a 5xx may still have been charged (bug
    # hunt 2026-10-20: those never reached the ledger, so resubmits passed the daily cap)
    add_ledger(root, data, data["usd_est"], "submitted")
    return data, ad, key, body


def send_submit(a, root, data, ad, key, body):
    try:
        remote = ad.submit(data["task"], body, key)
    except ApiError as e:
        unknown = e.status in (0, 500, 502, 503, 504)
        data.update(state="submit-unknown" if unknown else "failed", error=str(e))
        save_job(root, data)
        if not unknown:  # the service refused it (4xx): nothing was charged
            add_ledger(root, data, -data["usd_est"], f"refused by the service ({e.status})")
        raise SystemExit(f"submit failed: {e}. Not resent: the service may have charged it - "
                         "check the service's dashboard before trying again.")
    was_requested = data.get("why") is not None
    data.update(state="running", remote_id=remote, submitted_at=time.time())
    save_job(root, data)
    if was_requested:
        mark_spend_request(root, a.job, "submitted")
    return {"job": a.job, "state": "running", "remote_id": remote}


def spend_state(root, job):
    """The State cell of a job's row in production/SPEND_REQUESTS.md, or None."""
    try:
        with open(os.path.join(root, SPEND_FILE), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(f"| {job} |"):
                    return line.rstrip().rstrip("|").rsplit("|", 1)[-1].strip().lower()
    except OSError:
        return None
    return None


def cmd_decline(a, root):
    """The user said no to a spend request: the job can no longer be submitted."""
    data = load_job(root, a.job)
    if data["state"] not in ("estimated", "requested"):
        raise SystemExit(f"job {a.job} is {data['state']}")
    data["state"] = "declined"
    save_job(root, data)
    mark_spend_request(root, a.job, "declined")
    return {"job": a.job, "state": "declined"}


def cmd_status(a, root):
    data = load_job(root, a.job)
    ad = adapter_or_exit(data["service"])
    if data["state"] in ("estimated", "requested", "declined", "submitting", "submit-unknown") \
            or not data.get("remote_id"):  # nothing at the service to ask about
        return {"job": a.job, "state": data["state"], **({"error": data["error"]}
                                                         if data.get("error") else {})}
    key = need_key(ad)
    deadline, delay = time.time() + a.timeout, 5.0
    while True:
        try:
            st = ad.status(data["task"], data["remote_id"], key)
        except ApiError as e:
            if e.status == 429 and a.wait and time.time() < deadline:
                time.sleep(delay)
                continue
            raise SystemExit(f"status failed: {e}")
        if st["state"] in ("succeeded", "failed", "cancelled") or not a.wait:
            break
        if time.time() > deadline:
            return {"job": a.job, "state": "running", "progress": st.get("progress"),
                    "note": "still running; run status --wait again later"}
        time.sleep(delay)
        delay = min(delay * 1.5, 60)
    data["state"] = st["state"]
    if st.get("error"):
        data["error"] = scrub(st["error"])
    save_job(root, data)
    out = {"job": a.job, "state": st["state"], "progress": st.get("progress")}
    if st["state"] == "succeeded" and a.wait:
        out["fetched"] = cmd_fetch(argparse.Namespace(job=a.job, out=None), root, st)
    return out


def cmd_fetch(a, root, st=None):
    data = load_job(root, a.job)
    ad = adapter_or_exit(data["service"])
    key = need_key(ad)
    st = st or ad.status(data["task"], data["remote_id"], key)
    if st["state"] != "succeeded":
        raise SystemExit(f"job {a.job} is {st['state']}")
    sub = ad.subfolder(data["task"], data["opts"]) if hasattr(ad, "subfolder") else ""
    out = a.out or os.path.join(root, "art", "generated", data["asset"], sub)
    os.makedirs(out, exist_ok=True)
    files = []
    for url, name in st["outputs"]:
        _, raw, _ = request("GET", url, None, timeout=300)
        path = os.path.join(out, name)
        with open(path, "wb") as fh:
            fh.write(raw)
        files.append({"file": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    if not any(f["file"].endswith(".glb") for f in files):
        raise SystemExit("the service returned no GLB")
    prov = {"tool": data["service"], "version": f"{data['task']} {data['opts'].get('ai_model', 'default')}",
            "service": data["service"], "task": data["task"], "remote_task_id": data["remote_id"],
            "kiln_job": data["job"], "prompt": data["prompt"], "settings": data["opts"],
            "inputs": [{"file": os.path.relpath(p, root).replace("\\", "/"), "sha256": sha256(p)}
                       for p in data["images"] + ([data["model"]] if data.get("model") else [])],
            "from_job": data.get("from_job", ""),
            "outputs": files,
            "cost": {"credits": data["credits"], "usd_est": data["usd_est"],
                     "estimate_source": data["price_source"],
                     "balance_before": data["balance_before"]},
            "plan_declared": data["plan"], "licence": data["licence"],
            # CC BY output (Meshy's free plan) must credit its owner (bug hunt 2026-10-20)
            "attribution": (f"{data['asset']}: generated with {data['service'].capitalize()}, "
                            f"{data['licence'].split(',')[0]}"
                            if data["licence"].upper().startswith("CC BY") else ""),
            "notes": data["notes"], "ai_generated": True,
            "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    with open(os.path.join(out, "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(prov, fh, indent=1)
    data["state"] = "fetched"
    data["out"] = os.path.relpath(out, root).replace("\\", "/")
    save_job(root, data)
    return {"out": data["out"], "files": [f["file"] for f in files]}


def cmd_actions(a, root):
    ad = adapter_or_exit(a.service)
    if not hasattr(ad, "actions"):
        raise SystemExit(f"{ad.name} has no animation library")
    return {"service": ad.name, "actions": ad.actions(need_key(ad), a.search, a.category)}


def cmd_jobs(a, root):
    rows = []
    folder = jobs_dir(root)
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            d = json.load(fh)
        rows.append({k: d.get(k) for k in ("job", "service", "task", "asset", "state", "credits")})
    return {"jobs": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("services")
    b = sub.add_parser("balance")
    b.add_argument("service")
    e = sub.add_parser("estimate")
    e.add_argument("service")
    e.add_argument("task")
    e.add_argument("--asset", required=True)
    e.add_argument("--image", action="append", default=[])
    e.add_argument("--prompt", default="")
    e.add_argument("--opt", action="append", default=[])
    e.add_argument("--from", dest="from_job", default="")
    e.add_argument("--model", default="")
    ac = sub.add_parser("actions")
    ac.add_argument("service")
    ac.add_argument("--search", default="")
    ac.add_argument("--category", default="")
    r = sub.add_parser("request")
    r.add_argument("job")
    r.add_argument("--why", required=True)
    for name in ("submit", "fetch", "decline"):
        p = sub.add_parser(name)
        p.add_argument("job")
        if name == "fetch":
            p.add_argument("--out")
    s = sub.add_parser("status")
    s.add_argument("job")
    s.add_argument("--wait", action="store_true")
    s.add_argument("--timeout", type=float, default=1800)
    sub.add_parser("jobs")
    a = ap.parse_args()
    root = os.getcwd()
    try:
        result = globals()["cmd_" + a.cmd](a, root)
    except ApiError as err:
        print(json.dumps({"error": scrub(err)}))
        return 1
    except SystemExit as err:
        print(json.dumps({"error": scrub(err.code)}))
        return 1
    print(scrub(json.dumps(result, indent=1)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
