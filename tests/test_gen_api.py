"""Tests for the api-generators skill's gen_api.py against a local fake of the Meshy API
(shapes from docs.meshy.ai, read 2026-10-19). No real service is called; a sentinel key checks
that no key ever leaks."""

import glob
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "api-generators", "scripts", "gen_api.py")
SENTINEL = "msy_SENTINEL_never_leak_123"


class FakeMeshy(BaseHTTPRequestHandler):
    calls, polls, fail_create = [], {}, {"code": 0}

    def log_message(self, *a):
        pass

    def reply(self, code, obj=None, raw=None, ctype="application/json"):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        FakeMeshy.calls.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path == "/openapi/v1/balance":
            return self.reply(200, {"balance": 970})
        if self.path.startswith("/openapi/v1/image-to-3d/"):
            tid = self.path.rsplit("/", 1)[1]
            n = FakeMeshy.polls[tid] = FakeMeshy.polls.get(tid, 0) + 1
            if n < 2:
                return self.reply(200, {"id": tid, "status": "IN_PROGRESS", "progress": 40})
            base = f"http://127.0.0.1:{self.server.server_port}"
            return self.reply(200, {"id": tid, "status": "SUCCEEDED", "progress": 100,
                                    "consumed_credits": 30,
                                    "model_urls": {"glb": base + "/files/model.glb?Expires=1",
                                                   "fbx": base + "/files/model.fbx"},
                                    "thumbnail_url": base + "/files/preview.png"})
        if self.path.startswith("/openapi/v1/rigging/"):
            base = f"http://127.0.0.1:{self.server.server_port}"
            return self.reply(200, {"id": "rig-7", "type": "rig", "status": "SUCCEEDED",
                                    "progress": 100, "consumed_credits": 5, "result": {
                                        "rigged_character_glb_url": base + "/files/Character_output.glb",
                                        "rigged_character_fbx_url": base + "/files/Character_output.fbx",
                                        "basic_animations": {
                                            "walking_glb_url": base + "/files/walk.glb",
                                            "running_glb_url": base + "/files/run.glb",
                                            "walking_armature_glb_url": base + "/files/wa.glb"}}})
        if self.path.startswith("/openapi/v1/animations/library"):
            return self.reply(200, [{"action_id": 92, "name": "Double Combo Attack", "key": "x",
                                     "category": "Fighting", "sub_category": "A",
                                     "preview_url": "https://cdn/x.gif"}])
        if self.path.startswith("/openapi/v1/animations/"):
            base = f"http://127.0.0.1:{self.server.server_port}"
            return self.reply(200, {"id": "anim-9", "type": "animate", "status": "SUCCEEDED",
                                    "progress": 100, "consumed_credits": 6, "result": {
                                        "animation_glb_url": base + "/files/anim.glb",
                                        "animation_fbx_url": base + "/files/anim.fbx"}})
        if self.path.startswith("/files/"):
            return self.reply(200, raw=b"glTF\x02\x00\x00\x00fake", ctype="application/octet-stream")
        self.reply(404, {"message": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        FakeMeshy.calls.append(("POST", self.path, self.headers.get("Authorization"), body))
        if FakeMeshy.fail_create["code"]:
            return self.reply(FakeMeshy.fail_create["code"], {"message": "upstream error"})
        if self.path == "/openapi/v1/image-to-3d":
            return self.reply(202, {"result": "task-123"})
        if self.path == "/openapi/v1/rigging":
            return self.reply(202, {"result": "rig-7"})
        if self.path == "/openapi/v1/animations":
            return self.reply(202, {"result": "anim-9"})
        self.reply(404, {"message": "not found"})


class GenApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMeshy)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeMeshy.calls.clear()
        FakeMeshy.polls.clear()
        FakeMeshy.fail_create["code"] = 0
        self.root = tempfile.mkdtemp(prefix="kiln-gen-")
        self.home = tempfile.mkdtemp(prefix="kiln-genhome-")
        with open(os.path.join(self.root, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework=kiln\nengine=godot\nmodel_generators=api\n")
        os.makedirs(os.path.join(self.root, "ref"))
        self.image = os.path.join(self.root, "ref", "crate.png")
        with open(self.image, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\nfake")

    def run_gen(self, *args, key=SENTINEL, fake=True):
        env = dict(os.environ, KILN_HOME=self.home)
        env.pop("MESHY_API_KEY", None)
        if key:
            env["MESHY_API_KEY"] = key
        if fake:
            env["KILN_GEN_FAKE"] = self.url
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=self.root, env=env,
                           capture_output=True, text=True, timeout=120)
        self.assertNotIn(SENTINEL, p.stdout + p.stderr)
        return p.returncode, json.loads(p.stdout)

    def estimate(self, *extra):
        code, out = self.run_gen("estimate", "meshy", "image-to-3d", "--asset", "crate",
                                 "--image", self.image, *extra)
        self.assertEqual(code, 0, out)
        return out

    def test_services_say_whether_the_key_is_set_never_its_value(self):
        code, out = self.run_gen("services", key=None, fake=False)
        meshy = [s for s in out["services"] if s["service"] == "meshy"][0]
        self.assertFalse(meshy["key_set"])
        code, out = self.run_gen("services", fake=False)
        self.assertTrue([s for s in out["services"] if s["service"] == "meshy"][0]["key_set"])

    def test_estimate_is_free_and_asks_the_user(self):
        out = self.estimate()
        self.assertEqual(out["credits"], 30)
        self.assertEqual(out["balance_before"], 970)
        self.assertIn("Generate? (yes/no)", out["ask_the_user"])
        self.assertIn("CC BY", out["ask_the_user"])             # plan unknown: the free licence
        self.assertEqual([c[0] for c in FakeMeshy.calls], ["GET"])  # only the balance call
        self.assertEqual(FakeMeshy.calls[0][2], "Bearer kiln-fake-key")  # never the real key

    def test_prices_follow_the_model(self):
        # docs.meshy.ai/api/pricing (2026-10-19): meshy-6-lite and the t2 models cost less
        self.assertEqual(self.estimate("--opt", "ai_model=meshy-6-lite")["credits"], 15)
        self.assertEqual(self.estimate("--opt", "ai_model=meshy-6-lite", "--opt", "texture=false")["credits"], 5)
        self.assertEqual(self.estimate("--opt", "ai_model=meshy-t2.5", "--opt", "texture_resolution=8k")["credits"], 20)
        self.assertEqual(self.estimate("--opt", "geometry_resolution=2k")["credits"], 35)

    def test_full_run_writes_provenance_and_no_key_anywhere(self):
        job = self.estimate()["job"]
        with open(os.path.join(self.root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("gen_spend_cap_usd=1\n")
        code, out = self.run_gen("submit", job)
        self.assertEqual((code, out["state"]), (0, "running"), out)
        posts = [c for c in FakeMeshy.calls if c[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0][3]["image_url"].startswith("data:image/png;base64,"))
        code, out = self.run_gen("status", job, "--wait", "--timeout", "60")
        self.assertEqual(out["state"], "succeeded", out)
        folder = os.path.join(self.root, "art", "generated", "crate")
        self.assertTrue(os.path.isfile(os.path.join(folder, "model.glb")))
        with open(os.path.join(folder, "provenance.json"), encoding="utf-8") as fh:
            prov = json.load(fh)
        self.assertEqual((prov["tool"], prov["remote_task_id"], prov["ai_generated"]),
                         ("meshy", "task-123", True))
        self.assertEqual(prov["cost"]["credits"], 30)
        for path in glob.glob(os.path.join(self.root, "**", "*"), recursive=True):
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    self.assertNotIn(SENTINEL.encode(), fh.read(), path)
        code, out = self.run_gen("submit", job)                  # no second spend on one yes
        self.assertNotEqual(code, 0)

    def test_submit_refusals(self):
        job = self.estimate()["job"]
        with open(os.path.join(self.root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("gen_spend_cap_usd=0.1\n")
        code, out = self.run_gen("submit", job)
        self.assertIn("gen_spend_cap_usd", out["error"])
        with open(os.path.join(self.root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("gen_spend_cap_usd=5\ngen_services=tripo\n")
        code, out = self.run_gen("submit", job)
        self.assertIn("gen_services", out["error"])
        with open(os.path.join(self.root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("gen_services=meshy\n")
        with open(self.image, "ab") as fh:
            fh.write(b"changed")
        code, out = self.run_gen("submit", job)
        self.assertIn("changed since the estimate", out["error"])
        self.assertFalse([c for c in FakeMeshy.calls if c[0] == "POST"])

    def test_a_failed_create_is_never_resent(self):
        job = self.estimate()["job"]
        FakeMeshy.fail_create["code"] = 502
        code, out = self.run_gen("submit", job)
        self.assertNotEqual(code, 0)
        self.assertIn("Not resent", out["error"])
        self.assertEqual(len([c for c in FakeMeshy.calls if c[0] == "POST"]), 1)
        code, out = self.run_gen("submit", job)                  # still refused afterwards
        self.assertNotEqual(code, 0)
        self.assertEqual(len([c for c in FakeMeshy.calls if c[0] == "POST"]), 1)

    def generate(self, *est):
        code, out = self.run_gen("estimate", "meshy", *est)
        self.assertEqual(code, 0, out)
        job = out["job"]
        code, out = self.run_gen("submit", job)
        self.assertEqual(code, 0, out)
        code, out = self.run_gen("status", job, "--wait", "--timeout", "60")
        self.assertEqual(out["state"], "succeeded", out)
        return job, out

    def test_rig_and_animate_chain_from_the_model_job(self):
        model_job, _ = self.generate("image-to-3d", "--asset", "crate", "--image", self.image)
        code, out = self.run_gen("estimate", "meshy", "rigging", "--asset", "crate",
                                 "--from", model_job, "--opt", "height_meters=1.8")
        self.assertEqual((code, out["credits"]), (0, 5), out)     # docs.meshy.ai: rigging 5
        FakeMeshy.calls.clear()
        rig_job, out = self.generate("rigging", "--asset", "crate", "--from", model_job,
                                     "--opt", "height_meters=1.8")
        post = [c for c in FakeMeshy.calls if c[0] == "POST"][0]
        self.assertEqual(post[1], "/openapi/v1/rigging")
        self.assertEqual(post[3], {"input_task_id": "task-123", "height_meters": 1.8})
        rig = os.path.join(self.root, "art", "generated", "crate", "rig")
        for name in ("rigged.glb", "rigged.fbx", "walk.glb", "run.glb", "provenance.json"):
            self.assertTrue(os.path.isfile(os.path.join(rig, name)), name)
        with open(os.path.join(rig, "provenance.json"), encoding="utf-8") as fh:
            prov = json.load(fh)
        self.assertEqual((prov["task"], prov["from_job"]), ("rigging", model_job))
        # animations: 3 credits per action, one merged file with a clip per action
        code, out = self.run_gen("estimate", "meshy", "animations", "--asset", "crate",
                                 "--from", rig_job, "--opt", "actions=92,15")
        self.assertEqual((code, out["credits"]), (0, 6), out)
        FakeMeshy.calls.clear()
        self.generate("animations", "--asset", "crate", "--from", rig_job, "--opt", "actions=92,15")
        post = [c for c in FakeMeshy.calls if c[0] == "POST"][0]
        self.assertEqual(post[3], {"rig_task_id": "rig-7", "action_ids": [92, 15]})
        anim = os.path.join(self.root, "art", "generated", "crate", "anim-92-15")
        self.assertTrue(os.path.isfile(os.path.join(anim, "animation.glb")))

    def test_rig_and_animate_refusals(self):
        model_job, _ = self.generate("image-to-3d", "--asset", "crate", "--image", self.image)
        code, out = self.run_gen("estimate", "meshy", "animations", "--asset", "crate",
                                 "--from", model_job, "--opt", "actions=92")
        self.assertIn("rigging job", out["error"])                # animations need a rig
        code, out = self.run_gen("estimate", "meshy", "rigging", "--asset", "crate")
        self.assertIn("--from", out["error"])                     # nothing to rig
        code, out = self.run_gen("estimate", "meshy", "rigging", "--asset", "crate",
                                 "--from", "meshy-nope")
        self.assertIn("no job", out["error"])
        rig_job, _ = self.generate("rigging", "--asset", "crate", "--from", model_job)
        code, out = self.run_gen("estimate", "meshy", "animations", "--asset", "crate", "--from",
                                 rig_job, "--opt", "actions=" + ",".join(map(str, range(1, 12))))
        self.assertIn("1 to 10", out["error"])
        code, out = self.run_gen("estimate", "meshy", "animations", "--asset", "crate",
                                 "--from", rig_job, "--opt", "actions=5,5")
        self.assertIn("twice", out["error"])
        path = os.path.join(self.root, ".kiln", "gen", "jobs", model_job + ".json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["submitted_at"] -= 4 * 86400                         # Meshy keeps outputs 3 days
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        code, out = self.run_gen("estimate", "meshy", "rigging", "--asset", "crate",
                                 "--from", model_job)
        self.assertIn("3 days", out["error"])

    def test_rig_a_local_glb(self):
        glb = os.path.join(self.root, "art", "hero.glb")
        os.makedirs(os.path.dirname(glb))
        with open(glb, "wb") as fh:
            fh.write(b"glTF\x02\x00\x00\x00hero")
        FakeMeshy.calls.clear()
        self.generate("rigging", "--asset", "hero", "--model", glb)
        body = [c for c in FakeMeshy.calls if c[0] == "POST"][0][3]
        self.assertTrue(body["model_url"].startswith("data:model/gltf-binary;base64,"))

    def test_spend_request_waits_for_the_user(self):
        # Under autopilot an estimate becomes a row in production/SPEND_REQUESTS.md; the user's
        # yes later submits that same job (the estimate is kept for 7 days, inputs unchanged).
        job = self.estimate()["job"]
        code, out = self.run_gen("request", job, "--why", "hero crate for the slice")
        self.assertEqual((code, out["state"]), (0, "requested"), out)
        with open(os.path.join(self.root, "production", "SPEND_REQUESTS.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(job, text)
        self.assertIn("hero crate for the slice", text)
        self.assertIn("| 30 |", text)
        code, out = self.run_gen("request", job, "--why", "again")      # one row per job
        self.assertNotEqual(code, 0)
        path = os.path.join(self.root, ".kiln", "gen", "jobs", job + ".json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["estimated_at"] -= 2 * 86400                               # two days later
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        code, out = self.run_gen("submit", job)
        self.assertEqual((code, out["state"]), (0, "running"), out)
        with open(os.path.join(self.root, "production", "SPEND_REQUESTS.md"), encoding="utf-8") as fh:
            self.assertIn("submitted", fh.read())

    def test_action_library_is_a_free_call(self):
        code, out = self.run_gen("actions", "meshy", "--search", "combo")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["actions"][0]["action_id"], 92)
        self.assertIn("search=combo", FakeMeshy.calls[0][1])
        self.assertFalse([c for c in FakeMeshy.calls if c[0] == "POST"])

    def test_no_key_points_to_settings(self):
        code, out = self.run_gen("balance", "meshy", key=None, fake=False)
        self.assertNotEqual(code, 0)
        self.assertIn("/kiln:settings", out["error"])


    # bug hunt 2026-10-20: ways the caps and the user's no could be got around

    def caps(self, text):
        with open(os.path.join(self.root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write(text)

    def submit_at_once(self, jobs):
        """Submit `jobs` from threads that all reach the daily-cap check before any of them
        reserves (a barrier inside ledger_today), against the local fake Meshy."""
        import argparse
        sys.path.insert(0, os.path.dirname(SCRIPT))
        import gen_api
        env = {"MESHY_API_KEY": "msy_inprocess_test_key_0000", "KILN_GEN_FAKE": self.url,
               "KILN_HOME": self.home}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        # the module reads KILN_GEN_FAKE when imported: point it at the fake here, and refuse
        # any request that would leave this machine
        saved_fake, saved_request = gen_api.FAKE, gen_api.request
        gen_api.FAKE = self.url

        def local_only(method, url, *args, **kwargs):
            if not gen_api.FAKE.startswith("http://127.0.0.1"):
                raise AssertionError(f"a test request would leave the machine: {url}")
            return saved_request(method, url, *args, **kwargs)
        gen_api.request = local_only
        barrier = threading.Barrier(len(jobs), timeout=3)
        orig = gen_api.ledger_today

        def at_once(root):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            return orig(root)
        gen_api.ledger_today = at_once
        results = []

        def go(job):
            try:
                results.append(gen_api.cmd_submit(argparse.Namespace(job=job), self.root))
            except SystemExit as e:
                results.append({"refused": str(e.code)})
        try:
            threads = [threading.Thread(target=go, args=(j,)) for j in jobs]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
        finally:
            gen_api.ledger_today = orig
            gen_api.FAKE, gen_api.request = saved_fake, saved_request
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        return results

    def test_two_submits_at_once_keep_the_cap_and_send_a_job_once(self):
        # KILN-REV-03 (review 2026-10-21): the check and the reservation were not one step, so
        # two $0.60 jobs under a $1 cap both went out, and one job could be sent twice
        self.caps("gen_daily_cap_usd=1\n")
        a, b = self.estimate()["job"], self.estimate()["job"]
        results = self.submit_at_once([a, b])
        self.assertEqual(len(self.posts()), 1, results)
        self.assertEqual(sum("refused" in r for r in results), 1, results)
        self.caps("gen_daily_cap_usd=20\n")
        c = self.estimate()["job"]
        results = self.submit_at_once([c, c])
        self.assertEqual(len(self.posts()), 2, results)                 # one more, not two
        self.assertEqual(sum("refused" in r for r in results), 1, results)

    def posts(self):
        return [c for c in FakeMeshy.calls if c[0] == "POST"]

    def test_a_broken_ledger_line_stops_spending(self):
        self.caps("gen_daily_cap_usd=1\n")
        os.makedirs(os.path.join(self.root, ".kiln", "gen"), exist_ok=True)
        with open(os.path.join(self.root, ".kiln", "gen", "ledger.jsonl"), "w") as fh:
            fh.write("\n")                                           # a blank line is fine
        self.assertEqual(self.run_gen("submit", self.estimate()["job"])[0], 0)   # $0.60
        code, out = self.run_gen("submit", self.estimate()["job"])               # $1.20 > 1
        self.assertIn("gen_daily_cap_usd", out["error"])
        with open(os.path.join(self.root, ".kiln", "gen", "ledger.jsonl"), "a") as fh:
            fh.write("{broken\n")
        code, out = self.run_gen("submit", self.estimate()["job"])
        self.assertIn("does not parse", out["error"])
        self.assertEqual(len(self.posts()), 1)

    def test_an_unknown_submit_counts_against_the_daily_cap(self):
        self.caps("gen_daily_cap_usd=1\n")
        FakeMeshy.fail_create["code"] = 502
        self.run_gen("submit", self.estimate()["job"])
        code, out = self.run_gen("submit", self.estimate()["job"])
        self.assertIn("gen_daily_cap_usd", out["error"])
        self.assertEqual(len(self.posts()), 1)
        FakeMeshy.fail_create["code"] = 400                         # refused: nothing charged
        root2 = self.root
        self.setUp()
        self.caps("gen_daily_cap_usd=1\n")
        FakeMeshy.fail_create["code"] = 400
        self.run_gen("submit", self.estimate()["job"])
        FakeMeshy.fail_create["code"] = 0
        self.assertEqual(self.run_gen("submit", self.estimate()["job"])[0], 0)
        self.assertNotEqual(root2, self.root)

    def test_a_declined_request_cannot_be_submitted(self):
        job = self.estimate()["job"]
        self.run_gen("request", job, "--why", "crate for the dock")
        code, out = self.run_gen("decline", job)
        self.assertEqual(out["state"], "declined")
        with open(os.path.join(self.root, "production", "SPEND_REQUESTS.md"), encoding="utf-8") as fh:
            self.assertIn("declined", fh.read())
        code, out = self.run_gen("submit", job)
        self.assertNotEqual(code, 0)
        job = self.estimate()["job"]
        self.run_gen("request", job, "--why", "again")
        path = os.path.join(self.root, "production", "SPEND_REQUESTS.md")
        text = open(path, encoding="utf-8").read().replace(f"| {job} |", f"| {job} |", 1)
        rows = text.split("\n")
        rows = [r.rsplit("|", 2)[0] + "| declined |" if r.startswith(f"| {job} |") else r
                for r in rows]
        open(path, "w", encoding="utf-8").write("\n".join(rows))      # the row edited by hand
        code, out = self.run_gen("submit", job)
        self.assertIn("declined", out["error"])
        self.assertFalse(self.posts())

    def test_caps_that_are_not_numbers_stop_the_submit(self):
        for value in ("nan", "5$x", "-1"):
            self.setUp()
            self.caps(f"gen_spend_cap_usd={value}\n")
            code, out = self.run_gen("submit", self.estimate()["job"])
            self.assertNotEqual(code, 0, value)
            self.assertIn("gen_spend_cap_usd", out["error"])
        self.assertFalse(self.posts())
        self.setUp()
        self.caps("gen_spend_cap_usd=$5\n")
        self.assertEqual(self.run_gen("submit", self.estimate()["job"])[0], 0)

    def test_status_of_a_job_never_sent_and_a_bad_opt(self):
        job = self.estimate()["job"]
        self.run_gen("request", job, "--why", "x")
        code, out = self.run_gen("status", job)
        self.assertEqual((code, out["state"]), (0, "requested"))
        code, out = self.run_gen("estimate", "meshy", "image-to-3d", "--asset", "c", "--image",
                                 self.image, "--opt", "texture")
        self.assertIn("key=value", out["error"])

    def test_cc_by_output_carries_its_attribution(self):
        job = self.estimate()["job"]
        self.run_gen("submit", job)
        self.run_gen("status", job, "--wait", "--timeout", "60")
        with open(os.path.join(self.root, "art", "generated", "crate", "provenance.json"),
                  encoding="utf-8") as fh:
            prov = json.load(fh)
        self.assertIn("CC BY", prov["attribution"])
        self.assertIn("Meshy", prov["attribution"])


if __name__ == "__main__":
    unittest.main()
