"""Free asset libraries: search, read the licence from the item, download with provenance.
Stdlib only.

  python assets_api.py sources
  python assets_api.py search <source|all> "<query>" --kind hdri|texture|model|sprite|ui|audio|icon|font [--limit 12]
  python assets_api.py info <source> <id>
  python assets_api.py fetch <source> <id> [--res 2k] [--format gltf] [--only name,name] [--into art/library]
  python assets_api.py import <folder> --source <name> --id <id> --url <page> [--licence <id>]
                       [--author ...] [--title ...] [--attribution ...]   # files the user downloaded

Run from the project root. Sources (no key, no account; checked 2026-10-19):
  polyhaven    api.polyhaven.com - HDRIs, PBR textures, models; CC0 for every asset
  ambientcg    ambientcg.com/api/v3 - PBR materials, HDRIs, models; CC0 for every asset
  kenney       kenney.nl pack pages and zips - 2D, 3D, UI, audio, textures; CC0, checked in the
               pack's License.txt
  kaykit       KayKit packs on GitHub (Kay Lousberg) - low-poly 3D; CC0, checked in LICENSE.txt
  gameicons    game-icons.net on GitHub - SVG icons; CC BY 3.0, some authors CC0 (license.txt)
  googlefonts  Google Fonts (GitHub google/fonts) - OFL / Apache / UFL from METADATA.pb
The licence is read from the item and checked against the project's allow-list (manifest
`asset_libraries`: off | cc0 | attribution | sharealike, default attribution); anything else is
never downloaded. Files land in art/library/<source>/<id>/ with provenance.json (kind "library")
and evidence/ (the item's record, the pack's licence file); then licenses.py rebuilds
production/LICENSES.md and CREDITS.md. A download is assembled in <id>.part and kept only when
every check passed. GitHub's API allows 60 calls an hour without a token: listings are cached
for a day in .kiln/cache/assets_api/.
KILN_ASSETS_FAKE=http://127.0.0.1:<port> sends every request to a local fake (tests).
"""

import argparse
import datetime
import hashlib
import html
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

FAKE = os.environ.get("KILN_ASSETS_FAKE", "")
UA = "Kiln/0.9 (+https://github.com/ajadi/kiln)"  # Poly Haven API terms 2.4: a unique User-Agent
CC0 = "CC0-1.0"
FONTS = {"OFL-1.1", "Apache-2.0", "LicenseRef-UFL-1.0"}
CUSTOM = {"LicenseRef-Quaternius-QAL-1.0", "LicenseRef-Sonniss-GDC-2.0", "LicenseRef-Pixabay"}
TIERS = {"off": set(), "cc0": {CC0},
         "attribution": {CC0, "CC-BY-3.0", "CC-BY-4.0"} | FONTS,
         "sharealike": {CC0, "CC-BY-3.0", "CC-BY-4.0", "CC-BY-SA-3.0", "CC-BY-SA-4.0"} | FONTS | CUSTOM}
LICENCE_URLS = {
    CC0: "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-3.0": "https://creativecommons.org/licenses/by/3.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC-BY-SA-3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC-BY-SA-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "OFL-1.1": "https://openfontlicense.org/",
    "Apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0",
    "LicenseRef-UFL-1.0": "https://ubuntu.com/legal/font-licence",
    "LicenseRef-Quaternius-QAL-1.0": "https://quaternius.com/license.html"}
CC0_TEXT = re.compile(r"creative commons zero|\bcc0\b|publicdomain/zero", re.I)
CACHE_S = 86400


# --- http ---------------------------------------------------------------------------------------

