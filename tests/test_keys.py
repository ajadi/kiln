"""Tests for the api-generators keys.py: the key page (`/kiln:settings api`) takes the key in the
browser, checks it against the (fake) service, stores it in the user's key store; status, check
and plan; the key is never printed."""

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(__file__))
from test_gen_api import FakeMeshy  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "api-generators", "scripts", "keys.py")
KEY = "msy_KEYS_SENTINEL_0123456789"


def post(url, body):
    host, port = url.split("/")[2].split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=30)
    try:
        raw = json.dumps(body).encode()
        conn.request("POST", "/" + url.split("/", 3)[3], body=raw,
                     headers={"Content-Type": "application/json", "Content-Length": str(len(raw))})
        return json.loads(conn.getresponse().read())["message"]
    finally:
        conn.close()


class Keys(unittest.TestCase):
    def setUp(self):
        self.fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeMeshy)
        threading.Thread(target=self.fake.serve_forever, daemon=True).start()
        self.home = tempfile.mkdtemp(prefix="kiln-keys-")
        self.env = dict(os.environ, KILN_HOME=self.home, KILN_KEYS_STORE="file",
                        KILN_GEN_FAKE=f"http://127.0.0.1:{self.fake.server_port}")
        self.env.pop("MESHY_API_KEY", None)

    def tearDown(self):
        self.fake.shutdown()

    def run_keys(self, *args):
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], env=self.env, capture_output=True,
                           text=True, timeout=60)
        self.assertNotIn(KEY, p.stdout + p.stderr)
        return p

    def test_the_page(self):
        p = subprocess.Popen([sys.executable, "-B", SCRIPT, "serve", "--no-browser", "--timeout", "60"],
                             env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            url = json.loads(p.stdout.readline())["url"]
            with urllib.request.urlopen(url, timeout=30) as r:
                self.assertIn("keys for paid generators", r.read().decode())
            host, port = url.split("/")[2].split(":")
            conn = http.client.HTTPConnection(host, int(port), timeout=30)
            conn.request("GET", "/")                          # no token, no page
            resp = conn.getresponse()
            self.assertEqual(resp.status, 404)
            resp.read()
            conn.close()
            self.assertIn("works, balance 970",
                          post(url + "act", {"service": "meshy", "act": "check", "key": KEY,
                                             "plan": "pro"}))
            self.assertIn("saved", post(url + "act", {"service": "meshy", "act": "save", "key": KEY,
                                                      "plan": "pro"}))
            post(url + "done", {})
            out, err = p.communicate(timeout=60)
        finally:
            if p.poll() is None:
                p.kill()
        self.assertNotIn(KEY, out + err)
        self.assertTrue([r for r in json.loads(out.strip().splitlines()[-1])["keys"]
                         if r["service"] == "meshy"][0]["key_set"])
        with open(os.path.join(self.home, "keys.env"), encoding="utf-8") as fh:
            self.assertIn(f"MESHY_API_KEY={KEY}", fh.read())
        row = [r for r in json.loads(self.run_keys("status").stdout)["keys"] if r["service"] == "meshy"][0]
        self.assertEqual((row["key_set"], row["plan"]), (True, "pro"))
        self.assertIn("works, balance 970", self.run_keys("check", "meshy").stdout)
        # gen_api.py reads the stored key without a restart (no MESHY_API_KEY in the process)
        gen = os.path.join(os.path.dirname(SCRIPT), "gen_api.py")
        env = {k: v for k, v in self.env.items() if k != "KILN_GEN_FAKE"}
        services = subprocess.run([sys.executable, "-B", gen, "services"], env=env, cwd=self.home,
                                  capture_output=True, text=True, timeout=30).stdout
        self.assertTrue([s for s in json.loads(services)["services"] if s["service"] == "meshy"][0]["key_set"])

    def test_it_stops_when_the_page_is_gone(self):
        # user 2026-10-19: "I just closed the browser" - no Done, no heartbeat: it stops by itself
        p = subprocess.Popen([sys.executable, "-B", SCRIPT, "serve", "--no-browser", "--idle", "3"],
                             env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out, _ = p.communicate(timeout=30)
        finally:
            if p.poll() is None:
                p.kill()
        self.assertEqual(p.returncode, 0)
        self.assertIn('"keys"', out.strip().splitlines()[-1])

    def test_a_refused_key_is_not_saved_and_status_without_a_key(self):
        row = [r for r in json.loads(self.run_keys("status").stdout)["keys"] if r["service"] == "meshy"][0]
        self.assertEqual((row["key_set"], row["plan"]), (False, "unknown"))
        self.assertIn("no key", self.run_keys("check", "meshy").stdout)
        self.env["KILN_GEN_FAKE"] = "http://127.0.0.1:9"          # nothing listens: the check fails
        p = subprocess.Popen([sys.executable, "-B", SCRIPT, "serve", "--no-browser", "--timeout", "60"],
                             env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            url = json.loads(p.stdout.readline())["url"]
            self.assertIn("not saved", post(url + "act", {"service": "meshy", "act": "save", "key": KEY}))
            post(url + "done", {})
            p.communicate(timeout=60)
        finally:
            if p.poll() is None:
                p.kill()
        self.assertFalse(os.path.exists(os.path.join(self.home, "keys.env")))


if __name__ == "__main__":
    unittest.main()
