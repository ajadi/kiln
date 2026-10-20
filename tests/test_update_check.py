"""Tests for the new-version check: plugins/kiln/hooks/update_check.py and its use at session
start (stdlib only). Offline: the releases API is a file:// fixture.

User (2026-10-14): Kiln should notice a new version by itself when a session starts. Done as a
hook (code, no tokens, works offline): a background check at most once a day, the notice at the
next session start, nothing updated without the user's yes.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HOOKS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "hooks")
CHECK = os.path.join(HOOKS, "update_check.py")
SESSION = os.path.join(HOOKS, "session.py")


def installed_version():
    with open(os.path.join(HOOKS, "..", ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        return json.load(fh)["version"]


class Env:
    def __init__(self, latest="v9.9.9"):
        self.root = tempfile.mkdtemp(prefix="kiln-upcheck-")
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home)
        self.api = os.path.join(self.root, "latest.json")
        with open(self.api, "w", encoding="utf-8") as fh:
            json.dump({"tag_name": latest, "html_url": "https://example.invalid/r"}, fh)
        self.project = os.path.join(self.root, "game")
        os.makedirs(self.project)
        with open(os.path.join(self.project, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write(f"framework=kiln\nframework_version={installed_version()}\nengine=godot\n")

    def env(self, url=None):
        return dict(os.environ, KILN_HOME=self.home, KILN_REGISTER_TEMP="1",
                    CLAUDE_PROJECT_DIR=self.project,
                    KILN_RELEASES_URL=url or "file:///" + self.api.replace("\\", "/"))

    def cache(self, value=None):
        path = os.path.join(self.home, "update-check.json")
        if value is not None:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(value, fh)
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except OSError:
            return None

    def check(self, url=None):
        return subprocess.run([sys.executable, "-B", CHECK], env=self.env(url),
                              capture_output=True, text=True, timeout=60)

    def start(self):
        p = subprocess.run([sys.executable, "-B", SESSION, "start"], env=self.env(),
                           input=json.dumps({"session_id": "s", "source": "startup"}),
                           capture_output=True, text=True, timeout=30)
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


class UpdateCheck(unittest.TestCase):
    def test_the_check_records_the_latest_release(self):
        e = Env()
        p = e.check()
        self.assertEqual(p.returncode, 0, p.stderr)
        cache = e.cache()
        self.assertEqual(cache["latest"], "9.9.9")
        self.assertGreater(cache["checked"], time.time() - 60)

    def test_no_network_is_quiet_and_not_retried_every_session(self):
        e = Env()
        p = e.check(url="file:///" + os.path.join(e.root, "missing.json").replace("\\", "/"))
        self.assertEqual(p.returncode, 0, p.stderr)
        cache = e.cache()
        self.assertNotIn("latest", cache)
        self.assertIn("error", cache)
        self.assertNotIn("is out", e.start())

    def test_a_bad_answer_is_recorded_too(self):
        # Review: a JSON list (or a cut connection) crashed the checker before it wrote anything,
        # so every session start spawned it again.
        e = Env()
        with open(e.api, "w", encoding="utf-8") as fh:
            fh.write("[1, 2]")
        p = e.check()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("error", e.cache())

    def test_an_offline_day_keeps_the_release_already_seen(self):
        # Review: a failed lookup dropped the newer version seen the day before.
        e = Env()
        e.cache({"latest": "9.9.9", "checked": time.time() - 2 * 86400})
        e.check(url="file:///" + os.path.join(e.root, "missing.json").replace("\\", "/"))
        self.assertEqual(e.cache()["latest"], "9.9.9")
        self.assertIn("Kiln 9.9.9 is out", e.start())

    def test_codex_gets_codex_commands(self):
        e = Env()
        e.cache({"latest": "9.9.9", "checked": time.time()})
        p = subprocess.run([sys.executable, "-B", SESSION, "start", "--runtime", "codex"],
                           env=e.env(),
                           input=json.dumps({"session_id": "s", "source": "startup"}),
                           capture_output=True, text=True, timeout=30)
        ctx = p.stdout
        self.assertIn("codex plugin marketplace upgrade kiln", ctx)
        self.assertNotIn("claude plugin marketplace update", ctx)

    def test_copilot_and_opencode_sessions_are_not_told_slash_commands(self):
        for runtime in ("copilot", "opencode"):
            e = Env()
            e.cache({"latest": "9.9.9", "checked": time.time()})
            payload = {"sessionId": "s", "source": "new"} if runtime == "copilot" else \
                {"session_id": "s", "source": "startup", "hook_event_name": "SessionStart"}
            p = subprocess.run([sys.executable, "-B", SESSION, "start", "--runtime", runtime],
                               env=e.env(), input=json.dumps(payload), capture_output=True,
                               text=True, timeout=30)
            self.assertIn("Kiln 9.9.9 is out", p.stdout, runtime)
            self.assertNotIn("/kiln:pipeline", p.stdout, runtime)
            self.assertNotIn("claude plugin marketplace update", p.stdout, runtime)

    def test_every_runtime_gets_its_own_update_commands(self):
        # every agent's session names its own way to update (Gemini, Copilot and OpenCode were
        # told Claude Code's commands)
        sys.path.insert(0, os.path.dirname(SESSION))
        import update_check
        for runtime, want in (("gemini", "gemini extensions update kiln"),
                              ("copilot", "copilot plugin update kiln"),
                              ("opencode", "git pull"),
                              ("claude", "claude plugin marketplace update kiln")):
            self.assertIn(want, update_check.UPDATE_HOW[runtime])
            for other in ("claude plugin", "codex plugin", "gemini extensions", "copilot plugin"):
                if runtime not in other:
                    self.assertNotIn(other, update_check.UPDATE_HOW[runtime], runtime)

    def test_a_check_in_flight_is_not_started_twice(self):
        # Review: due() stayed true until the background check finished.
        e = Env()
        e.cache({"latest": installed_version(), "checked": time.time() - 2 * 86400})
        e.start()
        self.assertGreater(e.cache()["checked"], time.time() - 30)

    def test_a_newer_release_is_announced_with_the_commands(self):
        e = Env()
        e.cache({"latest": "9.9.9", "checked": time.time()})
        ctx = e.start()
        self.assertIn(f"Kiln 9.9.9 is out (installed: {installed_version()})", ctx)
        self.assertIn("claude plugin marketplace update kiln", ctx)
        self.assertIn("/kiln:update all", ctx)
        self.assertIn("only after the user's yes", ctx)

    def test_the_same_version_says_nothing(self):
        e = Env()
        e.cache({"latest": installed_version(), "checked": time.time()})
        self.assertNotIn("is out", e.start())

    def test_a_stale_check_runs_again_in_the_background(self):
        e = Env()
        e.cache({"latest": installed_version(), "checked": time.time() - 2 * 86400})
        e.start()
        for _ in range(100):
            cache = e.cache()
            if cache and cache.get("latest") == "9.9.9":
                break
            time.sleep(0.1)
        self.assertEqual(e.cache()["latest"], "9.9.9")

    def test_switched_off_in_machine_json(self):
        e = Env()
        with open(os.path.join(e.home, "machine.json"), "w", encoding="utf-8") as fh:
            json.dump({"update_check": "off"}, fh)
        e.cache({"latest": "9.9.9", "checked": time.time() - 2 * 86400})
        self.assertNotIn("is out", e.start())
        time.sleep(1.5)
        self.assertLess(e.cache()["checked"], time.time() - 86400)   # no new check started


if __name__ == "__main__":
    unittest.main()
