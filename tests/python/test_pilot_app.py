"""Pilot folder + Pilot Desk end-to-end on SYNTHETIC data (no real responses)."""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from oe import app, collection, pilot, synthetic, validate  # noqa: E402
from oe.common import images_dir, path, read_csv, write_csv  # noqa: E402


def post(url, fields, files=None):
    b = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        for vv in (v if isinstance(v, list) else [v]):
            body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{vv}\r\n'.encode()
    for k, (fn, data) in (files or {}).items():
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\nContent-Type: image/png\r\n\r\n'.encode() + data + b"\r\n"
    body += f"--{b}--\r\n".encode()
    req = Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    return urlopen(req).read().decode()


class TestPilot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.main = cls.tmp / "data"
        synthetic.build(cls.main, seed=3)
        # the synthetic main root is fully "collected"; snapshot it to prove the pilot never touches it
        cls.main_coll_before = path(cls.main, "collection").read_bytes()
        # mark a flagged answer key so the confirmation flow can be exercised
        keys = read_csv(path(cls.main, "answer_key"))
        for k in keys:
            if k["case_id"] == "369":
                k["key_check"] = "REVIEW: published answer has no 'X.' letter prefix"
        write_csv(path(cls.main, "answer_key"), keys, list(keys[0].keys()))
        write_csv(path(cls.main, "answer_key").with_name("answer_key_confirmations.csv"),
                  [{"case_id": "369", "workbook_letter": "A", "issue": "synthetic flag"}],
                  ["case_id", "workbook_letter", "issue", "confirmed_letter", "confirmed_by", "confirmed_date", "evidence_note"])
        # image-arm texts start unapproved for one pilot case to test the review page
        cls.res = pilot.setup(cls.main)
        cls.pr = cls.main / "pilot"
        cls.case = str(cls.res["cases"][0])
        arm = read_csv(path(cls.pr, "image_arm"))
        for a in arm:
            if a["case_id"] == cls.case:
                a.update(status="draft_needs_review", approved_by="")
        write_csv(path(cls.pr, "image_arm"), arm, list(arm[0].keys()))
        from oe import legend
        legend.build_drafts(cls.main)
        app.STATE.update(main=cls.main, pilot=cls.pr)
        app.refresh_prompts()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_1_pilot_selection_and_separation(self):
        self.assertEqual(len(self.res["cases"]), 10)
        sched = read_csv(path(self.pr, "schedule"))
        self.assertEqual(len(sched), 60)
        self.assertTrue(all(s["run_type"] == "Pilot" and s["run_id"].startswith("P-") for s in sched))
        retest = {r["case_id"] for r in read_csv(path(self.main, "schedule")) if r["run_type"] == "Retest"}
        self.assertFalse(set(map(str, self.res["cases"])) & retest)
        self.assertNotIn(369, self.res["cases"])  # flagged key excluded from pilot
        # registry is shared, not copied
        self.assertEqual(path(self.pr, "registry").resolve(), path(self.main, "registry").resolve())
        self.assertEqual(pilot.select_cases(self.main), self.res["cases"])  # reproducible
        pr = read_csv(self.pr / "prompts" / "prompts_P1-standardized.csv")
        self.assertEqual(len(pr), 20)  # 10 cases x 2 inputs, pilot only

    def test_2_image_text_review_and_approval(self):
        html = urlopen(f"{self.url}/image-text/{self.case}").read().decode()
        self.assertIn("<del>", html)
        out = post(f"{self.url}/image-text/{self.case}", {"image_arm_text": "SYNTHETIC approved text (Figure 1 attached).",
                                                          "who": "TST", "decision": "approved", "notes": "t"})
        self.assertIn("Approved for collection", out)
        p = [x for x in read_csv(self.pr / "prompts" / "prompts_P1-standardized.csv") if x["case_id"] == self.case and x["input"] == "text_image"][0]
        self.assertEqual(p["ready"], "Yes")
        self.assertIn("SYNTHETIC approved text", p["prompt_text"])

    def test_3_record_six_runs_with_retry(self):
        sched = sorted([s for s in read_csv(path(self.pr, "schedule")) if s["case_id"] == self.case], key=lambda s: int(s["run_order"]))
        page = urlopen(f"{self.url}/case/{self.case}").read().decode()
        self.assertIn("Copy prompt", page)
        self.assertNotIn("Synthetic Title", page)            # no title on collector page
        self.assertNotIn("Synthetic disorder", page)         # no answer on collector page
        first = sched[0]["run_id"]
        out = post(f"{self.url}/record", {"run_id": first, "status": "completed", "collector": "TST"})
        self.assertIn("Not saved", out)                      # required fields enforced
        out = post(f"{self.url}/record", {"run_id": first, "status": "failed", "collector": "TST", "notes": "wrong model selected"})
        self.assertIn("failed attempt 1", out)
        for s in sched:
            f = {"run_id": s["run_id"], "status": "completed", "collector": "TST", "run_date": "2026-10-02", "run_time": "10:00",
                 "timezone": "America/New_York", "response_duration_s": "12", "citation_count": "4", "source_retrieved": "No",
                 "response_text": "Diagnosis: SYNTHETIC placeholder\nNext step: B\nSYNTHETIC - NOT OPENEVIDENCE OUTPUT",
                 "model_selection_confirmed": "Yes", "new_session_confirmed": "Yes"}
            if s["input"] == "text_image":
                p = [x for x in read_csv(self.pr / "prompts" / "prompts_P1-standardized.csv") if x["case_id"] == self.case and x["input"] == "text_image"][0]
                f["image_ids_uploaded"] = p["image_ids_to_upload"]
            out = post(f"{self.url}/record", f, {"screenshot": ("shot.png", b"\x89PNG fake")})
            self.assertIn("Saved run", out)
        out = post(f"{self.url}/record", {"run_id": first, "status": "failed", "collector": "TST", "notes": "x"})
        self.assertIn("already completed", out)              # no re-runs after completion
        runs = collection.derive_runs(sched, read_csv(path(self.pr, "collection")))
        self.assertTrue(all(r["status"] == "completed" for r in runs.values()))
        self.assertEqual(str(runs[first]["designated"]["attempt_no"]), "2")
        self.assertTrue((self.pr / "collection" / "screenshots" / f"{first}_a2.png").exists())

    def test_4_answer_key_confirmation(self):
        html = urlopen(f"{self.url}/keys").read().decode()
        self.assertIn("Coordinator only", html)
        out = post(f"{self.url}/keys", {"case_id": "369", "letter": "C", "who": "TST", "note": "checked article"})
        self.assertIn("letter C confirmed", out)
        k = [x for x in read_csv(path(self.main, "answer_key")) if x["case_id"] == "369"][0]
        self.assertEqual(k["correct_letter"], "C")
        self.assertTrue(k["key_check"].startswith("CONFIRMED"))

    def test_4b_synonyms(self):
        c = self.case
        out = post(f"{self.url}/synonyms", {"who": "TST", f"syn_{c}": "Synth A; Synth B", f"year_{c}": "2020"})
        self.assertIn("Synonyms saved", out)
        a = [x for x in read_csv(path(self.main, "annotations")) if x["case_id"] == c][0]
        self.assertEqual((a["accepted_dx_synonyms"], a["synonyms_finalized_by"], a["publication_year"]), ("Synth A; Synth B", "TST", "2020"))

    def test_5_export_and_checks(self):
        out = post(f"{self.url}/export", {})
        self.assertIn("6 new response(s)", out)
        pk = list((self.pr / "grading" / "packets").glob("grader_G1_*.csv"))
        self.assertEqual(len(pk), 1)
        rows = read_csv(pk[0])
        self.assertEqual(len(rows), 6)
        self.assertNotIn("model", rows[0])
        # nothing written to the MAIN study folders
        self.assertEqual(path(self.main, "collection").read_bytes(), self.main_coll_before)
        self.assertFalse(any(k["run_id"].startswith("P-") for k in read_csv(path(self.main, "response_key"))))
        r = validate.run(self.pr, "collection", write=False)
        errs = [i for i in r["items"] if i["severity"] == "ERROR"]
        self.assertEqual(errs, [], errs[:5])
        self.assertIn("Quality checks", urlopen(f"{self.url}/checks").read().decode())
        out = post(f"{self.url}/merge", {})
        self.assertIn("6 responses combined", out)

    def test_5b_signoff_clears_items(self):
        post(f"{self.url}/signoff", {"selector_checked_by": "TST", "selector_checked_date": "2026-10-02",
                                     "collectors": "C1", "grader_1": "G1x", "grader_2": "G2x", "adjudicator": "ADJ"})
        st = {i["item"][:20]: i["status"] for i in pilot.readiness(self.pr)}
        self.assertEqual(st["Model selector check"], "ready")
        self.assertEqual(st["Collector(s), two gr"], "ready")

    def test_5c_separation_check_fires_on_leak(self):
        coll = read_csv(path(self.main, "collection"))
        leaked = dict(coll[0], run_id="P-031-C1")
        write_csv(path(self.main, "collection"), coll + [leaked], list(coll[0].keys()))
        try:
            r = validate.run(self.pr, "collection", write=False)
            self.assertTrue(any(i["check"].startswith("C16") for i in r["items"]))
            r2 = validate.run(self.main, "collection", write=False)
            self.assertTrue(any("not in schedule" in i["message"] for i in r2["items"]))
        finally:
            path(self.main, "collection").write_bytes(self.main_coll_before)

    def test_6_pilot_rebuild_refused_after_data(self):
        with self.assertRaises(SystemExit):
            pilot.setup(self.main)


if __name__ == "__main__":
    unittest.main()
