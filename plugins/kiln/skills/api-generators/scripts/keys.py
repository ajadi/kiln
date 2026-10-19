"""Paid generators' keys and plans, for `/kiln:settings api`. Stdlib only. Never prints a key.

  python keys.py serve [--no-browser]    # the key page: http://127.0.0.1:<port>/<token>/ (English)
  python keys.py status                  # one row per service: key set or not, plan, where to get a key
  python keys.py check <service>         # a free balance call with the key that is set
  python keys.py plan <service> <plan>   # the user's plan decides the output licence

The page lists every service gen_api.py knows: where to get a key, a field for it, the user's
plan, and Check (a free balance call), Save and Remove. The user pastes the key there, never into
the chat. Saved keys go to the user's environment - on Windows HKCU\\Environment (what "Edit
environment variables for your account" shows), elsewhere ~/.kiln/keys.env with mode 600 - where
gen_api.py reads them without a restart. The page binds 127.0.0.1 only and answers only under a
random token path; a key is never printed, logged or sent anywhere but to its own service's
balance call. The server stops when the user presses Done, 10 minutes after the tab is
closed (the page reports every 5 s that it is open), or after 30 minutes, and prints the status
table. KILN_KEYS_STORE=file forces ~/.kiln/keys.env (tests).
"""

import argparse
import html
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_api  # noqa: E402

# Every text the page shows (English: Kiln's interface language).
STRINGS = {
    "title": "Kiln: keys for paid generators",
    "intro": "The key stays on this computer: it is saved in your user environment, never in a "
             "project, the chat or git. Check makes one free call to the service to show your "
             "balance.",
    "key_set": "key set", "no_key": "no key", "get_a_key": "Get a key:", "key": "Key",
    "plan": "Your plan", "check": "Check", "save": "Save", "remove": "Remove", "done": "Done",
    "closed": "Saved. You can close this tab and go back to the chat.",
    "paste_first": "paste the key first", "works": "works, balance {balance}",
    "refused": "the service refused it: {error}", "not_saved": "not saved",
    "saved_in": "saved in {where}", "removed": "removed",
    "meshy_note": "API keys need a paid plan",
    "plan_unknown": "not set", "plan_free": "free", "plan_pro": "Pro", "plan_studio": "Studio",
    "plan_business": "Business", "plan_enterprise": "Enterprise",
}
T = dict(STRINGS)

LINKS = {"meshy": "https://www.meshy.ai/developers/keys"}
PLANS = ["unknown", "free", "pro", "studio", "business", "enterprise"]


def kiln_home():
    return os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln")


def use_registry():
    return os.name == "nt" and os.environ.get("KILN_KEYS_STORE") != "file"


def keys_file():
    return os.path.join(kiln_home(), "keys.env")


def read_file_keys():
    out = {}
    try:
        with open(keys_file(), encoding="utf-8") as fh:
            for line in fh:
                k, sep, v = line.strip().partition("=")
                if sep and not k.startswith("#"):
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def write_file_keys(keys):
    os.makedirs(kiln_home(), exist_ok=True)
    path = keys_file()
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("# Kiln: API keys for paid generators (kept out of every project)\n")
        for k, v in sorted(keys.items()):
            fh.write(f"{k}={v}\n")
    os.replace(path + ".tmp", path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def store_key(name, value):
    if use_registry():
        import ctypes
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
            if value:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(key, name)
                except OSError:
                    pass
        # tell running programs (new terminals, Explorer) that the environment changed
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 2000, None)
        return "your Windows user environment"
    keys = read_file_keys()
    if value:
        keys[name] = value
    else:
        keys.pop(name, None)
    write_file_keys(keys)
    return keys_file()


def saved_key(adapter):
    if use_registry():
        return os.environ.get(adapter.key_env) or gen_api.user_env(adapter.key_env)
    return os.environ.get(adapter.key_env) or read_file_keys().get(adapter.key_env, "")