def fetch_bytes(url, timeout=120):
    if FAKE:
        url = re.sub(r"^https?://[^/]+", FAKE.rstrip("/"), url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_json(url):
    return json.loads(fetch_bytes(url, 60) or b"{}")


def cached(url, root=None, parse=json.loads):
    """A listing that changes slowly (GitHub trees, the fonts list): kept a day per project."""
    folder = os.path.join(root or os.getcwd(), ".kiln", "cache", "assets_api")
    path = os.path.join(folder, hashlib.sha1(url.encode()).hexdigest() + ".json")
    if not FAKE and os.path.isfile(path) and time.time() - os.path.getmtime(path) < CACHE_S:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    try:
        raw = fetch_bytes(url, 120)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and "api.github.com" in url:
            raise SystemExit("GitHub's limit of 60 calls an hour without a token is used up; "
                             "try again within the hour (listings are cached for a day)")
        raise
    data = parse(raw.decode("utf-8"))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data


def words_of(query):
    return [w for w in re.split(r"[\s,]+", query.lower()) if w]


def score(text, words):
    text = text.lower()
    return sum(w in text for w in words)


def git_blob_sha(data):
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


# --- sources ------------------------------------------------------------------------------------

class PolyHaven:
    name = "polyhaven"
    api = "https://api.polyhaven.com"
    kinds = {"hdri": "hdris", "texture": "textures", "model": "models"}
    terms = "https://polyhaven.com/license (CC0); API terms https://polyhaven.com/our-api"
    thanks = "Poly Haven (polyhaven.com)"

    def search(self, query, kind, limit, root):
        data = fetch_json(f"{self.api}/assets?type={self.kinds[kind]}")
        words = words_of(query)
        hits = []
        for aid, a in data.items():
            s = score(" ".join([aid, a.get("name", ""), " ".join(a.get("tags", [])),
                                " ".join(a.get("categories", []))]), words)
            if s:
                hits.append((s, a.get("download_count", 0), aid, a))
        hits.sort(key=lambda h: (-h[0], -h[1]))
        return [{"source": self.name, "id": aid, "title": a.get("name"), "kind": kind,
                 "licence": CC0, "preview": a.get("thumbnail_url"),
                 "page": f"https://polyhaven.com/a/{aid}"} for _, _, aid, a in hits[:limit]]

    def info(self, aid, root):
        a = fetch_json(f"{self.api}/info/{urllib.parse.quote(aid)}")
        if not a or "name" not in a:
            raise SystemExit(f"polyhaven has no asset {aid}")
        kind = {0: "hdri", 1: "texture", 2: "model"}.get(a.get("type"), "texture")
        return {"source": self.name, "id": aid, "title": a["name"], "kind": kind,
                "author": ", ".join(a.get("authors", {})), "licence": CC0,
                "page": f"https://polyhaven.com/a/{aid}",
                "api_url": f"{self.api}/info/{aid}", "preview": a.get("thumbnail_url"),
                "attribution": "", "record": a}

    def files(self, item, a):
        files = fetch_json(f"{self.api}/files/{urllib.parse.quote(item['id'])}")
        md5 = lambda f: ("md5", f["md5"]) if f.get("md5") else None  # noqa: E731
        if item["kind"] == "hdri":
            entry = files["hdri"].get(a.res.lower()) or files["hdri"].get(a.res)
            if not entry:
                # the nearest size at or below the request, by number (bug hunt 2026-10-20: a
                # string sort fell back to "16k", the largest file)
                def k(r):  # "2k" = 2048 px, "512" = 512 px
                    m = re.match(r"\s*(\d+)\s*(k?)", str(r).lower())
                    return (int(m.group(1)) * (1024 if m.group(2) else 1)) if m else 0
                want = k(a.res)
                sizes = sorted(files["hdri"], key=k)
                below = [r for r in sizes if k(r) <= want]
                if not sizes:
                    raise SystemExit(f"polyhaven {item['id']} has no HDRI files")
                pick_res = below[-1] if below else sizes[0]
                entry = files["hdri"][pick_res]
                item["res_used"] = pick_res
            f = entry["hdr"]
            return [(f["url"], os.path.basename(urllib.parse.urlparse(f["url"]).path), md5(f))], files
        entry = files.get("gltf", {}).get(a.res)
        if not entry:
            raise SystemExit(f"no glTF at {a.res}; available: {', '.join(files.get('gltf', {}))}")
        main = entry["gltf"]
        out = [(main["url"], os.path.basename(urllib.parse.urlparse(main["url"]).path), md5(main))]
        out += [(f["url"], rel, md5(f)) for rel, f in main.get("include", {}).items()]
        return out, files


class AmbientCG:
    name = "ambientcg"
    api = "https://ambientcg.com/api/v3/assets"
    kinds = {"hdri": "hdri", "texture": "material", "model": "3d-model"}
    terms = "https://docs.ambientcg.com/license/ (CC0 1.0)"
    thanks = "ambientCG (ambientcg.com)"

    def record(self, query=None, aid=None, kind=None, limit=12):
        params = {"include": "downloads,previews,tags", "limit": str(limit)}
        if query:
            params["q"] = query
        if aid:
            params["id"] = aid
        if kind:
            params["type"] = self.kinds[kind]
        return fetch_json(f"{self.api}?{urllib.parse.urlencode(params)}").get("assets", [])

    @staticmethod
    def preview(a):
        for p in a.get("previews") or []:
            if re.search(r"\.(jpe?g|png|webp)(\?|$)", p.get("url", ""), re.I):
                return p["url"]
        return None

    def search(self, query, kind, limit, root):
        return [{"source": self.name, "id": a["id"], "title": a["id"], "kind": kind,
                 "licence": CC0, "preview": self.preview(a),
                 "page": f"https://ambientcg.com/view?id={a['id']}"}
                for a in self.record(query=query, kind=kind, limit=limit)]

    def info(self, aid, root):
        found = self.record(aid=aid, limit=1)
        if not found:
            raise SystemExit(f"ambientcg has no asset {aid}")
        a = found[0]
        return {"source": self.name, "id": aid, "title": aid, "kind": "texture",
                "author": "ambientCG (Lennart Demes)", "licence": CC0,
                "page": f"https://ambientcg.com/view?id={aid}", "api_url": f"{self.api}?id={aid}",
                "preview": self.preview(a), "record": a,
                "attribution": f"Created using {aid} from ambientCG.com, licensed under CC0 1.0"}

    def files(self, item, a):
        want = f"{a.res.upper()}-JPG"
        downloads = item["record"].get("downloads") or []
        pick = next((d for d in downloads if d.get("attributes") == want), None) or \
            next((d for d in downloads if d.get("attributes", "").startswith(a.res.upper())), None)
        if not pick:
            raise SystemExit(f"no {want}; available: {', '.join(d.get('attributes', '') for d in downloads)}")
        return [(pick["url"], f"{item['id']}_{pick['attributes']}.zip", None)], downloads


class Kenney:
    """No API: the search page lists pack links, a pack page links its zip, and every zip carries
    License.txt (CC0), which is checked before anything is kept."""
    name = "kenney"
    site = "https://kenney.nl"
    kinds = {"model": "3D", "sprite": "2D", "ui": "UI", "audio": "Audio", "texture": "Textures"}
    terms = "https://kenney.nl/support (CC0; credit not required)"
    thanks = "Kenney (www.kenney.nl)"
    NOT_PACKS = {"category", "tag", "series", "page"}

    def search(self, query, kind, limit, root):
        q = urllib.parse.quote(query)
        page = fetch_bytes(f"{self.site}/assets/category:{self.kinds[kind]}?search={q}").decode("utf-8", "replace")
        slugs = []
        for slug in re.findall(r"kenney\.nl/assets/([a-z0-9-]+)(?=['\"?#])", page):
            if slug not in self.NOT_PACKS and slug not in slugs:
                slugs.append(slug)
        return [{"source": self.name, "id": s, "title": s.replace("-", " ").title(), "kind": kind,
                 "licence": CC0, "preview": None, "page": f"{self.site}/assets/{s}"}
                for s in slugs[:limit]]

    def info(self, aid, root):
        if not re.fullmatch(r"[a-z0-9-]+", aid):
            raise SystemExit(f"not a Kenney pack name: {aid}")
        page = fetch_bytes(f"{self.site}/assets/{aid}").decode("utf-8", "replace")
        meta = {k: html.unescape(v) for k, v in
                re.findall(r"property=['\"]og:(\w+)['\"]\s+content=['\"]([^'\"]*)", page)}
        zips = re.findall(r"https://kenney\.nl/media/pages/assets/[^'\"]+\.zip", page)
        if not zips:
            raise SystemExit(f"kenney has no pack {aid} (no download link on its page)")
        category = re.search(r"assets/category:(\w+)", page)
        record = {"page": f"{self.site}/assets/{aid}", "og": meta, "zip": zips[0],
                  "category": category.group(1) if category else ""}
        return {"source": self.name, "id": aid, "kind": record["category"],
                "title": re.sub(r"\s*·\s*Kenney$", "", meta.get("title", aid)),
                "author": "Kenney", "licence": CC0, "page": record["page"],
                "api_url": record["page"], "preview": meta.get("image"), "attribution": "",
                "record": record}

    def files(self, item, a):
        z = item["record"]["zip"]
        return [(z, os.path.basename(urllib.parse.urlparse(z).path), None)], {"zip": z}

    def verify(self, item, folder, written):
        lic = next((f["path"] for f in written
                    if re.fullmatch(r"(.*/)?licen[cs]e\.txt", f["path"], re.I)), None)
        text = open(os.path.join(folder, lic), encoding="utf-8", errors="replace").read() if lic else ""
        if not CC0_TEXT.search(text):
            raise SystemExit("the pack's License.txt does not say CC0; not kept")
        return {"License.txt": text}


class GitHubSource:
    raw = "https://raw.githubusercontent.com"
    api = "https://api.github.com"

    def tree(self, owner, repo, branch, root):
        data = cached(f"{self.api}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1", root)
        if data.get("truncated"):
            raise SystemExit(f"{owner}/{repo}: GitHub returned a truncated file list")
        return [t for t in data.get("tree", []) if t.get("type") == "blob"]

    def raw_url(self, owner, repo, branch, path):
        return f"{self.raw}/{owner}/{repo}/{branch}/{urllib.parse.quote(path)}"


class KayKit(GitHubSource):
    name = "kaykit"
    owner = "KayKit-Game-Assets"
    kinds = {"model": "model"}
    terms = "https://kaylousberg.com/game-assets (free tier CC0; please do not resell unmodified)"
    thanks = "Kay Lousberg - KayKit (kaylousberg.com)"

    def repos(self, root):
        return cached(f"{self.api}/users/{self.owner}/repos?per_page=100", root)

    @staticmethod
    def short(repo):
        return re.sub(r"^kaykit-|-\d+(\.\d+)*$", "", repo["name"].lower())

    def search(self, query, kind, limit, root):
        words = words_of(query)
        hits = [(score(r["name"] + " " + (r.get("description") or ""), words), r)
                for r in self.repos(root)]
        return [{"source": self.name, "id": self.short(r), "title": r["name"], "kind": "model",
                 "licence": CC0, "preview": None,
                 "page": f"https://github.com/{self.owner}/{r['name']}"}
                for s, r in sorted(hits, key=lambda h: -h[0]) if s][:limit]

    def info(self, aid, root):
        repo = next((r for r in self.repos(root) if self.short(r) == aid), None)
        if not repo:
            raise SystemExit(f"kaykit has no pack {aid}")
        branch = repo.get("default_branch", "main")
        blobs = self.tree(self.owner, repo["name"], branch, root)
        text = fetch_bytes(self.raw_url(self.owner, repo["name"], branch, "LICENSE.txt")).decode("utf-8", "replace")
        sample = next((b["path"] for b in blobs if b["path"].endswith("sample.png")), None)
        return {"source": self.name, "id": aid, "title": repo["name"], "kind": "model",
                "author": "Kay Lousberg", "licence": CC0 if CC0_TEXT.search(text) else "unknown",
                "page": f"https://github.com/{self.owner}/{repo['name']}",
                "api_url": f"{self.api}/repos/{self.owner}/{repo['name']}",
                "preview": sample and self.raw_url(self.owner, repo["name"], branch, sample),
                "attribution": "", "evidence_files": {"LICENSE.txt": text},
                "record": {"repo": repo, "branch": branch, "blobs": blobs}}

    def files(self, item, a):
        rec, fmt = item["record"], a.format or "gltf"
        only = [o.strip().lower() for o in (a.only or "").split(",") if o.strip()]
        picked, formats = [], set()
        for b in rec["blobs"]:
            path = b["path"]
            if path == "LICENSE.txt":
                picked.append((path, "LICENSE.txt", b["sha"]))
                continue
            if "/Assets/" not in path:
                continue
            rel = path.split("/Assets/", 1)[1]
            top = rel.split("/", 1)[0]
            if "/" in rel:
                formats.add(top)
            if top == "texture" or (top == fmt and (not only or any(
                    os.path.basename(rel).lower().startswith(o) for o in only))):
                picked.append((path, rel, b["sha"]))
        if not any(rel.startswith(fmt + "/") for _, rel, _ in picked):
            raise SystemExit(f"no {fmt} files{' matching ' + a.only if only else ''}; formats: "
                             f"{', '.join(sorted(formats - {'texture'}))}")
        repo = rec["repo"]["name"]
        return [(self.raw_url(self.owner, repo, rec["branch"], p), rel, ("git", sha))
                for p, rel, sha in picked], [p for p, _, _ in picked]


class GameIcons(GitHubSource):
    name = "gameicons"
    owner, repo, branch = "game-icons", "icons", "master"
    kinds = {"icon": "icon"}
    terms = "https://game-icons.net/about.html (CC BY 3.0; some authors CC0)"
    thanks = "game-icons.net"

    def licences(self, root):
        """license.txt: CC BY 3.0 unless the author's line says CC0."""
        text = cached(self.raw_url(self.owner, self.repo, self.branch, "license.txt"), root,
                      parse=lambda s: {"text": s})["text"]
        authors = {}
        for name, rest in re.findall(r"^- ([^,\n]+?)(?:,|$| -)(.*)$", text, re.M):
            authors[re.sub(r"[^a-z0-9]", "", name.lower())] = (
                name.strip(), CC0 if re.search(r"\bCC0\b", f"{name} {rest}") else "CC-BY-3.0")
        return authors, text

    def author(self, folder, root):
        authors, _ = self.licences(root)
        return authors.get(re.sub(r"[^a-z0-9]", "", folder.lower()), (folder, "CC-BY-3.0"))

    def search(self, query, kind, limit, root):
        words = words_of(query)
        hits = []
        for b in self.tree(self.owner, self.repo, self.branch, root):
            if b["path"].endswith(".svg") and "/" in b["path"]:
                aid = b["path"][:-4]
                s = score(aid.replace("-", " ").replace("/", " "), words)
                if s:
                    hits.append((s, aid))
        out = []
        for _, aid in sorted(hits, key=lambda h: (-h[0], h[1]))[:limit]:
            folder, icon = aid.split("/", 1)
            out.append({"source": self.name, "id": aid, "title": icon, "kind": "icon",
                        "licence": self.author(folder, root)[1], "preview": None,
                        "page": f"https://game-icons.net/1x1/{aid}.html"})
        return out

    def info(self, aid, root):
        blob = next((b for b in self.tree(self.owner, self.repo, self.branch, root)
                     if b["path"] == aid + ".svg"), None)
        if not blob or "/" not in aid:
            raise SystemExit(f"game-icons has no icon {aid} (ids look like lorc/broadsword)")
        name, licence = self.author(aid.split("/", 1)[0], root)
        _, text = self.licences(root)
        return {"source": self.name, "id": aid, "title": aid.split("/", 1)[1], "kind": "icon",
                "author": name, "licence": licence, "page": f"https://game-icons.net/1x1/{aid}.html",
                "api_url": self.raw_url(self.owner, self.repo, self.branch, aid + ".svg"),
                "preview": None, "evidence_files": {"license.txt": text},
                "attribution": "" if licence == CC0 else
                f"Icons made by {name}. Available on https://game-icons.net",
                "record": blob}

    def files(self, item, a):
        b = item["record"]
        return [(self.raw_url(self.owner, self.repo, self.branch, b["path"]),
                 os.path.basename(b["path"]), ("git", b["sha"]))], b


class GoogleFonts(GitHubSource):
    name = "googlefonts"
    kinds = {"font": "font"}
    terms = "https://github.com/google/fonts (per family: OFL, Apache or UFL in METADATA.pb)"
    thanks = "Google Fonts"
    LICENCES = {"OFL": ("ofl", "OFL-1.1", "OFL.txt"), "APACHE2": ("apache", "Apache-2.0", "LICENSE.txt"),
                "UFL": ("ufl", "LicenseRef-UFL-1.0", "UFL.txt")}

    def families(self, root):
        return cached("https://fonts.google.com/metadata/fonts", root,
                      parse=lambda s: json.loads(s[s.index("{"):]))["familyMetadataList"]

    @staticmethod
    def slug(family):
        return re.sub(r"[^a-z0-9]", "", family.lower())

    def search(self, query, kind, limit, root):
        words = words_of(query)
        hits = [(score(" ".join([f["family"], f["family"].replace(" ", ""), f.get("category", ""),
                                 " ".join(f.get("designers", []))]), words), f)
                for f in self.families(root)]
        hits = [h for h in hits if h[0]]
        hits.sort(key=lambda h: (-h[0], h[1].get("popularity", 1e9)))
        return [{"source": self.name, "id": self.slug(f["family"]), "title": f["family"],
                 "kind": "font", "licence": None, "preview": None,
                 "page": "https://fonts.google.com/specimen/" + f["family"].replace(" ", "+")}
                for _, f in hits[:limit]]

    def info(self, aid, root):
        if not re.fullmatch(r"[a-z0-9]+", aid):
            raise SystemExit(f"not a Google Fonts family folder: {aid} (e.g. pressstart2p)")
        for folder in ("ofl", "apache", "ufl"):
            url = self.raw_url("google", "fonts", "main", f"{folder}/{aid}/METADATA.pb")
            try:
                text = fetch_bytes(url).decode("utf-8", "replace")
                break
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
        else:
            raise SystemExit(f"google/fonts has no family {aid}")
        field = lambda k: (re.search(rf'^{k}: "([^"]*)"', text, re.M) or [None, ""])[1]  # noqa: E731
        lic = self.LICENCES.get(field("license"))
        name = field("name") or aid
        return {"source": self.name, "id": aid, "title": name, "kind": "font",
                "author": field("designer"), "licence": lic[1] if lic else "unknown",
                "page": "https://fonts.google.com/specimen/" + name.replace(" ", "+"),
                "api_url": url, "preview": None, "attribution": "",
                "flags": ["ship the licence file with the font"],
                "evidence_files": {"METADATA.pb": text},
                "record": {"folder": f"{folder}/{aid}", "licence_file": lic[2] if lic else "",
                           "fonts": re.findall(r'filename: "([^"]+)"', text),
                           "copyright": re.findall(r'copyright: "((?:[^"\\]|\\.)*)"', text)}}

    def files(self, item, a):
        rec = item["record"]
        names = rec["fonts"] + ([rec["licence_file"]] if rec["licence_file"] else [])
        return [(self.raw_url("google", "fonts", "main", f"{rec['folder']}/{n}"), n, None)
                for n in names], rec


SOURCES = {s.name: s for s in (PolyHaven(), AmbientCG(), Kenney(), KayKit(), GameIcons(),
                               GoogleFonts())}

# import: files the user downloaded by hand (sources without an API or with a login)
MANUAL = {
    "kenney": (CC0, "Kenney", []),
    "kaykit": (CC0, "Kay Lousberg", []),
    "polyhaven": (CC0, "", []),
    "ambientcg": (CC0, "ambientCG", []),
    "quaternius": ("LicenseRef-Quaternius-QAL-1.0", "Quaternius",
                   ["QAL: no redistribution as a standalone asset or pack, even modified; keep the "
                    "raw files out of a public repository"]),
    "sonniss": ("LicenseRef-Sonniss-GDC-2.0", "Sonniss",
                ["Sonniss GDC licence: no redistribution of the sounds as sounds; keep the raw "
                 "files out of a public repository"]),
}


# --- helpers ------------------------------------------------------------------------------------

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


def tier(root):
    return manifest(root).get("asset_libraries", "attribution")


def allowed(root):
    return TIERS.get(tier(root), TIERS["attribution"])


def refuse_unless_allowed(licence, root):
    if licence not in allowed(root):
        raise SystemExit(f"{licence} is not allowed here (manifest asset_libraries={tier(root)}); "
                         "not downloaded")


def source_or_exit(name):
    if name not in SOURCES:
        raise SystemExit(f"unknown source {name}; known: {', '.join(SOURCES)}")
    return SOURCES[name]


def safe_extract(raw, folder):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = []
        for m in z.infolist():
            target = os.path.realpath(os.path.join(folder, m.filename))
            if not target.startswith(os.path.realpath(folder) + os.sep):
                raise SystemExit(f"refusing a zip entry outside the folder: {m.filename}")
            if m.is_dir():
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(m) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            names.append(m.filename)
        return names


def file_entry(folder, rel, **extra):
    with open(os.path.join(folder, rel), "rb") as fh:
        data = fh.read()
    return {"path": rel.replace("\\", "/"), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), **extra}


