"""Tests for the Python workflow. All fixtures are SYNTHETIC (built by oe.synthetic).

Run:  python -m unittest discover -s tests/python -v
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from oe import build, collection, grading, legend, prompts, schedule, synthetic, validate  # noqa: E402
from oe.common import path, read_csv, sha256_text, write_csv  # noqa: E402
from oe.extract import parse_response  # noqa: E402

_BASE = None


def base_root() -> Path:
    """Build the synthetic root once, then copy it for each test."""
    global _BASE
    if _BASE is None:
        _BASE = Path(tempfile.mkdtemp()) / "base"
        synthetic.build(_BASE, seed=5)
    return _BASE


class SyntheticCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "root"
        shutil.copytree(base_root(), self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers
    def issues(self, stage="analysis", check=None):
        items = validate.run(self.root, stage, write=False)["items"]
        return [i for i in items if check is None or i["check"].startswith(check)]

    def edit(self, key, fn):
        rows = read_csv(path(self.root, key))
        fields = list(rows[0].keys())
        rows = fn(rows) or rows
        write_csv(path(self.root, key), rows, fields)

    def rebuild(self):
        grading.merge(self.root)
        build.build(self.root)


class TestCleanSynthetic(SyntheticCase):
    def test_clean_root_has_no_errors(self):
        errs = [i for i in self.issues() if i["severity"] == "ERROR"]
        self.assertEqual(errs, [], errs[:5])

    def test_unavailable_runs_not_counted_incorrect(self):
        rows = read_csv(path(self.root, "analysis"))
        un = [r for r in rows if r["run_status"] == "unavailable"]
        self.assertTrue(un)
        for r in un:
            self.assertEqual(r["analyzable_dx"], "0")
            self.assertEqual(r["dx_final"], "")


class TestSchedule(unittest.TestCase):
    def test_reproduces_workbook_assignments_from_seeds(self):
        # Facts taken from the workbook Run Log (IDs/orders only, no case content).
        elig = [c for c in range(2, 424) if c != 234]
        rows = schedule.generate(elig, 20261002, 2026, 50)
        case2 = [r["condition"] for r in rows if r["case_id"] == 2 and r["run_type"] == "Main"]
        self.assertEqual(case2, [1, 6, 4, 2, 3, 5])
        rt = sorted({r["case_id"] for r in rows if r["run_type"] == "Retest"})
        self.assertEqual(rt[:10], [3, 7, 41, 43, 47, 52, 54, 58, 62, 109])
        r3 = [r["condition"] for r in rows if r["case_id"] == 3 and r["run_type"] == "Retest"]
        self.assertEqual(r3, [4, 2, 1, 3, 6, 5])
        self.assertEqual(len(rows), 2826)
        self.assertNotIn(234, {r["case_id"] for r in rows})

    def test_retest_links_to_main(self):
        rows = schedule.generate([2, 3, 4, 5], 1, 1, 2)
        for r in rows:
            if r["run_type"] == "Retest":
                self.assertEqual(r["linked_main_run_id"], r["run_id"][:-2])


class TestExtraction(unittest.TestCase):
    OPTS = "A. Observe\n B. Start steroids\n C. Biopsy\n D. Refer"

    def test_standard(self):
        r = parse_response("**Diagnosis:** Toxoplasmosis\n**Next step:** C. Biopsy\nExplanation", self.OPTS)
        self.assertEqual((r["auto_diagnosis"], r["auto_letter"], r["format_complete"]), ("Toxoplasmosis", "C", "Yes"))

    def test_multiple(self):
        self.assertEqual(parse_response("Diagnosis: X\nNext step: B or C", self.OPTS)["auto_letter"], "MULTIPLE")

    def test_missing_format_is_flagged_not_scored(self):
        r = parse_response("The patient likely has X. I would biopsy.", self.OPTS)
        self.assertEqual(r["format_complete"], "No")
        self.assertIn("no 'Next step:' line", r["extraction_flags"])
        self.assertEqual(r["auto_letter"], "")

    def test_text_without_letter(self):
        r = parse_response("Diagnosis: X\nNext step: Biopsy", self.OPTS)
        self.assertEqual(r["auto_letter"], "")
        self.assertIn("resembles option C", r["extraction_flags"])


class TestPrompts(SyntheticCase):
    def test_deterministic_and_no_title(self):
        prompts.generate(self.root)
        a = read_csv(self.root / "prompts" / "prompts_P1-standardized.csv")
        prompts.generate(self.root)
        b = read_csv(self.root / "prompts" / "prompts_P1-standardized.csv")
        self.assertEqual([x["prompt_sha256"] for x in a], [x["prompt_sha256"] for x in b])
        keys = {k["case_id"]: k for k in read_csv(path(self.root, "answer_key"))}
        for p in a:
            self.assertNotIn(keys[p["case_id"]]["case_title"], p["prompt_text"])
            self.assertNotIn("JAMA", p["prompt_text"])  # source-exclusion off by default
        self.assertTrue(a[0]["prompt_text"].endswith('"Next step: <letter>".'))

    def test_options_preserved_verbatim(self):
        reg = {r["case_id"]: r for r in read_csv(path(self.root, "registry"))}
        for p in read_csv(self.root / "prompts" / "prompts_P1-standardized.csv")[:20]:
            self.assertIn(reg[p["case_id"]]["answer_options"], p["prompt_text"])

    def test_unapproved_image_text_not_generated(self):
        self.edit("image_arm", lambda rows: [dict(r, status="draft_needs_review") if r["case_id"] == "5" else r for r in rows])
        prompts.generate(self.root)
        p = [x for x in read_csv(self.root / "prompts" / "prompts_P1-standardized.csv") if x["case_id"] == "5" and x["input"] == "text_image"][0]
        self.assertEqual(p["ready"], "No")
        self.assertTrue(p["prompt_text"].startswith("[NOT READY"))
        iss = self.issues("analysis", "C06")
        self.assertTrue(any(i["ref"] == "5" and i["severity"] == "ERROR" for i in iss))

    def test_source_exclusion_toggle(self):
        prompts.generate(self.root, settings_override={"include_source_exclusion_instruction": True})
        p = read_csv(self.root / "prompts" / "prompts_P1-standardized.csv")[0]
        self.assertIn("Do not search for, use, or cite JAMA", p["prompt_text"])


class TestLegendDraft(unittest.TestCase):
    def test_trailing_legend_removed_and_nonvisual_flagged(self):
        t = ("A 60-year-old man presented with blurred vision (Figure 1).\n"
             " Examination findings were otherwise unremarkable.\n"
             " A, Fundus photograph of the right eye 2 weeks later showing a yellow lesion (arrowheads).")
        d = legend.draft_for_text(t)
        self.assertEqual(d["n_removed"], 1)
        self.assertNotIn("yellow lesion", d["draft_image_arm_text"])
        self.assertIn("(Figure 1 attached)", d["draft_image_arm_text"])
        self.assertIn("laterality", d["nonvisual_details_in_removed"])
        self.assertIn("timing", d["nonvisual_details_in_removed"])

    def test_first_paragraph_never_removed(self):
        d = legend.draft_for_text("Fundus photograph shows a lesion.")
        self.assertEqual(d["n_removed"], 0)
        self.assertIn("no trailing legend", d["review_flags"])


class TestGradingBlinding(SyntheticCase):
    def test_packets_have_no_unblinding_columns_and_independent_order(self):
        pk = self.root / "grading" / "packets"
        g1 = read_csv(pk / "grader_G1_batch_SYN001.csv")
        g2 = read_csv(pk / "grader_G2_batch_SYN001.csv")
        self.assertFalse(grading.FORBIDDEN_PACKET_COLUMNS & set(g1[0]))
        self.assertEqual(sorted(x["response_id"] for x in g1), sorted(x["response_id"] for x in g2))
        self.assertNotEqual([x["response_id"] for x in g1], [x["response_id"] for x in g2])
        self.assertTrue(all(x["response_id"].startswith("RSP-") for x in g1))
        self.assertFalse(any("dx_g2" in k or "G2" == x.get("grader_id") for x in g1 for k in x))

    def test_response_files_contain_only_response(self):
        f = next((self.root / "grading" / "packets" / "responses").glob("*.txt"))
        txt = f.read_text()
        for word in ("Osler", "Sackett", "Snow", "text_image", "Main"):
            self.assertNotIn(word, txt)

    def test_incremental_packets_reuse_ids(self):
        before = read_csv(path(self.root, "response_key"))
        r = grading.make_packets(self.root, seed=99, batch="SYN002")
        after = read_csv(path(self.root, "response_key"))
        self.assertEqual(r["new_response_ids"], 0)
        self.assertEqual(r["per_grader"]["G1"], {"primary": 0, "interp": 0})  # nothing new issued
        self.assertEqual(before, after)

    def test_disagreement_requires_adjudication_and_keeps_scores(self):
        (self.root / "grading" / "adjudication" / "adjudication_return.csv").unlink()
        res = grading.merge(self.root)
        self.assertGreater(res["awaiting_adjudication"], 0)
        fin = read_csv(path(self.root, "grades_final"))
        dis = [r for r in fin if r["dx_final_source"] == "awaiting_adjudication"]
        self.assertTrue(dis)
        self.assertTrue(all(r["dx_g1"] != r["dx_g2"] and r["dx_final"] == "" for r in dis))
        build.build(self.root)
        iss = self.issues("analysis", "C10 unresolved")
        self.assertTrue(iss and iss[0]["severity"] == "ERROR")


class TestValidationChecks(SyntheticCase):
    """Each test plants one SYNTHETIC defect and asserts the matching check fires."""

    def assertFires(self, check, ref_sub="", sev=None, stage="analysis", msg_sub=""):
        iss = self.issues(stage, check)
        hit = [i for i in iss if ref_sub in i["ref"] and msg_sub in i["message"] and (sev is None or i["severity"] == sev)]
        self.assertTrue(hit, f"{check} did not fire; got {iss[:3]}")

    def test_duplicate_run_ids_and_case_condition(self):
        s = read_csv(path(self.root, "schedule"))
        s.append(dict(s[0]))
        dup = dict(s[1]); dup["run_id"] = "XXX-C9"
        s.append(dup)
        write_csv(path(self.root, "schedule"), s, list(s[0].keys()))
        self.assertFires("C01", s[0]["run_id"], "ERROR", msg_sub="appears 2 times")
        self.assertFires("C01", msg_sub="case-condition combination scheduled 2 times")

    def test_missing_expected_runs(self):
        s = [r for r in read_csv(path(self.root, "schedule")) if r["run_id"] != "002-C3"]
        write_csv(path(self.root, "schedule"), s, list(s[0].keys()))
        self.assertFires("C02", "2", "ERROR", msg_sub="[3]")

    def test_pending_runs_error_at_analysis(self):
        self.edit("collection", lambda rows: [dict(r, status="") if r["run_id"] == "010-C1" else r for r in rows])
        self.assertFires("C02", "runs", "ERROR", msg_sub="010-C1")
        self.assertFires("C02", "runs", "INFO", stage="collection")

    def test_excluded_case_in_schedule(self):
        s = read_csv(path(self.root, "schedule"))
        bad = dict(s[0]); bad.update(run_id="234-C1", case_id="234")
        s.append(bad)
        write_csv(path(self.root, "schedule"), s, list(s[0].keys()))
        self.assertFires("C03", "234-C1", "ERROR")

    def test_changed_options_and_case_id(self):
        self.edit("registry", lambda rows: [dict(r, options_sha256="changed") if r["case_id"] == "7" else r for r in rows])
        self.assertFires("C04", "7", "ERROR", msg_sub="options_sha256")
        self.edit("registry", lambda rows: [dict(r, case_id="999") if r["case_id"] == "8" else r for r in rows])
        self.assertFires("C04", "999", "ERROR", msg_sub="added after lock")
        self.assertFires("C04", "8", "ERROR", msg_sub="disappeared")

    def test_answer_key_leak_in_prompt(self):
        p = self.root / "prompts" / "prompts_P1-standardized.csv"
        rows = read_csv(p)
        rows[0]["prompt_text"] += " Correct answer: B"
        rows[1]["prompt_text"] = rows[1]["prompt_text"].replace("SYNTHETIC case", "Synthetic Title " + rows[1]["case_id"] + " SYNTHETIC case")
        write_csv(p, rows, list(rows[0].keys()))
        self.assertFires("C07", rows[0]["case_id"], "ERROR", msg_sub="answer-key label")
        self.assertFires("C07", rows[0]["case_id"], "ERROR", msg_sub="SHA-256")
        self.assertFires("C07", rows[1]["case_id"], "WARNING", msg_sub="case title")

    def test_revealing_image_filename(self):
        self.edit("images", lambda rows: [dict(r, prepared_filename="synthetic_disorder_12.png") if r["image_id"] == "IMG-012-1" else r for r in rows])
        self.assertFires("C08", "IMG-012-1", "ERROR", msg_sub="diagnosis/title word")

    def test_missing_and_inconsistent_images(self):
        (self.root / "images" / "prepared" / "IMG-013-1.png").unlink()
        self.assertFires("C09", "IMG-013-1", "ERROR", msg_sub="not found")
        def tweak(rows):
            for r in rows:
                if r["run_id"] == "014-C4" and r["status"] == "completed":
                    r["image_ids_uploaded"] = "IMG-014-1;IMG-999-9"
        self.edit("collection", tweak)
        self.assertFires("C09", "14/Main", "ERROR", msg_sub="different image sets")
        self.assertFires("C09", "014-C4", "ERROR", msg_sub="not listed as available")

    def test_changed_image_file_hash(self):
        (self.root / "images" / "prepared" / "IMG-015-1.png").write_bytes(b"different")
        self.assertFires("C09", "IMG-015-1", "ERROR", msg_sub="changed since")

    def test_invalid_management_letters_and_multiple(self):
        f = self.root / "grading" / "returns" / "grader_G1_batch_SYN001.csv"
        rows = read_csv(f)
        rows[0]["mgmt_letter"] = "E"
        rows[1]["mgmt_letter"], rows[1]["mgmt_correct"] = "MULTIPLE", "1"
        key = {k["case_id"]: k["correct_letter"] for k in read_csv(path(self.root, "answer_key"))}
        rows[2]["mgmt_letter"] = key[rows[2]["case_id"]]; rows[2]["mgmt_correct"] = "0"
        write_csv(f, rows, list(rows[0].keys()))
        self.assertFires("C10", rows[0]["response_id"], "ERROR", msg_sub="invalid")
        self.assertFires("C10", rows[1]["response_id"], "ERROR", msg_sub="must be scored 0")
        self.assertFires("C10", rows[2]["response_id"], "ERROR", msg_sub="inconsistent")

    def test_incomplete_grading(self):
        f = self.root / "grading" / "returns" / "grader_G2_batch_SYN001.csv"
        rows = read_csv(f)
        for r in rows[:5]:
            r["dx_correct"] = ""
        write_csv(f, rows, list(rows[0].keys()))
        self.rebuild()
        self.assertFires("C10 incomplete", "", "ERROR", msg_sub="dx")

    def test_missing_retrieval_assessment(self):
        def t(rows):
            for r in rows:
                if r["run_id"] == "020-C5" and r["status"] == "completed":
                    r["source_retrieved"] = ""
        self.edit("collection", t)
        self.assertFires("C11", "020-C5", "ERROR")
        self.assertFires("C11", "020-C5", "WARNING", stage="collection")

    def test_retest_interval_and_linkage(self):
        rt = [r for r in read_csv(path(self.root, "schedule")) if r["run_type"] == "Retest"][0]
        main_id = rt["linked_main_run_id"]
        main_row = [r for r in read_csv(path(self.root, "collection")) if r["run_id"] == main_id and r["status"] == "completed"][0]
        def t(rows):
            for r in rows:
                if r["run_id"] == rt["run_id"] and r["status"] == "completed":
                    r["run_date"], r["run_time"] = main_row["run_date"], "23:59"
        self.edit("collection", t)
        self.assertFires("C12", rt["run_id"], "ERROR", msg_sub="days after main")
        s = read_csv(path(self.root, "schedule"))
        s = [dict(r, linked_main_run_id="NOPE-C1") if r["run_id"] == rt["run_id"] else r for r in s]
        write_csv(path(self.root, "schedule"), s, list(s[0].keys()))
        self.assertFires("C12", rt["run_id"], "ERROR", msg_sub="no matching main run")

    def test_invalid_timestamps_and_durations(self):
        def t(rows):
            for r in rows:
                if r["status"] != "completed":
                    continue
                if r["run_id"] == "030-C1":
                    r["run_date"] = "2026-13-45"
                if r["run_id"] == "031-C1":
                    r["run_date"] = "2099-01-01"
                if r["run_id"] == "032-C1":
                    r["response_duration_s"] = "-3"
                if r["run_id"] == "033-C1":
                    r["response_duration_s"] = "fast"
                if r["run_id"] == "034-C1":
                    r["timezone"] = "Mars/Olympus"
        self.edit("collection", t)
        for rid, m in [("030-C1", "invalid"), ("031-C1", "future"), ("032-C1", "outside"), ("033-C1", "not a number"), ("034-C1", "invalid")]:
            self.assertFires("C13", rid, "ERROR", msg_sub=m)

    def test_collection_integrity(self):
        def t(rows):
            for r in rows:
                if r["run_id"] == "040-C2" and r["status"] == "completed":
                    r["model"] = "Snow"            # helper column edited
                if r["run_id"] == "041-C2" and r["status"] == "completed":
                    r["status"] = "done"           # invalid status
                if r["run_id"] == "042-C2" and r["status"] == "completed":
                    r["prompt_version"] = "P0-natural"
            rows.append(dict(rows[0]))             # duplicate attempt
        self.edit("collection", t)
        self.assertFires("C05", "040-C2", "ERROR", msg_sub="helper column")
        self.assertFires("C05", "041-C2", "ERROR", msg_sub="not in")
        self.assertFires("C05", "042-C2", "ERROR", msg_sub="not the active version")
        self.assertFires("C01", "#", "ERROR", msg_sub="attempt recorded 2 times")

    def test_failed_attempt_retry_designation(self):
        sched = read_csv(path(self.root, "schedule"))
        coll = read_csv(path(self.root, "collection"))
        runs = collection.derive_runs(sched, coll)
        retried = [r for r in runs.values() if r["n_attempts"] == 2]
        self.assertTrue(retried)
        for r in retried:
            self.assertEqual(r["status"], "completed")
            self.assertEqual(str(r["designated"]["attempt_no"]), "2")


class TestRealWorkbookCrosscheck(unittest.TestCase):
    """Runs only when the real workbook has been imported into data/ (never in CI)."""

    def test_generator_matches_workbook_prompts(self):
        root = REPO / "data"
        if not (root / "registry" / "workbook_prompts_cached_PRIVATE.csv").exists():
            self.skipTest("real workbook not imported on this machine")
        r = prompts.crosscheck_workbook(root)
        self.assertEqual(r["identical"], r["total"], r["different_case_ids"][:10])

    def test_real_schedule_matches_seeds(self):
        root = REPO / "data"
        if not path(root, "workbook_schedule").exists():
            self.skipTest("real workbook not imported on this machine")
        self.assertTrue(schedule.build(root)["reproducible"])


if __name__ == "__main__":
    unittest.main()
