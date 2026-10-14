"""Local review board: show images (references, captures, variants) to the user in the browser,
collect likes / dislikes / comments / a choice, and exit when the user presses Send.

  python board.py build <board_dir> --title "Style directions" [--images <folder> ...]
                       [--mode single|multi|none] [--question "Which direction?"]
  python board.py serve <board_dir>          # run in the background; exits after Send

<board_dir>/board.json (written by build, editable by hand or by the agent):
  {"title": "...", "question": "...", "mode": "single|multi|none",
   "groups": [{"id": "A", "title": "Direction A — Rust & Neon", "text": "visual rule...",
               "items": [{"src": "img/a1.png", "caption": "...", "source": "url"}]}]}

Feedback is written to <board_dir>/feedback.json ({"latest": {...}, "history": [...]}) and
printed. Run `serve` as a background task: its exit is the signal that the user answered.
"""

import argparse
import html
import json
import os
import shutil
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def build(board_dir, title, folders, mode, question):
    os.makedirs(os.path.join(board_dir, "img"), exist_ok=True)
    groups = []
    for n, folder in enumerate(folders):
        items = []
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(IMAGE_EXT):
                dst = os.path.join(board_dir, "img", f"{n}_{name}")
                shutil.copy2(os.path.join(folder, name), dst)
                items.append({"src": f"img/{n}_{name}", "caption": os.path.splitext(name)[0]})
        groups.append({"id": chr(65 + n), "title": os.path.basename(folder.rstrip("/\\")),
                       "text": "", "items": items})
    spec = {"title": title, "question": question, "mode": mode, "groups": groups}
    with open(os.path.join(board_dir, "board.json"), "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)
    print("board.json written; edit group titles/text, then: python board.py serve", board_dir)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>
body{{font:15px system-ui,sans-serif;margin:0;padding:16px 24px 120px;background:#16181c;color:#e8e8e8}}
h1{{font-size:22px}} .q{{color:#9cc3ff;margin:4px 0 16px}}
.group{{border:1px solid #333;border-radius:8px;padding:12px;margin:14px 0}}
.group.sel{{border-color:#5aa0ff;box-shadow:0 0 0 2px #5aa0ff55}}
.gh{{display:flex;gap:12px;align-items:center}} .gh h2{{margin:0;font-size:18px}}
.gt{{color:#bbb;white-space:pre-wrap;margin:6px 0}}
.items{{display:flex;flex-wrap:wrap;gap:10px}}
.it{{width:280px;background:#202329;border-radius:6px;padding:6px}}
.it img{{width:100%;border-radius:4px;cursor:zoom-in}} .cap{{font-size:12px;color:#aaa}}
.btns button{{margin-right:4px;background:#2b2f36;color:#ddd;border:1px solid #444;border-radius:4px;cursor:pointer}}
.btns button.on{{background:#3a6;border-color:#3a6;color:#fff}} .btns button.no.on{{background:#a33;border-color:#a33}}
textarea{{width:100%;background:#202329;color:#ddd;border:1px solid #444;border-radius:4px}}
#bar{{position:fixed;left:0;right:0;bottom:0;background:#0d0f12;padding:12px 24px;border-top:1px solid #333}}
#send{{font-size:16px;padding:8px 22px;background:#5aa0ff;border:0;border-radius:6px;color:#000;cursor:pointer}}
#zoom{{position:fixed;inset:0;background:#000e;display:none;align-items:center;justify-content:center}}
#zoom img{{max-width:96vw;max-height:96vh}}
</style></head><body><h1>{title}</h1><div class="q">{question}</div><div id="groups"></div>
<div id="bar"><textarea id="overall" rows="2" placeholder="Overall comment"></textarea>
<button id="send">Send</button> <span id="msg"></span></div>
<div id="zoom" onclick="this.style.display='none'"><img id="zimg"></div>
<script>
const spec = {spec};
const state = {{chosen: [], items: {{}}, groups: {{}}}};
const root = document.getElementById('groups');
spec.groups.forEach(g => {{
  const d = document.createElement('div'); d.className = 'group'; d.id = 'g_' + g.id;
  let pick = spec.mode === 'none' ? '' : `<button class="pick">${{spec.mode === 'multi' ? '☐ Pick' : '◯ Pick'}}</button>`;
  d.innerHTML = `<div class="gh"><h2>${{g.id}} — ${{g.title}}</h2>${{pick}}</div><div class="gt">${{g.text || ''}}</div><div class="items"></div>
    <textarea rows="1" placeholder="Comment on ${{g.id}}"></textarea>`;
  d.querySelector('textarea').oninput = e => state.groups[g.id] = e.target.value;
  const p = d.querySelector('.pick');
  if (p) p.onclick = () => {{
    if (spec.mode === 'single') state.chosen = [g.id];
    else state.chosen = state.chosen.includes(g.id) ? state.chosen.filter(x => x !== g.id) : [...state.chosen, g.id];
    document.querySelectorAll('.group').forEach(x => x.classList.toggle('sel', state.chosen.includes(x.id.slice(2))));
  }};
  g.items.forEach(it => {{
    const e = document.createElement('div'); e.className = 'it';
    e.innerHTML = `<img src="${{it.src}}"><div class="cap">${{it.caption || ''}}</div>
      <div class="btns"><button class="yes">👍</button><button class="no">👎</button></div>`;
    e.querySelector('img').onclick = () => {{ zimg.src = it.src; zoom.style.display = 'flex'; }};
    const set = v => {{ state.items[it.src] = state.items[it.src] === v ? 0 : v;
      e.querySelector('.yes').classList.toggle('on', state.items[it.src] === 1);
      e.querySelector('.no').classList.toggle('on', state.items[it.src] === -1); }};
    e.querySelector('.yes').onclick = () => set(1); e.querySelector('.no').onclick = () => set(-1);
    d.querySelector('.items').appendChild(e);
  }});
  root.appendChild(d);
}});
document.getElementById('send').onclick = async () => {{
  const fb = {{chosen: state.chosen, overall: document.getElementById('overall').value,
    group_comments: state.groups,
    liked: Object.keys(state.items).filter(k => state.items[k] === 1),
    disliked: Object.keys(state.items).filter(k => state.items[k] === -1)}};
  try {{ await fetch('/api/feedback', {{method: 'POST', body: JSON.stringify(fb)}});
    document.getElementById('msg').textContent = 'Sent. You can close this tab.'; }}
  catch (e) {{ document.getElementById('msg').textContent = 'The server does not answer - copy this and paste it into the chat: ' + JSON.stringify(fb); }}
}};
</script></body></html>"""


def serve(board_dir):
    with open(os.path.join(board_dir, "board.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    page = PAGE.format(title=html.escape(spec.get("title", "Board")),
                       question=html.escape(spec.get("question", "")),
                       spec=json.dumps(spec, ensure_ascii=False))
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body, ctype = page.encode("utf-8"), "text/html; charset=utf-8"
            else:
                path = os.path.normpath(os.path.join(board_dir, self.path.lstrip("/")))
                if not path.startswith(os.path.abspath(board_dir)) and \
                        not os.path.abspath(path).startswith(os.path.abspath(board_dir)):
                    self.send_error(403)
                    return
                try:
                    with open(path, "rb") as fh:
                        body = fh.read()
                except OSError:
                    self.send_error(404)
                    return
                ctype = "image/png" if path.lower().endswith(".png") else "image/jpeg"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            data["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
            path = os.path.join(board_dir, "feedback.json")
            try:
                with open(path, encoding="utf-8") as fh:
                    store = json.load(fh)
            except (OSError, json.JSONDecodeError):
                store = {"history": []}
            store["history"].append(data)
            store["latest"] = data
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(store, fh, indent=2, ensure_ascii=False)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            done.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("board open at", url, flush=True)
    webbrowser.open(url)
    done.wait()
    time.sleep(0.5)
    server.shutdown()
    with open(os.path.join(board_dir, "feedback.json"), encoding="utf-8") as fh:
        print("FEEDBACK", json.dumps(json.load(fh)["latest"], ensure_ascii=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("board_dir"); b.add_argument("--title", default="Board")
    b.add_argument("--images", nargs="+", default=[]); b.add_argument("--mode", default="single")
    b.add_argument("--question", default="")
    s = sub.add_parser("serve"); s.add_argument("board_dir")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.board_dir, a.title, a.images, a.mode, a.question)
    else:
        serve(a.board_dir)