SAFE_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")


def item_folder(root, into, source, aid):
    """The item's folder, strictly inside <into>/<source>. Every part of the source and the id is
    a plain name (no '.', '..', separators or drive letters): `--id ..` once named art/library
    itself, and replacing it deleted every pack (review 2026-10-21, KILN-REV-01)."""
    parts = [source] + str(aid).split("/")
    if any(not SAFE_PART.fullmatch(p) or set(p) == {"."} for p in parts):
        raise SystemExit(f"{source}/{aid}: source and id are plain names (letters, digits, - _ ., "
                         "id parts separated by /), not . or .. or a path")
    base = os.path.realpath(os.path.join(root, into, source))
    folder = os.path.realpath(os.path.join(base, *parts[1:]))
    if not folder.startswith(base + os.sep):
        raise SystemExit(f"{source}/{aid} would not be inside {os.path.join(into, source)}")
    return folder


def write_item(root, into, source, aid, build):
    """Assemble <id>.part with `build(part)` -> provenance; keep it only when every check passed.
    An existing item is moved aside, not deleted, until the new one is in place."""
    folder = item_folder(root, into, source, aid)
    part, old = folder + ".part", folder + ".old"
    for leftover in (part, old):
        shutil.rmtree(leftover, ignore_errors=True)
    os.makedirs(os.path.join(part, "evidence"))
    try:
        prov = build(part)
        with open(os.path.join(part, "provenance.json"), "w", encoding="utf-8") as fh:
            json.dump(prov, fh, indent=1)
        if os.path.isdir(folder):
            os.replace(folder, old)
        try:
            os.replace(part, folder)
        except BaseException:
            if os.path.isdir(old) and not os.path.exists(folder):
                os.replace(old, folder)          # the old item comes back
            raise
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    return os.path.relpath(folder, root).replace("\\", "/"), prov


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# --- commands -----------------------------------------------------------------------------------

