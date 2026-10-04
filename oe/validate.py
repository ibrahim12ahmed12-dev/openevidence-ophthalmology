"""Data validation with a readable issue report.

Stages change severity, not the checks themselves:
  setup       before collection (registry, prompts, schedule, images)
  collection  while runs are being entered
  analysis    before the final analysis (anything incomplete becomes an ERROR)

Reports list IDs and short descriptions only - never answers or case text.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from pathlib import Path

from .build import parse_dt
from .collection import FIELDS as COLL_FIELDS, HELPER, derive_runs
from .common import (images_dir, MODELS, content_tokens, load_config, norm_key, path, read_csv, sha256_file,
                     sha256_text, shingles, write_csv)
from .grading import FORBIDDEN_PACKET_COLUMNS, INTERP_CATEGORIES, read_returns

SEV_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}


class Report:
    def __init__(self, stage: str):
        self.stage = stage
        self.items: list[dict] = []

    def add(self, sev: str, check: str, ref, msg: str):
        self.items.append({"severity": sev, "check": check, "ref": str(ref), "message": msg})

    def sev(self, by_stage: dict) -> str:
        return by_stage.get(self.stage, by_stage.get("default", "WARNING"))


# --------------------------------------------------------------------------- checks

def check_schedule(rep, cfg, reg, sched):
    c = "C01 duplicate runs"
    for rid, n in Counter(s["run_id"] for s in sched).items():
        if n > 1:
            rep.add("ERROR", c, rid, f"run_id appears {n} times in schedule")
    for k, n in Counter((s["run_type"], s["case_id"], s["condition"]) for s in sched).items():
        if n > 1:
            rep.add("ERROR", c, f"{k[1]}/C{k[2]}/{k[0]}", f"case-condition combination scheduled {n} times")
    c = "C02 missing expected runs"
    elig = {r["case_id"] for r in reg if r["eligible"] == "Yes"}
    pilot = cfg.get("pilot")
    main_type = "Pilot" if pilot else "Main"
    have = defaultdict(set)
    for s in sched:
        have[(s["run_type"], s["case_id"])].add(int(s["condition"]))
    for cid in sorted(elig, key=int):
        miss = set(range(1, 7)) - have[(main_type, cid)]
        if miss:
            rep.add("ERROR", c, cid, f"main runs missing for conditions {sorted(miss)}")
    rt_cases = {k[1] for k in have if k[0] == "Retest"}
    for cid in sorted(rt_cases, key=int):
        miss = set(range(1, 7)) - have[("Retest", cid)]
        if miss:
            rep.add("ERROR", c, cid, f"retest runs missing for conditions {sorted(miss)}")
    n_main = sum(s["run_type"] == main_type for s in sched)
    exp_main = len(elig) * 6
    if n_main != exp_main:
        rep.add("ERROR", c, "schedule", f"{n_main} {main_type.lower()} runs scheduled; expected {exp_main} (cases x 6)")
    if any(s["run_type"] not in ("Main", "Retest", "Pilot") for s in sched):
        rep.add("ERROR", c, "schedule", "unknown run_type in schedule")
    if pilot:
        if any(s["run_type"] != "Pilot" for s in sched):
            rep.add("ERROR", "C16 pilot separation", "schedule", "pilot schedule contains non-pilot runs")
    elif any(s["run_type"] == "Pilot" for s in sched):
        rep.add("ERROR", "C16 pilot separation", "schedule", "main schedule contains pilot runs")
    if not pilot and len(rt_cases) != cfg["design"]["retest_n_cases"]:
        rep.add("ERROR", c, "schedule", f"{len(rt_cases)} retest cases; protocol specifies {cfg['design']['retest_n_cases']}")
    if not pilot and len(elig) != cfg["design"]["expected_eligible_cases"]:
        rep.add("WARNING", c, "registry", f"{len(elig)} eligible cases; protocol expects {cfg['design']['expected_eligible_cases']}")
    c = "C03 excluded cases in workflow"
    for s in sched:
        if s["case_id"] not in elig:
            rep.add("ERROR", c, s["run_id"], "run scheduled for an ineligible/unknown case")
    for cid in rt_cases - {k[1] for k in have if k[0] == "Main"}:
        rep.add("ERROR", "C12 retest linkage", cid, "retest case has no main runs scheduled")


def check_registry(rep, root, reg, keys, ann):
    c = "C04 case IDs / option mapping changed"
    lock = read_csv(path(root, "registry_lock"))
    keyd = {k["case_id"]: k for k in keys}
    if not lock:
        rep.add(rep.sev({"setup": "INFO", "default": "WARNING"}), c, "registry",
                "registry not locked yet - run `python -m oe lock-registry` once case text and keys are final")
    else:
        L = {r["case_id"]: r for r in lock}
        cur = {r["case_id"]: r for r in reg}
        scope = set(cur) if any(r.get("_pilot_scope") for r in reg) else set(L) | set(cur)
        for cid in sorted(scope, key=int):
            if cid not in cur:
                rep.add("ERROR", c, cid, "case ID present at lock time has disappeared")
                continue
            if cid not in L:
                rep.add("ERROR", c, cid, "case ID added after lock")
                continue
            for fld, now in (("options_sha256", cur[cid]["options_sha256"]),
                             ("text_only_sha256", cur[cid]["text_only_sha256"]),
                             ("title_sha256", sha256_text(keyd.get(cid, {}).get("case_title", ""))),
                             ("correct_letter", keyd.get(cid, {}).get("correct_letter", "")),
                             ("eligible", cur[cid]["eligible"])):
                if L[cid].get(fld, "") != now:
                    rep.add("ERROR", c, cid, f"{fld} changed since registry lock")
    for r in reg:
        if r["eligible"] == "Yes" and r["n_options"] != "4":
            rep.add("WARNING", c, r["case_id"], f"{r['n_options']} answer options parsed (expected 4)")
    c = "C14 answer key / eligibility review"
    for k in keys:
        cid = k["case_id"]
        elig = next((r["eligible"] for r in reg if r["case_id"] == cid), "")
        chk = k["key_check"].replace("REVIEW: ", "")
        chk = "; ".join(x for x in chk.split("; ") if "typed value" not in x)
        if chk and chk != "OK" and not chk.startswith("CONFIRMED") and elig == "Yes":
            rep.add("WARNING", c, cid, "answer key needs human confirmation: " + chk)
    for r in reg:
        if r["eligible"] != "Yes" and (not r["exclusion_reason"] or "confirm" in r["exclusion_reason"].lower()):
            rep.add("WARNING", c, r["case_id"], f"excluded but reason not confirmed: '{r['exclusion_reason']}'")
        if r["leak_corrected_identical_to_original"] == "Yes":
            rep.add("INFO", c, r["case_id"], "leak-corrected text (col F) is identical to original (col E)")
    annd = {a["case_id"]: a for a in ann}
    miss_syn = [r["case_id"] for r in reg if r["eligible"] == "Yes" and not annd.get(r["case_id"], {}).get("accepted_dx_synonyms", "").strip()]
    if miss_syn:
        rep.add(rep.sev({"setup": "WARNING", "collection": "WARNING", "analysis": "ERROR"}), c,
                f"{len(miss_syn)} cases", "accepted diagnosis synonyms not written (must be fixed before grading): "
                + ", ".join(miss_syn[:20]) + (" ..." if len(miss_syn) > 20 else ""))
    miss_year = [r["case_id"] for r in reg if r["eligible"] == "Yes" and not annd.get(r["case_id"], {}).get("publication_year", "").strip()]
    if miss_year:
        rep.add("WARNING", c, f"{len(miss_year)} cases", "publication year not recorded")


def check_image_arm(rep, reg, arm, runs):
    c = "C06 image-arm text"
    armd = {a["case_id"]: a for a in arm}
    done_image = {r["schedule"]["case_id"] for r in runs.values()
                  if r["schedule"]["input"] == "text_image" and r["status"] == "completed"}
    not_ok = []
    for r in reg:
        if r["eligible"] != "Yes":
            continue
        a = armd.get(r["case_id"], {})
        st = a.get("status", "missing")
        if st != "approved" or not a.get("image_arm_text", "").strip():
            not_ok.append(r["case_id"])
            if r["case_id"] in done_image:
                rep.add("ERROR", c, r["case_id"], f"image-arm run completed but image-arm text status is '{st}'")
        elif norm_key(a["image_arm_text"]) == norm_key(r["text_only_input"]):
            rep.add("WARNING", c, r["case_id"], "approved image-arm text identical to text-only input (legend not removed?)")
        elif a.get("approved_by", "").strip() == "":
            rep.add("WARNING", c, r["case_id"], "image-arm text marked approved without approved_by")
    if not_ok:
        rep.add(rep.sev({"setup": "WARNING", "default": "WARNING", "analysis": "ERROR"}), c, f"{len(not_ok)} cases",
                "image-arm text missing or not approved: " + ", ".join(not_ok[:25]) + (" ..." if len(not_ok) > 25 else ""))


def check_prompts(rep, root, reg, keys):
    c = "C07 answer-key leakage in prompts"
    keyd = {k["case_id"]: k for k in keys}
    for f in sorted((Path(root) / "prompts").glob("prompts_*.csv")):
        for p in read_csv(f):
            txt = p.get("prompt_text", "")
            if not txt or txt.startswith("[NOT READY"):
                continue
            k = keyd.get(p["case_id"], {})
            ref = f"{f.name}:{p['case_id']}/{p['input']}"
            nt = norm_key(txt)
            if k.get("case_title") and norm_key(k["case_title"]) in nt:
                rep.add("WARNING", c, ref, "case title appears in prompt (titles can name the diagnosis) - review")
            dx = norm_key(k.get("reference_diagnosis", ""))
            if len(dx) >= 6 and dx in nt:
                rep.add("WARNING", c, ref, "reference diagnosis appears verbatim in prompt - review")
            if shingles(txt) & shingles(k.get("discussion", "")):
                rep.add("WARNING", c, ref, "prompt shares a >=10-word passage with the article discussion - review")
            if k.get("answer_key_explanation") and shingles(txt) & shingles(k["answer_key_explanation"]):
                rep.add("WARNING", c, ref, "prompt shares a >=10-word passage with the answer explanation (often the explanation quoting the vignette) - review")
            if re.search(r"correct (?:answer|dx|diagnosis|next step)\s*[:=]", txt, re.I):
                rep.add("ERROR", c, ref, "prompt contains an answer-key label")
            if p.get("prompt_sha256") and sha256_text(txt) != p["prompt_sha256"]:
                rep.add("ERROR", c, ref, "prompt text does not match its stored SHA-256 (edited after generation?)")


def check_images(rep, root, reg, keys, images, runs):
    keyd = {k["case_id"]: k for k in keys}
    elig = {r["case_id"] for r in reg if r["eligible"] == "Yes"}
    c8 = "C08 revealing model-input file names"
    c9 = "C09 images"
    by_case = defaultdict(list)
    for i in images:
        by_case[i["case_id"]].append(i)
        k = keyd.get(i["case_id"], {})
        bad = content_tokens(k.get("case_title")) | content_tokens(k.get("reference_diagnosis"))
        for fld in ("prepared_filename", "image_id"):
            toks = set(norm_key(Path(i.get(fld, "")).stem).split())
            hit = sorted(toks & bad)
            if hit:
                rep.add("ERROR", c8, i.get("image_id") or i["case_id"], f"{fld} contains diagnosis/title word(s) {hit}")
        av = (i.get("availability") or "").lower()
        if av not in ("available", "unavailable_video_only", "unavailable_other", ""):
            rep.add("ERROR", c9, i.get("image_id"), f"availability '{i.get('availability')}' not recognised")
        if av == "":
            rep.add(rep.sev({"setup": "WARNING", "default": "WARNING"}), c9, i.get("image_id"), "availability not recorded")
        if av == "available":
            pf = i.get("prepared_filename", "")
            fp = images_dir(root) / pf
            if not pf:
                rep.add("ERROR", c9, i.get("image_id"), "available image has no prepared_filename")
            elif not fp.exists():
                rep.add(rep.sev({"setup": "WARNING", "default": "ERROR"}), c9, i.get("image_id"), f"prepared file not found: images/prepared/{pf}")
            elif i.get("prepared_sha256") and sha256_file(fp) != i["prepared_sha256"]:
                rep.add("ERROR", c9, i.get("image_id"), "prepared file changed since its SHA-256 was recorded")
            elif not i.get("prepared_sha256"):
                rep.add("WARNING", c9, i.get("image_id"), "prepared_sha256 not recorded (run `python -m oe hash-images`)")
            if (i.get("label_or_caption_flag") or "").lower() in ("needs_review", "yes", ""):
                rep.add("WARNING", c9, i.get("image_id"), "caption/label review not signed off (possible diagnosis-revealing text)")
    for cid in sorted(elig, key=int):
        if not by_case.get(cid):
            rep.add(rep.sev({"setup": "WARNING", "default": "WARNING", "analysis": "ERROR"}), c9, cid,
                    "no image metadata for eligible case")
    # consistency of uploaded images across models
    up = defaultdict(dict)
    for rid, r in runs.items():
        s, a = r["schedule"], r["designated"]
        if s["input"] != "text_image":
            continue
        avail = {i["image_id"] for i in by_case.get(s["case_id"], []) if (i.get("availability") or "").lower() == "available"}
        if r["status"] == "completed" and a:
            ids = tuple(sorted(x.strip() for x in (a.get("image_ids_uploaded") or "").split(";") if x.strip()))
            up[(s["case_id"], s["run_type"])][s["model"]] = ids
            if not ids:
                rep.add("ERROR", c9, rid, "image-arm run completed with no image IDs recorded")
            extra = set(ids) - avail
            if extra:
                rep.add("ERROR", c9, rid, f"uploaded image IDs not listed as available for this case: {sorted(extra)}")
            n = (a.get("n_images_uploaded") or "").strip()
            if n and n.isdigit() and int(n) != len(ids):
                rep.add("WARNING", c9, rid, f"n_images_uploaded={n} but {len(ids)} image IDs listed")
        if r["status"] == "unavailable" and avail:
            rep.add("WARNING", c9, rid, "run marked unavailable although prepared images are listed as available")
    for (cid, rt), d in up.items():
        if len(set(d.values())) > 1:
            rep.add("ERROR", c9, f"{cid}/{rt}", "different image sets uploaded across models: "
                    + "; ".join(f"{m}={list(v)}" for m, v in sorted(d.items())))


def check_collection(rep, cfg, root, sched, coll, runs, active_prompts):
    c = "C05 collection log integrity"
    sd = {s["run_id"]: s for s in sched}
    allowed = set(cfg["collection"]["allowed_status"])
    for k, n in Counter((a["run_id"], str(a.get("attempt_no") or "1")) for a in coll).items():
        if n > 1:
            rep.add("ERROR", "C01 duplicate runs", f"{k[0]}#{k[1]}", f"attempt recorded {n} times")
    missing_cols = [f for f in COLL_FIELDS if coll and f not in coll[0]]
    if missing_cols:
        rep.add("ERROR", c, "collection_log.csv", f"columns missing: {missing_cols}")
    prompt_sha = {(p["case_id"], p["input"]): p for p in active_prompts}
    tmax = cfg["collection"]["max_plausible_duration_s"]
    warn = cfg["collection"]["warn_duration_s"]
    start = dt.datetime.fromisoformat(cfg["collection"]["study_start_date"]).replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    for a in coll:
        rid = a["run_id"]
        ref = f"{rid}#{a.get('attempt_no') or 1}"
        s = sd.get(rid)
        if not s:
            rep.add("ERROR", c, ref, "run_id not in schedule")
            continue
        for h in HELPER:
            if h in a and str(a[h]).strip() and str(a[h]).strip() != str(s[h]).strip():
                rep.add("ERROR", c, ref, f"helper column '{h}'='{a[h]}' disagrees with schedule '{s[h]}' (do not edit)")
        st = (a.get("status") or "").strip().lower()
        if not st:
            continue
        if st not in allowed:
            rep.add("ERROR", c, ref, f"status '{a['status']}' not in {sorted(allowed)}")
            continue
        if st in ("failed", "unavailable", "withdrawn") and not (a.get("failure_reason") or a.get("notes")):
            rep.add("WARNING", c, ref, f"status '{st}' without a reason")
        if st != "completed":
            continue
        if not ((a.get("response_text") or "").strip() or (a.get("response_file") or "").strip()):
            rep.add("ERROR", c, ref, "completed without response text or response file")
        if not (a.get("screenshot_path") or "").strip():
            rep.add("WARNING", c, ref, "no screenshot path recorded")
        if not (a.get("collector") or "").strip():
            rep.add("ERROR", c, ref, "collector not recorded")
        for flag in ("model_selection_confirmed", "new_session_confirmed"):
            if (a.get(flag) or "").strip().lower() not in ("yes", "y"):
                rep.add("WARNING", c, ref, f"{flag} not 'Yes'")
        pv = (a.get("prompt_version") or "").strip()
        if not pv:
            rep.add("ERROR", c, ref, "prompt_version not recorded")
        elif pv != cfg["prompt"]["active_version"]:
            rep.add("ERROR", c, ref, f"prompt_version '{pv}' is not the active version '{cfg['prompt']['active_version']}'")
        exp = prompt_sha.get((s["case_id"], s["input"]), {}).get("prompt_sha256", "")
        got = (a.get("prompt_sha256") or "").strip()
        if got and exp and got != exp:
            rep.add("ERROR", c, ref, "prompt_sha256 differs from the generated prompt for this case/input")
        # C13 timestamps / durations
        when = parse_dt(a.get("run_date"), a.get("run_time"), a.get("timezone"))
        if when is None:
            rep.add("ERROR", "C13 timestamps and durations", ref,
                    "date/time/timezone missing or invalid (need YYYY-MM-DD, HH:MM, IANA zone e.g. America/New_York)")
        else:
            if when > now + dt.timedelta(hours=1):
                rep.add("ERROR", "C13 timestamps and durations", ref, "timestamp is in the future")
            if when < start:
                rep.add("ERROR", "C13 timestamps and durations", ref, f"timestamp before study start {cfg['collection']['study_start_date']}")
        d = (a.get("response_duration_s") or "").strip()
        try:
            dv = float(d)
            if dv <= 0 or dv > tmax:
                rep.add("ERROR", "C13 timestamps and durations", ref, f"response duration {d}s outside (0, {tmax}]")
            elif dv > warn.get(s["model"], tmax):
                rep.add("WARNING", "C13 timestamps and durations", ref, f"response duration {d}s unusually long for {s['model']}")
        except ValueError:
            rep.add("ERROR" if d else "WARNING", "C13 timestamps and durations", ref,
                    f"response duration '{d}' not a number" if d else "response duration not recorded")
        cc = (a.get("citation_count") or "").strip()
        if cc and not cc.isdigit():
            rep.add("ERROR", "C13 timestamps and durations", ref, f"citation_count '{cc}' not a non-negative integer")
        if not cc:
            rep.add("WARNING", "C13 timestamps and durations", ref, "citation_count not recorded")
        # C11 retrieval
        sr = (a.get("source_retrieved") or "").strip()
        if sr == "":
            rep.add(rep.sev({"analysis": "ERROR", "default": "WARNING"}), "C11 source-retrieval assessment", ref,
                    "source-retrieval assessment missing (absence of a citation is not evidence of no contamination)")
        elif sr not in ("Yes", "No", "Unclear"):
            rep.add("ERROR", "C11 source-retrieval assessment", ref, f"source_retrieved '{sr}' must be Yes/No/Unclear")
        elif sr == "Unclear":
            rep.add("WARNING", "C11 source-retrieval assessment", ref, "retrieval marked Unclear - resolve before analysis")
    # pending / failed runs
    pend = [rid for rid, r in runs.items() if r["status"] in ("pending", "failed")]
    if pend:
        rep.add(rep.sev({"analysis": "ERROR", "setup": "INFO", "collection": "INFO"}), "C02 missing expected runs",
                f"{len(pend)} runs", "runs pending or failed without a completed retry: " + ", ".join(pend[:15]) + (" ..." if len(pend) > 15 else ""))
    # retests
    c = "C12 retest linkage"
    for rid, r in runs.items():
        s = r["schedule"]
        if s["run_type"] != "Retest":
            continue
        m = runs.get(s.get("linked_main_run_id", ""))
        if not m:
            rep.add("ERROR", c, rid, "retest has no matching main run in the schedule")
            continue
        if r["status"] == "completed":
            if m["status"] != "completed":
                rep.add("ERROR", c, rid, f"retest completed but main run status is '{m['status']}'")
                continue
            t1 = parse_dt(m["designated"].get("run_date"), m["designated"].get("run_time"), m["designated"].get("timezone"))
            t2 = parse_dt(r["designated"].get("run_date"), r["designated"].get("run_time"), r["designated"].get("timezone"))
            if t1 and t2:
                days = (t2 - t1).total_seconds() / 86400
                if days < 0:
                    rep.add("ERROR", c, rid, f"retest run {abs(days):.1f} days BEFORE its main run")
                elif days < cfg["design"]["retest_min_interval_days"]:
                    rep.add("ERROR", c, rid, f"only {days:.1f} days after main run (protocol >= {cfg['design']['retest_min_interval_days']})")


def check_grading(rep, cfg, root, runs, keys, graders):
    c = "C10 grading"
    rkey = read_csv(path(root, "response_key"))
    issued = {(k["run_id"], k["attempt_no"]) for k in rkey}
    ungraded_issue = [rid for rid, r in runs.items() if r["status"] == "completed"
                      and (rid, str(r["designated"].get("attempt_no") or "1")) not in issued]
    if ungraded_issue:
        rep.add(rep.sev({"analysis": "ERROR", "default": "INFO"}), c, f"{len(ungraded_issue)} runs",
                "completed runs not yet issued for grading (run `python -m oe packets`)")
    # packet blinding
    for f in sorted((Path(root) / "grading" / "packets").glob("*.csv")):
        rows = read_csv(f)
        if rows:
            bad = FORBIDDEN_PACKET_COLUMNS & set(rows[0])
            if bad:
                rep.add("ERROR", c, f.name, f"packet contains unblinding columns {sorted(bad)}")
    for f in sorted((Path(root) / "grading" / "packets" / "responses").glob("*.txt")):
        t = f.read_text(encoding="utf-8")
        hit = [m for m in MODELS if re.search(rf"\b{m}\b", t)]
        if hit:
            rep.add("WARNING", c, f.stem, f"response text names model(s) {hit} - grader may be unblinded")
    keyd = {k["case_id"]: k for k in keys}
    rets = read_returns(root)
    for k in rets["duplicates"]:
        rep.add("WARNING", c, f"{k[0]}/{k[1]}", "graded more than once; latest file used")
    case_of = {k["response_id"]: k["case_id"] for k in rkey}
    valid_letters = set(cfg["grading"]["mgmt_letters"]) | set(cfg["grading"]["mgmt_nonanswer_codes"])
    for (rid, g), r in rets["rows"].items():
        ref = f"{rid}/{g or '?'}"
        if g not in graders:
            rep.add("ERROR", c, ref, f"grader_id '{g}' not one of {list(graders)}")
        for col in ("dx_correct", "mgmt_correct", "dx_partial"):
            v = (r.get(col) or "").strip()
            if v not in ("", "0", "1"):
                rep.add("ERROR", c, ref, f"{col}='{v}' must be 0 or 1")
        L = (r.get("mgmt_letter") or "").strip().upper()
        if L and L not in valid_letters:
            rep.add("ERROR", c, ref, f"mgmt_letter '{L}' invalid (use A-D, MULTIPLE or NONE)")
        mc = (r.get("mgmt_correct") or "").strip()
        if mc and not L:
            rep.add("ERROR", c, ref, "mgmt_correct entered without mgmt_letter")
        if L in ("MULTIPLE", "NONE") and mc == "1":
            rep.add("ERROR", c, ref, f"mgmt_letter {L} must be scored 0 per protocol")
        key = keyd.get(case_of.get(rid, ""), {}).get("correct_letter", "")
        if L in ("A", "B", "C", "D") and mc in ("0", "1") and key and (L == key) != (mc == "1"):
            rep.add("ERROR", c, ref, "mgmt_correct inconsistent with recorded letter and answer key")
        if (r.get("dx_partial") or "").strip() == "1" and (r.get("dx_correct") or "").strip() == "1":
            rep.add("WARNING", c, ref, "dx_partial=1 on a response scored fully correct")
    for (rid, g), r in read_returns(root, "interp")["rows"].items():
        if (r.get("interp_category") or "").strip() not in INTERP_CATEGORIES:
            rep.add("ERROR", c, f"{rid}/{g}", f"interp_category '{r.get('interp_category')}' not in {INTERP_CATEGORIES}")
    fin = read_csv(path(root, "grades_final"))
    for o in ("dx", "mgmt"):
        aw = [r["response_id"] for r in fin if r.get(f"{o}_final_source") == "awaiting_grades"]
        ad = [r["response_id"] for r in fin if r.get(f"{o}_final_source") == "awaiting_adjudication"]
        if aw:
            rep.add(rep.sev({"analysis": "ERROR", "default": "INFO"}), "C10 incomplete grading", f"{len(aw)} responses",
                    f"{o}: waiting for one or both grader scores")
        if ad:
            rep.add(rep.sev({"analysis": "ERROR", "default": "WARNING"}), "C10 unresolved disagreements", f"{len(ad)} responses",
                    f"{o}: grader disagreement not yet adjudicated: " + ", ".join(ad[:15]))


def check_analysis_dataset(rep, root):
    rows = read_csv(path(root, "analysis"))
    for r in rows:
        if r["eligible"] != "Yes" and (r["analyzable_dx"] == "1" or r["analyzable_mgmt"] == "1"):
            rep.add("ERROR", "C03 excluded cases in workflow", r["run_id"], "ineligible case marked analysable")
    if rows and any(k.startswith("hist_") for k in rows[0]):
        rep.add("ERROR", "C15 historical data separation", "analysis_dataset.csv", "historical 2026 columns present in new-study dataset")


# --------------------------------------------------------------------------- driver

def run(root, stage: str = "collection", graders=("G1", "G2"), write: bool = True) -> dict:
    cfg = load_config(root)
    rep = Report(stage)
    reg = read_csv(path(root, "registry"))
    keys = read_csv(path(root, "answer_key"))
    ann = read_csv(path(root, "annotations"))
    arm = read_csv(path(root, "image_arm"))
    images = read_csv(path(root, "images"))
    sched = read_csv(path(root, "schedule"))
    coll = read_csv(path(root, "collection"))
    runs = derive_runs(sched, coll)
    active = read_csv(Path(root) / "prompts" / f"prompts_{cfg['prompt']['active_version']}.csv")
    if not reg:
        rep.add("ERROR", "C00 inputs", "registry", "case registry missing - run `python -m oe import`")
    if cfg.get("pilot"):
        ids = {str(c) for c in cfg["pilot"]["case_ids"]}
        reg = [dict(r, _pilot_scope=1) for r in reg if r["case_id"] in ids]
        keys = [k for k in keys if k["case_id"] in ids]
        images = [i for i in images if i["case_id"] in ids]
        # main-study collection folders must stay untouched by the pilot
        main_coll = path(Path(root).resolve().parent, "collection") if Path(root).name == "pilot" else None
        if main_coll and main_coll.exists():
            if any(a["run_id"].startswith("P-") for a in read_csv(main_coll)):
                rep.add("ERROR", "C16 pilot separation", "data/collection", "pilot run IDs found in the MAIN collection log")
    check_schedule(rep, cfg, reg, sched)
    check_registry(rep, root, reg, keys, ann)
    check_image_arm(rep, reg, arm, runs)
    check_prompts(rep, root, reg, keys)
    check_images(rep, root, reg, keys, images, runs)
    check_collection(rep, cfg, root, sched, coll, runs, active)
    check_grading(rep, cfg, root, runs, keys, graders)
    check_analysis_dataset(rep, root)
    items = sorted(rep.items, key=lambda x: (SEV_ORDER[x["severity"]], x["check"], x["ref"]))
    counts = Counter(i["severity"] for i in items)
    if write:
        rd = Path(root) / "reports"
        write_csv(rd / f"validation_issues_{stage}.csv", items, ["severity", "check", "ref", "message"])
        (rd / f"validation_report_{stage}.md").write_text(render_md(items, stage, root, runs), encoding="utf-8")
    return {"counts": dict(counts), "items": items}


def render_md(items, stage, root, runs) -> str:
    counts = Counter(i["severity"] for i in items)
    st = Counter(r["status"] for r in runs.values())
    out = [f"# Validation report - stage: {stage}", "",
           f"Generated {dt.datetime.now().isoformat(timespec='seconds')} for data root `{Path(root).name}`.", "",
           f"**{counts.get('ERROR', 0)} errors, {counts.get('WARNING', 0)} warnings, {counts.get('INFO', 0)} notes.**", "",
           "Run status: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())), "",
           "Errors must be fixed before the next stage. Warnings need a human decision. "
           "The report lists IDs only (no answers or case text).", ""]
    by = defaultdict(list)
    for i in items:
        by[(i["severity"], i["check"])].append(i)
    for (sev, chk), lst in sorted(by.items(), key=lambda kv: (SEV_ORDER[kv[0][0]], kv[0][1])):
        out.append(f"## {sev} - {chk} ({len(lst)})")
        out.append("")
        for i in lst[:15]:
            out.append(f"- `{i['ref']}`: {i['message']}")
        if len(lst) > 15:
            out.append(f"- ... {len(lst) - 15} more in the CSV")
        out.append("")
    if not items:
        out.append("No issues found.")
    return "\n".join(out) + "\n"
