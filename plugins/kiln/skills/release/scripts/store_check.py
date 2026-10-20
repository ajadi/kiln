"""Store and platform checks before a release: Steam capsules and screenshots, Steam Deck text
size, Google Play target API and 16 KB pages, web hosting headers, and a draft of Steam's AI
disclosure. Stdlib, plus Pillow for images.

  python store_check.py capsules store/steam [--screenshots store/steam/screenshots]
                                 [--out production/release/capsules] [--answers review.json]
  python store_check.py deck --scene res://ui/main_menu.tscn [--scene ...] [--min-px 9]
                             [--want-px 12] [--skip REGEX] [--engine-exe PATH]
  python store_check.py android export/android/game.aab|.apk [--min-target 36]
  python store_check.py android                   (Godot project: the Android presets only)
  python store_check.py web export/web [--url https://host/game/]
  python store_check.py ai-disclosure [--out production/release/AI_DISCLOSURE.md]

capsules  Files are named after the asset (header, small, main, vertical, library_capsule,
          library_header, library_hero, library_logo, page_background, community_icon): exact
          size, PNG, the library logo's transparent background, screenshots >= 5 at >= 1920x1080
          16:9. Text beyond the title cannot be measured, so it writes a review pack (each
          capsule, the small capsule at 120x45) with REVIEW.md and review.json; a reviewer
          fills each item's "answer" ({"extra_text": bool, "logo_legible": bool, "evidence":
          "..."}) and --answers turns them into the verdict.
deck      Godot: runs deck_text.gd headless (copied to .kiln/tmp/) on the given scenes. Every
          text Control's size on a 1280x800 screen = font size x canvas scale x the project's
          stretch scale; glyph cap and x heights come from the font file (Pillow), or Open
          Sans ratios for the default font. Fail: a font below --min-px (Valve: the smallest
          character never below 9 px at 1280x800). Warn: below --want-px (Valve recommends
          12 px) or a cap height below --min-px (the strict reading of "character height").
android   APK or AAB: targetSdkVersion from the manifest (binary XML or the bundle's protobuf)
          against --min-target (Google Play: API 36 for new apps and updates from 31 Aug 2026),
          every 64-bit native library (arm64-v8a, x86_64) with ELF LOAD segments aligned to
          16 KB, uncompressed libraries in an APK on 16 KB zip offsets. Without a file: the
          Godot Android presets' target SDK and format.
web       Godot web export: thread support on means the page needs cross-origin isolation
          (Cross-Origin-Opener-Policy: same-origin, Cross-Origin-Embedder-Policy: require-corp
          or credentialless). --url fetches the page and checks the headers and the .wasm MIME
          type; a _headers file in the export is read too.
ai-disclosure  Draft answers for Steam's content survey from every provenance.json (generated
          assets; library assets are skipped), production/ai-content.csv (item,category,tool,
          ships,notes - AI-made text, voices, localisation) and game code that calls a model at
          runtime. The user answers the survey; this is the list they answer from.

Output: JSON with "verdict" (pass | fail | not assessed | draft); exit 1 on fail.
"""

import argparse
import csv
import datetime
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B  # noqa: E402  (engine lookup and Godot config parsing)

HERE = os.path.dirname(os.path.abspath(__file__))


def emit(result):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 1 if result.get("verdict") == "fail" else 0


def pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        raise SystemExit("Pillow is needed: python -m pip install pillow")


# ---------------------------------------------------------------- capsules

# name: (width, height, format, needs review, required)  Steamworks store and library asset pages.
CAPSULES = {
    "header": (920, 430, "PNG", True, True),
    "small": (462, 174, "PNG", True, True),
    "main": (1232, 706, "PNG", True, True),
    "vertical": (748, 896, "PNG", True, True),
    "library_capsule": (600, 900, "PNG", True, True),
    "library_header": (920, 430, "PNG", True, True),
    "library_hero": (3840, 1240, "PNG", True, True),
    "library_logo": (None, None, "PNG", True, True),
    "page_background": (1438, 810, "PNG", False, False),
    "community_icon": (184, 184, "JPEG", False, False),
}
QUESTIONS = {
    "library_hero": "Any text at all? (the hero may carry none; the logo is a separate asset)",
    "library_logo": "Anything besides the logotype and an optional logomark?",
}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def asset_name(path):
    stem = re.sub(r"[^a-z0-9]+", "_", os.path.splitext(os.path.basename(path))[0].lower()).strip("_")
    for name in sorted(CAPSULES, key=len, reverse=True):
        if stem == name or stem.endswith("_" + name) or stem.startswith(name + "_"):
            return name
    return None