def cmd_sources(a, root):
    return {"asset_libraries": tier(root), "allowed_licences": sorted(allowed(root)),
            "sources": [{"source": n, "kinds": list(s.kinds), "key": "none", "terms": s.terms}
                        for n, s in SOURCES.items()],
            "import": sorted(MANUAL) + ["any other, with --licence"]}


def cmd_search(a, root):
    names = list(SOURCES) if a.source == "all" else [a.source]
    hits, errors = [], {}
    for n in names:
        src = source_or_exit(n)
        if a.kind not in src.kinds:
            continue
        try:
            found = src.search(a.query, a.kind, a.limit, root)
        except (urllib.error.URLError, OSError, ValueError, KeyError, SystemExit) as e:
            if a.source != "all":
                raise
            errors[n] = str(getattr(e, "code", None) or e)   # one source down: the rest still answer
            continue
        hits += [h for h in found if h["licence"] is None or h["licence"] in allowed(root)]
    out = {"query": a.query, "kind": a.kind, "results": hits,
           "note": "licence None = read from the item at fetch"}
    if errors:
        out["errors"] = errors
    return out


def cmd_info(a, root):
    item = source_or_exit(a.source).info(a.id, root)
    return {k: v for k, v in item.items() if k not in ("record", "evidence_files")}


