"""Collect reference images into a curated folder with provenance, and extract palettes.

  python refs_fetch.py fetch <refs_dir> <urls.txt>
      urls.txt lines: <image or page url> | <credit/source page> | <license or 'reference only'> | <note>
      Page URLs are resolved through their og:image. Images are verified by signature,
      downscaled to 1600 px, deduplicated by sha1, and recorded in <refs_dir>/sources.json.
  python refs_fetch.py note <refs_dir> <file> "<what to take from it>"
  python refs_fetch.py drop <refs_dir> <file> "<why>"      # removes and blacklists the URL
  python refs_fetch.py palette <refs_dir> [--liked feedback.json] [--colors 8]
      dominant colours (hex, share) from all or liked images — for the art bible.

References are for study only: they never ship in the game.
"""

import hashlib
import io
import json
import os
import re
import sys
import urllib.request

from PIL import Image

UA = {"User-Agent": "Mozilla/5.0 (kiln reference collector)"}
SIGNATURES = (b"\x89PNG", b"\xff\xd8\xff", b"RIFF", b"GIF8")


def load_sources(refs_dir):
    path = os.path.join(refs_dir, "sources.json")
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": [], "blacklist": []}


def save_sources(refs_dir, data):
    with open(os.path.join(refs_dir, "sources.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def fetch(refs_dir, list_path):
    os.makedirs(refs_dir, exist_ok=True)
    data = load_sources(refs_dir)
    known = {i["sha1"] for i in data["items"]} | set(data["blacklist"])
    for raw in open(list_path, encoding="utf-8"):
        parts = [p.strip() for p in raw.split("|")]
        if not parts[0] or parts[0].startswith("#"):
            continue
        url, credit, license_, note = (parts + ["", "", "", ""])[:4]
        if url in data["blacklist"]:
            continue
        try:
            body, ctype = get(url)
            if not body.startswith(SIGNATURES):
                m = re.search(rb'property=["\']og:image["\']\s+content=["\']([^"\']+)', body) or \
                    re.search(rb'content=["\']([^"\']+)["\']\s+property=["\']og:image', body)
                if not m:
                    print("skip (no image):", url)
                    continue
                body, ctype = get(m.group(1).decode())
            if not body.startswith(SIGNATURES):
                print("skip (not an image):", url)
                continue
            sha = hashlib.sha1(body).hexdigest()
            if sha in known:
                continue
            img = Image.open(io.BytesIO(body)).convert("RGB")
            img.thumbnail((1600, 1600), Image.LANCZOS)
            name = f"{len(data['items']) + 1:03d}_{sha[:8]}.jpg"
            img.save(os.path.join(refs_dir, name), "JPEG", quality=90)
            data["items"].append({"file": name, "url": url, "credit": credit or url,
                                  "license": license_ or "reference only", "note": note,
                                  "sha1": sha})
            known.add(sha)
            print("saved", name, "←", url)
        except Exception as exc:  # network errors are expected; keep going
            print("fail", url, exc)
    save_sources(refs_dir, data)


def note(refs_dir, file, text):
    data = load_sources(refs_dir)
    for item in data["items"]:
        if item["file"] == file:
            item["note"] = text
    save_sources(refs_dir, data)


def drop(refs_dir, file, why):
    data = load_sources(refs_dir)
    for item in list(data["items"]):
        if item["file"] == file:
            data["items"].remove(item)
            data["blacklist"].append(item["url"])
            data["blacklist"].append(item["sha1"])
            try:
                os.remove(os.path.join(refs_dir, file))
            except OSError:
                pass
            print("dropped", file, "—", why)
    save_sources(refs_dir, data)


def palette(refs_dir, liked_path, colors):
    files = [i["file"] for i in load_sources(refs_dir)["items"]]
    if liked_path:
        liked = json.load(open(liked_path, encoding="utf-8"))["latest"].get("liked", [])
        # board.py copies images as img/<group>_<name>; strip the group prefix to match
        names = {re.sub(r"^\d+_", "", os.path.basename(p)) for p in liked}
        chosen = [f for f in files if f in names]
        if not chosen:
            sys.exit(f"none of the {len(liked)} liked images is in {refs_dir}/sources.json — "
                     "pass the refs folder the board was built from")
        files = chosen
    pixels = Image.new("RGB", (256, 256 * max(1, len(files))))
    for n, f in enumerate(files):
        img = Image.open(os.path.join(refs_dir, f)).convert("RGB").resize((256, 256))
        pixels.paste(img, (0, 256 * n))
    quant = pixels.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    pal = quant.getpalette()[: colors * 3]
    counts = sorted(quant.getcolors(), reverse=True)
    total = sum(c for c, _ in counts)
    for c, idx in counts:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        print(f"#{r:02x}{g:02x}{b:02x}  {100 * c / total:5.1f}%")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fetch":
        fetch(sys.argv[2], sys.argv[3])
    elif cmd == "note":
        note(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "drop":
        drop(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "palette":
        liked = sys.argv[sys.argv.index("--liked") + 1] if "--liked" in sys.argv else None
        n = int(sys.argv[sys.argv.index("--colors") + 1]) if "--colors" in sys.argv else 8
        palette(sys.argv[2], liked, n)
    else:
        print(__doc__)