def transparent_background(img):
    if img.mode not in ("RGBA", "LA", "PA") and "transparency" not in img.info:
        return False, "no alpha channel"
    alpha = img.convert("RGBA").getchannel("A")
    w, h = alpha.size
    corners = [alpha.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    hist = alpha.histogram()
    clear = sum(hist[:8]) / float(w * h)
    if max(corners) > 8 or clear < 0.2:
        return False, f"corners alpha {corners}, {clear:.0%} of pixels transparent"
    return True, f"{clear:.0%} of pixels transparent"


def cmd_capsules(a):
    Image = pil()
    problems, warnings, assets = [], [], {}
    files = sorted(f for f in glob.glob(os.path.join(a.folder, "*")) if f.lower().endswith(IMAGE_EXT))
    for f in files:
        name = asset_name(f)
        if not name:
            continue
        if name in assets:
            problems.append(f"two files for {name}: {assets[name]['file']} and {f}")
            continue
        w, h, fmt, _, _ = CAPSULES[name]
        img = Image.open(f)
        row = {"file": B.norm(f), "size": list(img.size), "format": img.format}
        if name == "library_logo":
            if not (img.width == 1280 and img.height <= 720) and not (img.height == 720 and img.width <= 1280):
                problems.append(f"{name}: {img.width}x{img.height}, needs 1280 wide and/or 720 tall")
            ok, why = transparent_background(img)
            row["transparent"] = why
            if not ok:
                problems.append(f"{name}: needs a transparent background ({why})")
        elif list(img.size) != [w, h]:
            problems.append(f"{name}: {img.width}x{img.height}, needs {w}x{h}")
        if img.format != fmt:
            problems.append(f"{name}: {img.format}, needs {fmt}")
        assets[name] = row
    for name, spec in CAPSULES.items():
        if spec[4] and name not in assets:
            problems.append(f"{name}: missing (name the file {name}.png)")
    shots = []
    if a.screenshots:
        for f in sorted(glob.glob(os.path.join(a.screenshots, "*"))):
            if not f.lower().endswith(IMAGE_EXT):
                continue
            img = Image.open(f)
            w, h = img.size
            shots.append({"file": B.norm(f), "size": [w, h]})
            if w < 1920 or h < 1080 or abs(w * 9 - h * 16) > w * 9 * 0.01:
                problems.append(f"screenshot {os.path.basename(f)}: {w}x{h}, needs >= 1920x1080 at 16:9")
        if len(shots) < 5:
            problems.append(f"{len(shots)} screenshots, Steam needs at least 5")
    else:
        warnings.append("screenshots not checked (--screenshots <folder>)")

    # the review pack: what a script cannot judge
    out = a.out or os.path.join("production", "release", "capsules")
    os.makedirs(out, exist_ok=True)
    items = []
    for name, row in assets.items():
        if not CAPSULES[name][3]:
            continue
        img = Image.open(row["file"]).convert("RGBA")
        bg = Image.new("RGBA", img.size, (128, 128, 128, 255))
        img = Image.alpha_composite(bg, img).convert("RGB")
        if img.width > 1600:
            img = img.resize((1600, round(img.height * 1600 / img.width)), Image.LANCZOS)
        pack = f"{name}.png"
        img.save(os.path.join(out, pack))
        item = {"asset": name, "file": row["file"], "pack": pack,
                "question": QUESTIONS.get(name, "Any text besides the game's title (quotes, "
                                          "awards, review scores, 'out now', prices, platforms)? "
                                          "Is the logotype easy to read against the background?"),
                "answer": None}
        if name == "small":
            tiny = Image.open(row["file"]).convert("RGB").resize((120, 45), Image.LANCZOS)
            tiny.resize((360, 135), Image.NEAREST).save(os.path.join(out, "small_120x45.png"))
            item["pack_small"] = "small_120x45.png"
            item["question"] += " Is the logo still readable at 120x45 (small_120x45.png, x3)?"
        items.append(item)
    review = os.path.join(out, "review.json")
    with open(review, "w", encoding="utf-8") as fh:
        json.dump({"items": items}, fh, indent=1)
    lines = ["# Steam capsule review", "",
             "Steam: no quotes or other text beyond the game's title on capsules; the hero has no "
             "text; the small capsule's logo stays readable at its smallest size. For each item "
             "look at the image and fill its \"answer\" in review.json: "
             '{"extra_text": true|false, "logo_legible": true|false, "evidence": "what you see"}. '
             "Describe what is on the image before you answer.", ""]
    lines += [f"- `{i['pack']}` ({i['asset']}): {i['question']}" for i in items]
    with open(os.path.join(out, "REVIEW.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    unanswered = []
    if a.answers:
        with open(a.answers, encoding="utf-8") as fh:
            answered = {i["asset"]: i.get("answer") for i in json.load(fh).get("items", [])}
        for i in items:
            ans = answered.get(i["asset"])
            if not isinstance(ans, dict):
                unanswered.append(i["asset"])
                continue
            if ans.get("extra_text"):
                problems.append(f"{i['asset']}: text beyond the title - {ans.get('evidence', '')}")
            if ans.get("logo_legible") is False:
                problems.append(f"{i['asset']}: logo not legible - {ans.get('evidence', '')}")
    verdict = "fail" if problems else ("pass" if a.answers and not unanswered else "not assessed")
    if not a.answers and not problems:
        warnings.append(f"sizes pass; text rules wait for the review: {B.norm(review)}")
    return emit({"command": "capsules", "assets": assets, "screenshots": len(shots),
                 "review": B.norm(review), "unanswered": unanswered, "problems": problems,
                 "warnings": warnings, "verdict": verdict})


# ---------------------------------------------------------------- deck

# Open Sans (Godot 4's default font): capHeight 1462, xHeight 1096, unitsPerEm 2048.
DEFAULT_RATIOS = (1462 / 2048, 1096 / 2048)


def glyph_ratios(font, cache={}):
    """(cap height, x height) per pixel of font size, and where the numbers came from."""
    if font in cache:
        return cache[font]
    result = (DEFAULT_RATIOS, "Open Sans ratios (default font)")
    if font != "default":
        result = (DEFAULT_RATIOS, f"Open Sans ratios ({font} not measurable)")
        if os.path.isfile(font):
            try:
                from PIL import ImageFont
                f = ImageFont.truetype(font, 200)
                cap, x = f.getbbox("H"), f.getbbox("x")
                result = (((cap[3] - cap[1]) / 200.0, (x[3] - x[1]) / 200.0), "measured")
            except (OSError, ImportError) as exc:
                result = (DEFAULT_RATIOS, f"Open Sans ratios ({exc})")
    cache[font] = result
    return result


def cmd_deck(a):
    root = os.path.abspath(a.root)
    manifest = B.read_manifest(root)
    engine = B.detect_engine(root, manifest)
    if engine != "godot":
        return emit({"command": "deck", "verdict": "not assessed",
                     "problems": [f"engine {engine}: only Godot is measured; check a 1280x800 "
                                  "capture by eye (smallest letter >= 9 px)"]})
    exe, source = B.engine_exe("godot", root, manifest, a)
    if not exe:
        raise SystemExit("godot_exe not found (--engine-exe, $KILN_ENGINE_EXE, machine.json, PATH)")
    tmp = os.path.join(root, ".kiln", "tmp")
    os.makedirs(tmp, exist_ok=True)
    shutil.copy(os.path.join(HERE, "deck_text.gd"), os.path.join(tmp, "deck_text.gd"))
    out = os.path.join(tmp, "deck_text.json")
    if os.path.exists(out):
        os.remove(out)
    cmd = [exe, "--headless", "--path", root, "-s", "res://.kiln/tmp/deck_text.gd", "--"]
    for s in a.scene:
        cmd += ["--scene", s]
    cmd += ["--out", out, "--width", str(a.width), "--height", str(a.height)]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=a.timeout)
    if not os.path.isfile(out):
        return emit({"command": "deck", "verdict": "fail", "exit_code": p.returncode,
                     "problems": ["deck_text.gd wrote nothing"], "log": B.tail(p.stdout + p.stderr)})
    with open(out, encoding="utf-8") as fh:
        data = json.load(fh)
    problems, warnings, rows = [], [], []
    for r in data["rows"]:
        if a.skip and re.search(a.skip, r["scene"] + ":" + r["node"]):
            continue
        (cap, xh), how = glyph_ratios(r["font"])
        r.update({"px": round(r["px"], 2), "cap_px": round(r["px"] * cap, 2),
                  "x_px": round(r["px"] * xh, 2), "glyphs": how})
        rows.append(r)
        where = f"{r['scene']}:{r['node']} \"{r['text']}\" ({r['source']} {r['font_size']})"
        if r["px"] < a.min_px:
            problems.append(f"{where}: {r['px']} px at {a.width}x{a.height}, minimum {a.min_px}")
        elif r["cap_px"] < a.min_px:
            warnings.append(f"{where}: {r['px']} px, capital letters {r['cap_px']} px tall")
        elif r["px"] < a.want_px:
            warnings.append(f"{where}: {r['px']} px, Valve recommends {a.want_px}")
    for m in data.get("missing", []):
        problems.append(f"{m}: scene did not load")
    if data.get("label3d"):
        warnings.append(f"{data['label3d']} Label3D nodes: world-space text, check a capture")
    if not rows and not problems:
        problems.append("no text Controls found in the scenes")
    smallest = sorted(rows, key=lambda r: r["px"])[:10]
    return emit({"command": "deck", "screen": data["screen"], "stretch_scale": data["stretch_scale"],
                 "texts": len(rows), "smallest": smallest, "problems": problems,
                 "warnings": warnings, "verdict": "fail" if problems else "pass"})


# ---------------------------------------------------------------- android

RES_IDS = {0x01010270: "targetSdkVersion", 0x0101020c: "minSdkVersion",
           0x010104ea: "extractNativeLibs"}
PAGE_16K = 0x4000
ABI_64 = ("arm64-v8a", "x86_64")


def axml_strings(d, off):
    count, _, flags, start = struct.unpack_from("<IIII", d, off + 8)
    out = []
    for i in range(count):
        p = off + start + struct.unpack_from("<I", d, off + 28 + 4 * i)[0]
        if flags & 0x100:  # UTF-8: char count, byte count, bytes
            p += 2 if d[p] & 0x80 else 1
            n = d[p]
            if n & 0x80:
                n = ((n & 0x7F) << 8) | d[p + 1]
                p += 2
            else:
                p += 1
            out.append(d[p:p + n].decode("utf-8", "replace"))
        else:
            n = struct.unpack_from("<H", d, p)[0]
            p += 2
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", d, p)[0]
                p += 2
            out.append(d[p:p + 2 * n].decode("utf-16-le", "replace"))
    return out


def axml_manifest(d):
    """Android binary XML (an APK's AndroidManifest.xml) -> {element.attribute: int}."""
    pos, pool, resmap, res = 8, [], [], {}
    while pos + 8 <= len(d):
        kind, _, size = struct.unpack_from("<HHI", d, pos)
        if size <= 0:
            break
        if kind == 0x0001:
            pool = axml_strings(d, pos)
        elif kind == 0x0180:
            resmap = list(struct.unpack_from(f"<{(size - 8) // 4}I", d, pos + 8))
        elif kind == 0x0102:
            element = pool[struct.unpack_from("<I", d, pos + 20)[0]]
            astart, asize, acount = struct.unpack_from("<HHH", d, pos + 24)
            for k in range(acount):
                _, name, _, _, _, _, data = struct.unpack_from("<IIIHBBI", d, pos + 16 + astart + k * asize)
                key = RES_IDS.get(resmap[name]) if name < len(resmap) else None
                key = key or (pool[name] if name < len(pool) else "")
                if key in RES_IDS.values():
                    res[f"{element}.{key}"] = data - (1 << 32) if data >= 1 << 31 else data
        pos += size
    return res


def pb_fields(d):
    """Protocol buffer bytes -> [(field, wire type, value)], or None when they are not a message."""
    out, i = [], 0
    try:
        while i < len(d):
            key, i = pb_varint(d, i)
            field, wire = key >> 3, key & 7
            if field == 0:
                return None
            if wire == 0:
                value, i = pb_varint(d, i)
            elif wire == 2:
                n, i = pb_varint(d, i)
                if i + n > len(d):
                    return None
                value, i = d[i:i + n], i + n
            elif wire == 5:
                value, i = d[i:i + 4], i + 4
            elif wire == 1:
                value, i = d[i:i + 8], i + 8
            else:
                return None
            out.append((field, wire, value))
    except IndexError:
        return None
    return out if i == len(d) else None


def pb_varint(d, i):
    shift = value = 0
    while True:
        b = d[i]
        i += 1
        value |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return value, i


def pb_manifest(d, res=None, depth=0):
    """An AAB's base/manifest/AndroidManifest.xml (aapt2 XmlNode protobuf): XmlAttribute has
    name = 2, value = 3, resource_id = 5, compiled_item = 6 (Item.prim = 7, int_decimal = 6)."""
    res = {} if res is None else res
    fields = pb_fields(d) if depth < 12 else None
    if not fields:
        return res
    by = {}
    for f, w, v in fields:
        by.setdefault(f, []).append((w, v))
    name = by.get(2, [(None, None)])[0][1]
    rid = by.get(5, [(None, None)])[0][1]
    key = RES_IDS.get(rid) if isinstance(rid, int) else None
    if not key and isinstance(name, bytes) and name.decode("utf-8", "replace") in RES_IDS.values():
        key = name.decode("utf-8")
    if key:
        value = by.get(3, [(None, b"")])[0][1]
        try:
            res[key] = int(value.decode("utf-8")) if value else None
        except ValueError:
            res[key] = value.decode("utf-8", "replace") == "true"
        if res[key] is None:
            item = pb_fields(by.get(6, [(None, b"")])[0][1]) or []
            prim = next((pb_fields(v) for f, w, v in item if f == 7 and w == 2), None) or []
            res[key] = next((v for f, w, v in prim if w == 0), None)
        return res
    for f, w, v in fields:
        if w == 2 and len(v) > 1:
            pb_manifest(v, res, depth + 1)
    return res


def elf_load_aligns(d):
    """p_align of every PT_LOAD segment, and whether the file is 64-bit."""
    if d[:4] != b"\x7fELF":
        return None, None
    is64, end = d[4] == 2, "<" if d[5] == 1 else ">"
    if is64:
        phoff = struct.unpack_from(end + "Q", d, 0x20)[0]
        size, count = struct.unpack_from(end + "HH", d, 0x36)
        fmt, at = end + "Q", 48
    else:
        phoff = struct.unpack_from(end + "I", d, 0x1C)[0]
        size, count = struct.unpack_from(end + "HH", d, 0x2A)
        fmt, at = end + "I", 28
    aligns = []
    for k in range(count):
        o = phoff + k * size
        if struct.unpack_from(end + "I", d, o)[0] == 1:
            aligns.append(struct.unpack_from(fmt, d, o + at)[0])
    return aligns, is64


def zip_data_offset(z, info):
    z.fp.seek(info.header_offset)
    head = z.fp.read(30)
    name_len, extra_len = struct.unpack_from("<HH", head, 26)
    return info.header_offset + 30 + name_len + extra_len


def android_presets(root, a):
    presets = [p for p in B.godot_presets(root) if "android" in str(p.get("platform", "")).lower()]
    problems, warnings, rows = [], [], []
    for p in presets:
        o = p["_options"]
        target = str(o.get("gradle_build/target_sdk", "") or "").strip()
        fmt = "aab" if str(o.get("gradle_build/export_format", 0)) == "1" else "apk"
        rows.append({"preset": p.get("name"), "target_sdk": target or "template default",
                     "format": fmt, "gradle": bool(o.get("gradle_build/use_gradle_build"))})
        if target.isdigit() and int(target) < a.min_target:
            problems.append(f"preset {p.get('name')}: target SDK {target} < {a.min_target}")
        if fmt != "aab":
            warnings.append(f"preset {p.get('name')}: exports an APK; Google Play takes an AAB "
                            "(gradle build, export format AAB)")
    if not presets:
        problems.append("no Android preset in export_presets.cfg")
    warnings.append("the template's default target SDK is only known from a built file: run "
                    "android <export>.aab")
    return rows, problems, warnings


def cmd_android(a):
    if not a.file:
        rows, problems, warnings = android_presets(os.path.abspath(a.root), a)
        return emit({"command": "android", "presets": rows, "problems": problems,
                     "warnings": warnings, "verdict": "fail" if problems else "not assessed"})
    problems, warnings, libs = [], [], []
    is_aab = a.file.lower().endswith(".aab")
    with zipfile.ZipFile(a.file) as z:
        names = z.namelist()
        if is_aab:
            mpath = next((n for n in names if n.endswith("manifest/AndroidManifest.xml")
                          and n.startswith("base/")), None)
            manifest = pb_manifest(z.read(mpath)) if mpath else {}
            manifest = {f"uses-sdk.{k}" if k != "extractNativeLibs" else f"application.{k}": v
                        for k, v in manifest.items()}
        else:
            manifest = axml_manifest(z.read("AndroidManifest.xml")) if "AndroidManifest.xml" in names else {}
            warnings.append("an APK: Google Play takes an AAB for new apps (APK is fine for "
                            "itch.io and sideloading)")
        target = manifest.get("uses-sdk.targetSdkVersion")
        if target is None:
            problems.append("no targetSdkVersion in the manifest")
        elif target < a.min_target:
            problems.append(f"targetSdkVersion {target} < {a.min_target} (Google Play)")
        for info in z.infolist():
            m = re.match(r"(?:base/)?lib/([^/]+)/[^/]+\.so$", info.filename)
            if not m:
                continue
            abi = m.group(1)
            aligns, is64 = elf_load_aligns(z.read(info.filename))
            row = {"lib": info.filename, "abi": abi, "load_align": [hex(x) for x in aligns or []],
                   "compressed": info.compress_type != zipfile.ZIP_STORED}
            libs.append(row)
            if aligns is None:
                problems.append(f"{info.filename}: not an ELF file")
                continue
            if abi in ABI_64 and min(aligns or [0]) < PAGE_16K:
                problems.append(f"{info.filename}: LOAD segments aligned to {hex(min(aligns))}, "
                                "16 KB devices need 0x4000 (relink with -Wl,-z,max-page-size=16384)")
            if not is_aab and not row["compressed"] and abi in ABI_64:
                off = zip_data_offset(z, info)
                row["zip_offset"] = off
                if off % PAGE_16K:
                    problems.append(f"{info.filename}: stored uncompressed at zip offset {off}, "
                                    "not 16 KB aligned (zipalign -P 16)")
    if not any(r["abi"] in ABI_64 for r in libs):
        warnings.append("no 64-bit native libraries")
    return emit({"command": "android", "file": B.norm(a.file), "manifest": manifest,
                 "libs": libs, "problems": problems, "warnings": warnings,
                 "verdict": "fail" if problems else "pass"})


# ---------------------------------------------------------------- web

def godot_web_page(folder):
    pages = [folder] if os.path.isfile(folder) else glob.glob(os.path.join(folder, "*.html"))
    for page in pages:
        text = B.read_text(page)
        m = re.search(r"const GODOT_THREADS_ENABLED\s*=\s*(true|false)", text)
        if m:
            conf = re.search(r"const GODOT_CONFIG\s*=\s*(\{.*?\});", text, re.S)
            try:
                config = json.loads(conf.group(1)) if conf else {}
            except ValueError:
                config = {}
            return page, m.group(1) == "true", config
    return None, None, None


def isolation_problems(headers):
    coop = (headers.get("cross-origin-opener-policy") or "").split(";")[0].strip().lower()
    coep = (headers.get("cross-origin-embedder-policy") or "").split(";")[0].strip().lower()
    out = []
    if coop != "same-origin":
        out.append(f"Cross-Origin-Opener-Policy is '{coop or 'missing'}', needs same-origin")
    if coep not in ("require-corp", "credentialless"):
        out.append(f"Cross-Origin-Embedder-Policy is '{coep or 'missing'}', needs require-corp "
                   "(or credentialless)")
    return out


def headers_file(folder):
    """Netlify / Cloudflare Pages _headers: {path pattern: {header: value}}."""
    path = os.path.join(folder, "_headers")
    rules, current = {}, None
    for line in B.read_text(path).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            current = rules.setdefault(line.strip(), {})
        elif current is not None and ":" in line:
            k, v = line.split(":", 1)
            current[k.strip().lower()] = v.strip()
    return rules if os.path.isfile(path) else None


def fetch_headers(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "kiln-store-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return {k.lower(): v for k, v in r.headers.items()}


def cmd_web(a):
    folder = a.folder if os.path.isdir(a.folder) else os.path.dirname(a.folder)
    page, threads, config = godot_web_page(a.folder)
    if page is None:
        return emit({"command": "web", "verdict": "not assessed",
                     "problems": ["no Godot web export page (GODOT_THREADS_ENABLED) found"]})
    problems, warnings = [], []
    result = {"command": "web", "page": B.norm(page), "threads": threads,
              "pwa_isolation": bool(config.get("serviceWorker") and
                                    config.get("ensureCrossOriginIsolationHeaders"))}
    if not threads:
        warnings.append("single-threaded export: no COOP/COEP needed, runs on any static host "
                        "and in portal iframes")
    else:
        rules = headers_file(folder)
        if rules is not None:
            merged = {}
            for pattern, values in rules.items():
                if pattern in ("/*", "/", "/" + os.path.basename(page)) or pattern.endswith("/*"):
                    merged.update(values)
            result["_headers"] = isolation_problems(merged) or "sets COOP/COEP"
            if result["_headers"] != "sets COOP/COEP":
                problems += [f"_headers: {p}" for p in result["_headers"]]
        if result["pwa_isolation"]:
            warnings.append("the PWA service worker adds the headers after the first load (one "
                            "automatic reload); it cannot help inside a third-party iframe")
        if not a.url:
            warnings.append("thread support on: the host must send COOP same-origin and COEP "
                            "require-corp; itch.io: tick 'SharedArrayBuffer support'; check the "
                            "live page with --url")
    if a.url:
        try:
            headers = fetch_headers(a.url)
            result["headers"] = {k: headers.get(k) for k in ("cross-origin-opener-policy",
                                                             "cross-origin-embedder-policy")}
            if threads:
                problems += [f"{a.url}: {p}" for p in isolation_problems(headers)]
            base = a.url if a.url.endswith("/") else a.url.rsplit("/", 1)[0] + "/"
            wasm = sorted(glob.glob(os.path.join(folder, "*.wasm")))
            if wasm:
                wh = fetch_headers(base + os.path.basename(wasm[0]), "HEAD")
                result["wasm_type"] = wh.get("content-type")
                if not (wh.get("content-type") or "").startswith("application/wasm"):
                    warnings.append(f"{os.path.basename(wasm[0])} served as "
                                    f"'{wh.get('content-type')}', browsers compile faster from "
                                    "application/wasm")
        except (urllib.error.URLError, OSError) as exc:
            problems.append(f"{a.url}: {exc}")
    elif threads:
        result["verdict_note"] = "headers not checked on a host"
    result.update({"problems": problems, "warnings": warnings,
                   "verdict": "fail" if problems else
                   ("pass" if not threads or a.url else "not assessed")})
    return emit(result)


# ---------------------------------------------------------------- ai-disclosure

CATEGORIES = [((".glb", ".gltf", ".fbx", ".obj", ".blend", ".usd", ".usdz"), "3D models"),
              ((".png", ".jpg", ".jpeg", ".webp", ".exr", ".tga", ".svg"), "images and textures"),
              ((".wav", ".ogg", ".mp3", ".flac", ".opus"), "sound and music"),
              ((".mp4", ".webm", ".mov", ".ogv"), "video"),
              ((".txt", ".md", ".json", ".csv", ".po", ".pot", ".yaml"), "text")]
LIVE_PATTERNS = [r"/v1/chat/completions", r"/v1/messages\b", r"api\.openai\.com",
                 r"api\.anthropic\.com", r"generativelanguage\.googleapis\.com",
                 r"localhost:11434|127\.0\.0\.1:11434|/api/generate", r"\bollama\b",
                 r"api\.elevenlabs\.io", r"api\.stability\.ai", r"api\.replicate\.com",
                 r"open-llm-npc|:8100/", r"\bllama\.cpp\b|\bLlamaCpp\b"]
CODE_EXT = (".gd", ".cs", ".cpp", ".h", ".hpp", ".c", ".gdshader", ".tscn", ".tres", ".json",
            ".cfg", ".ini", ".js", ".ts", ".lua")


def category(files):
    seen = []
    for f in files:
        for exts, name in CATEGORIES:
            if f.lower().endswith(exts) and name not in seen:
                seen.append(name)
    return seen or ["other"]


def ships(rel):
    top = rel.replace("\\", "/").split("/")[0]
    return top not in B.NON_SHIPPING and top != "export"


def walk_files(root, exts):
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if name.lower().endswith(exts):
                yield os.path.join(dirpath, name)


SKIP_DIRS = {"Library", "Temp", "Obj", "Logs", "Intermediate", "Saved", "DerivedDataCache",
             "Binaries", "node_modules", "__pycache__", "export", "addons"}


def cmd_ai_disclosure(a):
    root = os.path.abspath(a.root)
    items = []
    for path in walk_files(root, ("provenance.json",)):
        try:
            with open(path, encoding="utf-8") as fh:
                p = json.load(fh)
        except (OSError, ValueError):
            continue
        if p.get("kind") == "library" or p.get("ai_generated") is False:
            continue
        folder = os.path.relpath(os.path.dirname(path), root).replace("\\", "/")
        outs = [o.get("file", "") if isinstance(o, dict) else str(o) for o in p.get("outputs", [])]
        if not outs:
            outs = [f for f in os.listdir(os.path.dirname(path)) if f != "provenance.json"]
        tool = " ".join(str(x) for x in (p.get("service") or p.get("tool") or "unknown tool",
                                         p.get("version", "")) if x).strip()
        items.append({"item": folder, "category": ", ".join(category(outs)), "tool": tool,
                      "ships": ships(folder), "source": "provenance.json",
                      "prompt": (p.get("prompt") or "")[:80]})
    extra = os.path.join(root, "production", "ai-content.csv")
    if os.path.isfile(extra):
        with open(extra, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                items.append({"item": r.get("item", "?"), "category": r.get("category", "other"),
                              "tool": r.get("tool", "?"),
                              "ships": (r.get("ships") or "yes").strip().lower() != "no",
                              "source": "ai-content.csv", "prompt": r.get("notes", "")})
    live = []
    rx = re.compile("|".join(LIVE_PATTERNS), re.I)
    for path in walk_files(root, CODE_EXT):
        rel = os.path.relpath(path, root).replace("\\", "/")
        if not ships(rel):
            continue
        for n, line in enumerate(B.read_text(path, 2_000_000).splitlines(), 1):
            if rx.search(line):
                live.append({"file": rel, "line": n, "text": line.strip()[:100]})
                break
    shipping = [i for i in items if i["ships"]]
    by_cat = {}
    for i in shipping:
        for c in i["category"].split(", "):
            by_cat.setdefault(c, set()).add(i["tool"])
    out = a.out or os.path.join(root, "production", "release", "AI_DISCLOSURE.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    lines = ["# Steam AI disclosure - draft", "",
             f"Generated by store_check.py ai-disclosure on {datetime.date.today().isoformat()}. "
             "The user answers Steam's content survey; this is the list to answer from. Steam asks "
             "about AI-made content players see or hear, not about tools that only made the work "
             "faster (code assistants, editor helpers).", "",
             "## Pre-generated content (made with AI during development, ships in the game)", ""]
    if by_cat:
        lines += [f"- {c}: {len([i for i in shipping if c in i['category']])} items - "
                  f"{', '.join(sorted(t))}" for c, t in sorted(by_cat.items())]
        lines += ["", "Draft answer (edit before pasting; say how people reviewed or changed the "
                  "output):", "",
                  "> " + "; ".join(f"{c} were generated with {', '.join(sorted(t))}"
                                   for c, t in sorted(by_cat.items())) +
                  ". <how the team reviewed, edited or replaced them>"]
    else:
        lines.append("- none found (no provenance.json of generated assets, no "
                     "production/ai-content.csv rows)")
    lines += ["", "## Live-generated content (made by AI while the game runs)", ""]
    if live:
        lines += [f"- `{l['file']}:{l['line']}` {l['text']}" for l in live]
        lines += ["", "If the game generates content at runtime, Steam asks what guardrails stop "
                  "illegal or infringing output; live-generated adult sexual content is not "
                  "allowed. Describe the guardrails here: <...>"]
    else:
        lines.append("- no runtime model calls found in the shipping code")
    lines += ["", "## Items", "", "| item | category | tool | ships | source |", "|---|---|---|---|---|"]
    lines += [f"| {i['item']} | {i['category']} | {i['tool']} | {'yes' if i['ships'] else 'no'} | "
              f"{i['source']} |" for i in items]
    lines += ["", "Not in this list: AI-made text, voices or translations without a provenance "
              "file - add them to production/ai-content.csv (item,category,tool,ships,notes)."]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return emit({"command": "ai-disclosure", "out": B.norm(os.path.relpath(out, root)),
                 "pre_generated": {c: sorted(t) for c, t in by_cat.items()},
                 "items": len(items), "shipping": len(shipping), "live_candidates": live,
                 "verdict": "draft"})


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("capsules")
    p.add_argument("folder")
    p.add_argument("--screenshots")
    p.add_argument("--out")
    p.add_argument("--answers")
    p = sub.add_parser("deck")
    p.add_argument("--root", default=".")
    p.add_argument("--scene", action="append", required=True, help="res:// path, repeatable")
    p.add_argument("--min-px", type=float, default=9)
    p.add_argument("--want-px", type=float, default=12)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=800)
    p.add_argument("--skip", help="regex on scene:node to leave out (debug overlays)")
    p.add_argument("--engine-exe")
    p.add_argument("--machine")
    p.add_argument("--timeout", type=float, default=300)
    p = sub.add_parser("android")
    p.add_argument("file", nargs="?")
    p.add_argument("--root", default=".")
    p.add_argument("--min-target", type=int, default=36)
    p = sub.add_parser("web")
    p.add_argument("folder")
    p.add_argument("--url")
    p = sub.add_parser("ai-disclosure")
    p.add_argument("--root", default=".")
    p.add_argument("--out")
    a = parser.parse_args(argv)
    return {"capsules": cmd_capsules, "deck": cmd_deck, "android": cmd_android, "web": cmd_web,
            "ai-disclosure": cmd_ai_disclosure}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