def cmd_fetch(a, root):
    src = source_or_exit(a.source)
    item = src.info(a.id, root)
    refuse_unless_allowed(item["licence"], root)

    def build(part):
        files, listing = src.files(item, a)
        written = []
        for url, rel, check in files:
            raw = fetch_bytes(url, 600)
            if check and check[1] != (hashlib.md5(raw).hexdigest() if check[0] == "md5"
                                      else git_blob_sha(raw)):
                raise SystemExit(f"{rel}: checksum differs from the source's; not kept")
            if rel.endswith(".zip"):
                written += [file_entry(part, n, url=url) for n in safe_extract(raw, part)]
                continue
            path = os.path.join(part, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(raw)
            written.append(file_entry(part, rel, url=url, **({check[0]: check[1]} if check else {})))
        evidence = dict(item.get("evidence_files") or {})
        if hasattr(src, "verify"):
            evidence.update(src.verify(item, part, written))
        names = []
        for name, data in [("info.json", item["record"]), ("files.json", listing)]:
            with open(os.path.join(part, "evidence", name), "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            names.append("evidence/" + name)
        for name, text in evidence.items():
            with open(os.path.join(part, "evidence", name), "w", encoding="utf-8") as fh:
                fh.write(text)
            names.append("evidence/" + name)
        return {"kind": "library", "tool": "assets_api.py", "source": src.name,
                "source_id": a.id, "title": item["title"], "author": item["author"],
                "page_url": item["page"], "api_url": item["api_url"], "licence": item["licence"],
                "licence_url": LICENCE_URLS.get(item["licence"], ""),
                "attribution": item["attribution"], "flags": item.get("flags", []),
                "modified": False, "variant": {"res": item.get("res_used", a.res),
                                               "res_asked": a.res, "format": a.format,
                                               "only": a.only},
                "retrieved_utc": now_utc(), "files": written, "evidence": names}

    out, prov = write_item(root, a.into, src.name, a.id, build)
    return {"out": out, "licence": prov["licence"], "files": [f["path"] for f in prov["files"]],
            "next": "run the asset pipeline (scale, pivot, budgets), then licenses.py build"}


def cmd_import(a, root):
    src_dir = os.path.abspath(a.folder)
    if not os.path.isdir(src_dir):
        raise SystemExit(f"no such folder: {a.folder}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", a.source) or not re.fullmatch(r"[\w.-]+", a.id):
        raise SystemExit("--source and --id are short names (letters, digits, - _ .)")
    known = MANUAL.get(a.source)
    licence = a.licence or (known[0] if known else "")
    if not licence:
        raise SystemExit(f"{a.source} is not a known source: say the licence with --licence <id> "
                         "as the source's page states it (e.g. CC0-1.0, CC-BY-4.0)")
    refuse_unless_allowed(licence, root)
    target = item_folder(root, a.into, a.source, a.id)
    real_src = os.path.realpath(src_dir)
    if target == real_src or target.startswith(real_src + os.sep) or \
            real_src.startswith(target + os.sep):
        raise SystemExit("import from a folder outside art/library")
    lic_files = [n for n in sorted(os.listdir(src_dir))
                 if re.match(r"(licen[cs]e|copying)", n, re.I) and os.path.isfile(os.path.join(src_dir, n))]
    texts = {n: open(os.path.join(src_dir, n), encoding="utf-8", errors="replace").read()
             for n in lic_files}
    if licence == CC0 and texts and not any(CC0_TEXT.search(t) for t in texts.values()):
        raise SystemExit(f"{', '.join(texts)} in the folder does not say CC0; not imported")
    flags = list(known[2]) if known else []
    if not texts:
        flags.append("licence declared by the user (no licence file)")
    author = a.author or (known[1] if known else "")
    title = a.title or a.id
    attribution = a.attribution or ("" if licence == CC0 or licence in FONTS or licence in CUSTOM
                                    else f'"{title}" by {author or "unknown"}, {licence}: {a.url}')

    def build(part):
        written = []
        for dirpath, _, names in os.walk(src_dir):
            for n in names:
                rel = os.path.relpath(os.path.join(dirpath, n), src_dir)
                os.makedirs(os.path.dirname(os.path.join(part, rel)) or part, exist_ok=True)
                shutil.copy2(os.path.join(dirpath, n), os.path.join(part, rel))
                written.append(file_entry(part, rel))
        for n, text in texts.items():
            with open(os.path.join(part, "evidence", n), "w", encoding="utf-8") as fh:
                fh.write(text)
        return {"kind": "library", "tool": "assets_api.py import", "source": a.source,
                "source_id": a.id, "title": title, "author": author, "page_url": a.url,
                "api_url": "", "licence": licence, "licence_url": LICENCE_URLS.get(licence, ""),
                "attribution": attribution, "flags": flags, "modified": False,
                "imported_from": os.path.basename(src_dir), "retrieved_utc": now_utc(),
                "files": written, "evidence": ["evidence/" + n for n in texts]}

    out, prov = write_item(root, a.into, a.source, a.id, build)
    return {"out": out, "licence": licence, "flags": flags, "files": len(prov["files"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sources")
    s = sub.add_parser("search")
    s.add_argument("source")
    s.add_argument("query")
    s.add_argument("--kind", required=True,
                   choices=["hdri", "texture", "model", "sprite", "ui", "audio", "icon", "font"])
    s.add_argument("--limit", type=int, default=12)
    i = sub.add_parser("info")
    i.add_argument("source")
    i.add_argument("id")
    f = sub.add_parser("fetch")
    f.add_argument("source")
    f.add_argument("id")
    f.add_argument("--res", default="2k")
    f.add_argument("--format", default="")
    f.add_argument("--only", default="")
    f.add_argument("--into", default=os.path.join("art", "library"))
    m = sub.add_parser("import")
    m.add_argument("folder")
    m.add_argument("--source", required=True)
    m.add_argument("--id", required=True)
    m.add_argument("--url", required=True)
    m.add_argument("--licence", default="")
    m.add_argument("--author", default="")
    m.add_argument("--title", default="")
    m.add_argument("--attribution", default="")
    m.add_argument("--into", default=os.path.join("art", "library"))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        out = globals()["cmd_" + a.cmd](a, os.getcwd())
    except SystemExit as e:
        print(json.dumps({"error": str(e.code)}))
        return 1
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 1
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
