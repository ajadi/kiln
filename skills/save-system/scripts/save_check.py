"""Golden save fixtures against the declared save versions and migration chain (stdlib only).

  python save_check.py tests/saves/manifest.json
  python save_check.py tests/saves/manifest.json --out production/save_check.json
  python save_check.py tests/saves/manifest.json --fixtures "tests/saves/v*/**/*.json"

Manifest (JSON next to the fixtures; its paths are relative to the manifest's folder):

  {
    "current_version": 3,
    "first_version": 1,                  oldest version the game still loads (default 1)
    "version_field": "save_version",     dotted path, in the header line or the body
    "fixtures": "v*/**/*.json",          glob (default)
    "migrations": [
      {"from": 1, "to": 2, "rename": {"hp": "player.health"}, "add": ["settings.fov"]},
      {"from": 2, "to": 3, "remove": ["legacy_flags"]}
    ],
    "schemas": {                         optional, per version: allowed and required paths
      "3": {"fields": ["player.health", "player.pos", "inventory[].id", "flags.*"],
            "required": ["player.health"]}
    },
    "checksum": {"field": "sha256", "algo": "sha256"}     optional: sha256|sha1|md5|crc32
  }

Paths: "a.b" nested keys, "list[]" every element, "*" any key; a declared path also allows
everything below it. Field operations of a migration (rename/add/remove; rename keys are literal
prefixes) are optional; when every migration on a fixture's path declares them, the fixture's
field set is migrated on paper and checked against the current schema.

Save layouts: one JSON object, or a header line (JSON object holding the version and the checksum)
followed by the JSON body; the checksum covers the body bytes exactly as written.

Checks: every version in [first_version, current_version) reaches current_version through the
declared migrations (no gaps, duplicates, backward steps or versions past current); at least one
fixture per version; a fixture's v<N> folder matches its version; integer versions not newer than
current; checksums; unknown and missing required fields; the simulated migration. Prints JSON with
"verdict" (pass|fail); exit code 1 on fail. It does not run game code: the engine test that loads
every fixture through the real loader is still required.
"""

import argparse
import glob as globlib
import hashlib
import json
import os
import re
import sys
import zlib

ALGOS = ("sha256", "sha1", "md5", "crc32")
PART = re.compile(r"^([^\[\]]*)((?:\[\])*)$")


# ---------------------------------------------------------------- field paths

