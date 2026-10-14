"""Look up the latest Kiln release and remember it for the next session start. Stdlib only.

Started in the background by the SessionStart hook at most once a day (never in the hook's own
time), so a session never waits for the network. Writes ~/.kiln/update-check.json:
{"checked": <unix time>, "latest": "<version>", "url": "<release page>"} or, when the lookup
fails (offline, rate limit), {"checked": ..., "error": "..."} so it is not retried every session.
The repository comes from the plugin manifest (`repository`, default ajadi/kiln);
KILN_RELEASES_URL overrides the API address (tests). Switch it off with "update_check": "off"
in ~/.kiln/machine.json.
"""

import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kiln_hooklib as k  # noqa: E402

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_EVERY_S = 86400


def cache_path():
    return os.path.join(k.kiln_home(), "update-check.json")


def releases_url():
    if os.environ.get("KILN_RELEASES_URL"):
        return os.environ["KILN_RELEASES_URL"]
    repo = "ajadi/kiln"
    try:
        with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            m = re.search(r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?/?$",
                          json.load(fh).get("repository", ""))
            repo = m.group(1) if m else repo
    except (OSError, ValueError):
        pass
    return f"https://api.github.com/repos/{repo}/releases/latest"


def switched_off():
    machine = k.load_json(os.path.join(k.kiln_home(), "machine.json"), {})
    return str(machine.get("update_check", "on")).lower() == "off"


def due():
    """True when the last check is older than a day (or there was none)."""
    if switched_off():
        return False
    return time.time() - k.load_json(cache_path(), {}).get("checked", 0) > CHECK_EVERY_S


def notice(installed, version_key, runtime="claude"):
    """The session-start line when a newer release was seen, else None."""
    if switched_off() or not installed:
        return None
    latest = k.load_json(cache_path(), {}).get("latest")
    if not latest or version_key(latest) <= version_key(installed):
        return None
    how = ("`codex plugin remove kiln@kiln`, then `codex plugin add kiln@kiln`, then the update "
           "skill with `all` (every project on this machine)" if runtime == "codex" else
           "`claude plugin marketplace update kiln`, then `/kiln:update all` (every project on "
           "this machine)")
    return (f"Kiln {latest} is out (installed: {installed}). Tell the user once, at the start: "
            f"update with {how} - only after the user's yes. Do not mention it again this "
            "session.")


def mark_started():
    """Record the check as started, so sessions opened before it answers do not start more."""
    record = k.load_json(cache_path(), {})
    record["checked"] = time.time()
    try:
        os.makedirs(k.kiln_home(), exist_ok=True)
        k.save_json(cache_path(), record)
    except OSError:
        pass


def main():
    # keep what was seen before: an offline day must not forget a newer release
    record = dict(k.load_json(cache_path(), {}), checked=time.time())
    record.pop("error", None)
    try:
        req = urllib.request.Request(releases_url(), headers={
            "Accept": "application/vnd.github+json", "User-Agent": "kiln-update-check"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict) or not data.get("tag_name"):
            raise ValueError("no tag_name in the releases answer")
        record["latest"] = str(data["tag_name"]).lstrip("v")
        record["url"] = data.get("html_url", "")
    except Exception as exc:  # background helper: any failure is recorded, never retried at once
        record["error"] = f"{type(exc).__name__}: {exc}"[:200]
    try:
        os.makedirs(k.kiln_home(), exist_ok=True)
        k.save_json(cache_path(), record)
    except OSError:
        pass


if __name__ == "__main__":
    main()