def set_plan(service, plan):
    data = gen_api.plans()
    data.setdefault(service, {})["plan"] = plan
    os.makedirs(kiln_home(), exist_ok=True)
    with open(os.path.join(kiln_home(), "gen.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)


def status():
    return [{"service": n, "key_env": a.key_env, "key_set": bool(saved_key(a)),
             "plan": gen_api.plans().get(n, {}).get("plan", "unknown"),
             "get_a_key": LINKS.get(n, "")} for n, a in gen_api.ADAPTERS.items()]


def balance(ad, key):
    gen_api.SECRETS.append(key)
    try:
        return True, T["works"].format(balance=ad.balance(key)["credits"])
    except gen_api.ApiError as e:
        return False, T["refused"].format(error=gen_api.scrub(e))


def page(token):
    e = html.escape
    rows = []
    for r in status():
        options = "".join(f'<option value="{p}"{" selected" if p == r["plan"] else ""}>'
                          f'{e(T.get("plan_" + p, p))}</option>' for p in PLANS)
        note = T.get(r["service"] + "_note", "")
        rows.append(f"""
<section data-service="{r['service']}">
  <h2>{html.escape(r['service'].title())} <small>{e(T['key_set'] if r['key_set'] else T['no_key'])}</small></h2>
  <p>{e(T['get_a_key'])} <a href="{e(r['get_a_key'])}" target="_blank">{e(r['get_a_key'])}</a>{' (' + e(note) + ')' if note else ''}</p>
  <label>{e(T['key'])} <input type="password" autocomplete="off" spellcheck="false"></label>
  <label>{e(T['plan'])} <select>{options}</select></label>
  <button data-act="check">{e(T['check'])}</button> <button data-act="save">{e(T['save'])}</button>
  <button data-act="remove">{e(T['remove'])}</button> <span class="msg"></span>
</section>""")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(T['title'])}</title>
<style>body{{font:15px system-ui;max-width:720px;margin:2em auto;padding:0 1em}}
section{{border:1px solid #ccc;border-radius:8px;padding:1em;margin:1em 0}}
input{{width:24em}} small{{color:#666;font-weight:normal}} .msg{{margin-left:1em}}</style></head>
<body><h1>{e(T['title'])}</h1>
<p>{e(T['intro'])}</p>
{''.join(rows)}
<p><button id="done">{e(T['done'])}</button></p>
<script>
const base = "/{token}/";
for (const s of document.querySelectorAll("section")) {{
  for (const b of s.querySelectorAll("button")) b.onclick = async () => {{
    const body = {{service: s.dataset.service, act: b.dataset.act,
                  key: s.querySelector("input").value, plan: s.querySelector("select").value}};
    const r = await fetch(base + "act", {{method: "POST", body: JSON.stringify(body)}});
    s.querySelector(".msg").textContent = (await r.json()).message;
    if (b.dataset.act !== "check") s.querySelector("input").value = "";
  }};
}}
setInterval(() => fetch(base + "alive", {{method: "POST"}}).catch(() => {{}}), 5000);
document.getElementById("done").onclick = async () => {{
  await fetch(base + "done", {{method: "POST"}});
  document.body.innerHTML = {json.dumps("<p>" + e(T["closed"]) + "</p>")};
}};
</script></body></html>"""


def act(body):
    ad = gen_api.ADAPTERS.get(body.get("service"))
    if not ad:
        return "unknown service"
    key = (body.get("key") or "").strip()
    if body.get("plan") in PLANS:
        set_plan(ad.name, body["plan"])
    if body.get("act") == "remove":
        store_key(ad.key_env, "")
        return T["removed"]
    if not key:
        return T["paste_first"] if body.get("act") != "check" or not saved_key(ad) else \
            balance(ad, saved_key(ad))[1]
    ok, message = balance(ad, key)
    if body.get("act") == "check" or not ok:
        return message if ok else f"{message} - {T['not_saved']}"
    return f"{message}; " + T["saved_in"].format(where=store_key(ad.key_env, key))


def serve(no_browser, port=0, timeout=1800, idle=600):
    token = secrets.token_urlsafe(16)
    done = threading.Event()
    seen = {"t": time.time()}  # the open page says so every 5 s; a closed tab stops the server

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            raw = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.rstrip("/") != f"/{token}":
                return self.send(404, '{"message": "not found"}')
            self.send(200, page(token), "text/html")

        def do_POST(self):
            # read the whole body first: closing with unread bytes makes Windows reset the connection
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if self.path == f"/{token}/alive":
                seen["t"] = time.time()
                return self.send(200, '{"message": "ok"}')
            if self.path == f"/{token}/done":
                self.send(200, '{"message": "done"}')  # answer before the server stops
                self.wfile.flush()
                done.set()
                return
            if self.path != f"/{token}/act":
                return self.send(404, '{"message": "not found"}')
            try:
                message = act(json.loads(raw or b"{}"))
            except Exception as e:  # never echo the request (it holds the key)
                message = f"error: {type(e).__name__}"
            self.send(200, json.dumps({"message": message}))

    server = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = f"http://127.0.0.1:{server.server_port}/{token}/"
    print(json.dumps({"url": url, "note": "open it in the browser; press Done there when finished"}),
          flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not no_browser:
        webbrowser.open(url)
    end = time.time() + timeout
    while not done.wait(1) and time.time() < end and time.time() - seen["t"] < idle:
        pass
    server.shutdown()
    print(json.dumps({"keys": status()}), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--timeout", type=float, default=1800)
    s.add_argument("--idle", type=float, default=600, help="stop this long after the page closed")

    sub.add_parser("status")
    sub.add_parser("check").add_argument("service")
    p = sub.add_parser("plan")
    p.add_argument("service")
    p.add_argument("plan", choices=PLANS)
    a = ap.parse_args()
    if a.cmd == "serve":
        serve(a.no_browser, a.port, a.timeout, a.idle)
        return 0
    if a.cmd == "status":
        print(json.dumps({"keys": status()}, indent=1))
        return 0
    if a.service not in gen_api.ADAPTERS:
        print(f"unknown service {a.service}; known: {', '.join(gen_api.ADAPTERS)}")
        return 1
    ad = gen_api.ADAPTERS[a.service]
    if a.cmd == "plan":
        set_plan(ad.name, a.plan)
        print(f"{ad.name}: plan {a.plan}")
        return 0
    key = saved_key(ad)
    if not key:
        print(f"{ad.name}: no key - /kiln:settings api opens the key page")
        return 1
    ok, message = balance(ad, key)
    print(f"{ad.name}: {message}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