def parse_path(path):
    """'inv[].id' -> [('key','inv'), ('each',), ('key','id')]; '*' -> ('any',)."""
    steps = []
    for part in str(path).split("."):
        m = PART.match(part)
        if not m:
            raise ValueError(f"bad field path {path!r}")
        name, brackets = m.groups()
        if name:
            steps.append(("any",) if name == "*" else ("key", name))
        steps.extend([("each",)] * (len(brackets) // 2))
    return tuple(steps)


def step_text(steps):
    out = ""
    for step in steps:
        if step[0] == "each":
            out += "[]"
        else:
            name = "*" if step[0] == "any" else step[1]
            out += ("." if out else "") + name
    return out


def flatten(value, prefix=()):
    """{path_steps: is_empty_container} for every leaf of a JSON value."""
    out = {}
    if isinstance(value, dict):
        if not value and prefix:
            out[prefix] = True
        for key, item in value.items():
            out.update(flatten(item, prefix + (("key", str(key)),)))
    elif isinstance(value, list):
        if not value:
            out[prefix + (("each",),)] = True
        for item in value:
            out.update(flatten(item, prefix + (("each",),)))
    else:
        out[prefix] = False
    return out


def step_match(pattern_step, path_step):
    if pattern_step[0] == "any":
        return path_step[0] in ("key", "any")
    return pattern_step == path_step


def prefix_match(pattern, path, n):
    return all(step_match(pattern[i], path[i]) for i in range(n))


def covers(pattern, path):
    """pattern allows path: equal, or path lies below pattern."""
    return len(pattern) <= len(path) and prefix_match(pattern, path, len(pattern))


def known(path, empty, patterns):
    for pattern in patterns:
        if covers(pattern, path):
            return True
        if empty and len(path) < len(pattern) and prefix_match(pattern, path, len(path)):
            return True  # an empty list/object the schema describes the inside of
    return False


def present_in_value(value, steps):
    """Required path exists; empty lists/objects satisfy everything below them."""
    if not steps:
        return True
    step, rest = steps[0], steps[1:]
    if step[0] == "each":
        return isinstance(value, list) and all(present_in_value(v, rest) for v in value)
    if not isinstance(value, dict):
        return False
    if step[0] == "any":
        return all(present_in_value(v, rest) for v in value.values())
    return step[1] in value and present_in_value(value[step[1]], rest)


def present_in_set(fields, steps):
    for path, empty in fields.items():
        if covers(steps, path) or covers(path, steps) and (empty or path == steps):
            return True
    return False


def get_dotted(obj, dotted):
    cur = obj
    for key in dotted.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


# ---------------------------------------------------------------- manifest

def load_json(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def check_chain(manifest, problems, warnings):
    current = as_int(manifest.get("current_version"))
    first = as_int(manifest.get("first_version", 1))
    if current is None or current < 1:
        problems.append("manifest: current_version must be an integer >= 1")
        return None, None, {}, {}
    if first is None or first > current:
        problems.append("manifest: first_version must be an integer <= current_version")
        first = 1
    by_from = {}
    for i, mig in enumerate(manifest.get("migrations") or []):
        src, dst = as_int(mig.get("from")), as_int(mig.get("to"))
        where = f"migration #{i + 1} ({mig.get('from')}->{mig.get('to')})"
        if src is None or dst is None:
            problems.append(f"{where}: from/to must be integers")
            continue
        if dst <= src:
            problems.append(f"{where}: goes backwards or nowhere")
            continue
        if dst > current or src >= current:
            problems.append(f"{where}: past current_version {current}")
            continue
        if src in by_from:
            problems.append(f"{where}: second migration from v{src}; the chain must be "
                            "unambiguous")
            continue
        for key in ("rename", "add", "remove"):
            if key in mig and not isinstance(mig[key], dict if key == "rename" else list):
                problems.append(f"{where}: '{key}' must be "
                                f"{'an object' if key == 'rename' else 'a list'}")
        by_from[src] = mig
    chains = {}
    for version in range(first, current + 1):
        path, v = [version], version
        while v != current:
            mig = by_from.get(v)
            if mig is None:
                break
            v = as_int(mig["to"])
            path.append(v)
        if v != current:
            problems.append(f"v{version} cannot reach v{current}: no migration from v{v}")
            chains[version] = None
        else:
            chains[version] = path
    for src in sorted(by_from):
        if src < first:
            warnings.append(f"migration from v{src} is below first_version {first} (dead code?)")
    return current, first, chains, by_from


def schemas_of(manifest, problems):
    out = {}
    for key, schema in (manifest.get("schemas") or {}).items():
        version = as_int(int(key)) if str(key).isdigit() else None
        if version is None or not isinstance(schema, dict):
            problems.append(f"manifest: schema key {key!r} must be a version number with an "
                            "object")
            continue
        try:
            fields = [parse_path(p) for p in schema.get("fields") or []]
            required = [parse_path(p) for p in schema.get("required") or []]
        except ValueError as exc:
            problems.append(f"manifest: schema v{version}: {exc}")
            continue
        out[version] = {"fields": fields, "required": required}
    return out


# ---------------------------------------------------------------- fixtures

def read_save(path):
    """(header or None, body object, body bytes)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    first, sep, rest = raw.partition(b"\n")
    if sep and rest.strip():
        try:
            header = json.loads(first.decode("utf-8").rstrip("\r"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            header = None
        if isinstance(header, dict):
            return header, json.loads(rest.decode("utf-8")), rest
    return None, json.loads(raw.decode("utf-8")), raw


def digest(algo, data):
    if algo == "crc32":
        return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"
    return hashlib.new(algo, data).hexdigest()


def migrate_fields(fields, chain, by_from):
    out = dict(fields)
    for src in chain[:-1]:
        mig = by_from[src]
        for old, new in (mig.get("rename") or {}).items():
            old_s, new_s = parse_path(old), parse_path(new)
            out = {(new_s + p[len(old_s):] if covers(old_s, p) else p): e for p, e in out.items()}
        for gone in mig.get("remove") or []:
            gone_s = parse_path(gone)
            out = {p: e for p, e in out.items() if not covers(gone_s, p)}
        for added in mig.get("add") or []:
            out.setdefault(parse_path(added), True)  # a default value, maybe an empty container
    return out


def check_fixture(path, ctx):
    res = {"file": path.replace("\\", "/"), "problems": [], "warnings": []}
    probs, warns = res["problems"], res["warnings"]
    try:
        header, body, body_bytes = read_save(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        probs.append(f"unreadable: {exc}")
        return res
    if not isinstance(body, dict):
        probs.append("save body is not a JSON object")
        return res
    field = ctx["version_field"]
    raw_version = get_dotted(header, field) if header else None
    if raw_version is None:
        raw_version = get_dotted(body, field)
    version = as_int(raw_version)
    if version is None:
        probs.append(f"no integer '{field}' (found {raw_version!r})")
        return res
    if isinstance(raw_version, float):
        warns.append(f"'{field}' stored as a float ({raw_version}); compare with int()")
    res["version"] = version
    folder = [int(m.group(1)) for part in re.split(r"[\\/]", path)
              if (m := re.fullmatch(r"v(\d+)", part))]
    if folder and folder[-1] != version:
        probs.append(f"in folder v{folder[-1]} but {field} = {version}")
    current, first = ctx["current"], ctx["first"]
    if version > current:
        probs.append(f"v{version} is newer than current_version {current}; the loader must "
                     "refuse it without overwriting — keep such cases outside the fixture glob")
        return res
    if version < first:
        probs.append(f"v{version} is older than first_version {first}; drop the fixture or "
                     "lower first_version")
        return res
    checksum = ctx["checksum"]
    if checksum:
        stored = (header or {}).get(checksum["field"])
        if stored is None:
            probs.append(f"no header line with '{checksum['field']}' (checksum configured)")
        else:
            want = str(stored).lower().split(":")[-1]
            got = digest(checksum["algo"], body_bytes)
            if want != got:
                probs.append(f"{checksum['algo']} mismatch: header {want}, body {got}")
    fields = flatten(body)
    fields.pop(parse_path(field), None)
    schema = ctx["schemas"].get(version)
    if schema is None:
        if ctx["schemas"]:
            warns.append(f"no schema for v{version}: field check skipped")
    else:
        unknown = sorted(step_text(p) for p, e in fields.items()
                         if not known(p, e, schema["fields"]))
        missing = [step_text(r) for r in schema["required"] if not present_in_value(body, r)]
        if unknown:
            probs.append(f"unknown fields for v{version}: {', '.join(unknown[:8])}")
        if missing:
            probs.append(f"missing required fields for v{version}: {', '.join(missing[:8])}")
    chain = ctx["chains"].get(version)
    res["chain"] = chain
    target = ctx["schemas"].get(current)
    if chain is None:
        res["simulated"] = "no chain"
    elif version == current:
        res["simulated"] = "current"
    elif target is None:
        res["simulated"] = f"skipped: no schema for current v{current}"
    elif not all(any(k in ctx["by_from"][v] for k in ("rename", "add", "remove"))
                 for v in chain[:-1]):
        res["simulated"] = "skipped: a migration on the path declares no field operations"
    else:
        migrated = migrate_fields(fields, chain, ctx["by_from"])
        unknown = sorted(step_text(p) for p, e in migrated.items()
                         if not known(p, e, target["fields"]))
        missing = [step_text(r) for r in target["required"] if not present_in_set(migrated, r)]
        sim = []
        if unknown:
            sim.append(f"after migration still has fields unknown to v{current}: "
                       f"{', '.join(unknown[:8])} (rename or remove them)")
        if missing:
            sim.append(f"after migration lacks required v{current} fields: "
                       f"{', '.join(missing[:8])} (add them with defaults)")
        probs.extend(sim)
        res["simulated"] = "fail" if sim else "ok"
    return res


def expand(patterns, base):
    files = set()
    for pattern in patterns:
        full = pattern if os.path.isabs(pattern) or base is None else os.path.join(base, pattern)
        files.update(p for p in globlib.glob(full, recursive=True) if os.path.isfile(p))
    return sorted(files)


def run(manifest_path, fixture_globs=None):
    problems, warnings = [], []
    try:
        manifest = load_json(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {"manifest": manifest_path, "problems": [f"manifest unreadable: {exc}"],
                "verdict": "fail"}
    if not isinstance(manifest, dict):
        return {"manifest": manifest_path, "problems": ["manifest is not a JSON object"],
                "verdict": "fail"}
    current, first, chains, by_from = check_chain(manifest, problems, warnings)
    if current is None:
        return {"manifest": manifest_path, "problems": problems, "verdict": "fail"}
    checksum = manifest.get("checksum")
    if checksum is not None:
        if not isinstance(checksum, dict) or checksum.get("algo", "sha256") not in ALGOS:
            problems.append(f"manifest: checksum needs field and algo in {ALGOS}")
            checksum = None
        else:
            checksum = {"field": checksum.get("field", checksum.get("algo", "sha256")),
                        "algo": checksum.get("algo", "sha256")}
    ctx = {"current": current, "first": first, "chains": chains, "by_from": by_from,
           "version_field": manifest.get("version_field", "save_version"),
           "schemas": schemas_of(manifest, problems), "checksum": checksum}
    if fixture_globs:
        files = expand(fixture_globs, None)
    else:
        base = os.path.dirname(os.path.abspath(manifest_path))
        files = expand([manifest.get("fixtures", "v*/**/*.json")], base)
    files = [f for f in files if os.path.abspath(f) != os.path.abspath(manifest_path)]
    fixtures = [check_fixture(f, ctx) for f in files]
    counts = {v: 0 for v in range(first, current + 1)}
    for fx in fixtures:
        if fx.get("version") in counts:
            counts[fx["version"]] += 1
        problems.extend(f"{fx['file']}: {p}" for p in fx["problems"])
        warnings.extend(f"{fx['file']}: {w}" for w in fx["warnings"])
    if not files:
        problems.append("no fixture files found")
    for version, n in counts.items():
        if n == 0:
            problems.append(f"no golden fixture for v{version} (capture one from a build that "
                            f"writes v{version})")
    if current not in ctx["schemas"] and ctx["schemas"]:
        warnings.append(f"no schema for current v{current}: migration simulation skipped")
    return {"manifest": manifest_path.replace("\\", "/"), "current_version": current,
            "first_version": first,
            "chains": {str(v): c for v, c in chains.items()},
            "fixtures_per_version": {str(v): n for v, n in counts.items()},
            "fixtures": fixtures, "problems": problems, "warnings": warnings,
            "verdict": "fail" if problems else "pass"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", help="save manifest JSON (e.g. tests/saves/manifest.json)")
    parser.add_argument("--fixtures", nargs="+", default=None,
                        help="fixture globs relative to the working directory (overrides the "
                             "manifest's 'fixtures')")
    parser.add_argument("--out", default=None, help="also write the JSON report here")
    args = parser.parse_args(argv)
    result = run(args.manifest, args.fixtures)
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
