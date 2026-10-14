"""10-case pilot: a SEPARATE data root that shares the main registry.

* Pilot runs live in data/pilot/ (schedule, prompts, collection log, grading,
  reports). Nothing is written to the main collection log or grading folders,
  so pilot responses cannot leak into the main analysis.
* Registry files (case text, keys, image-arm text, images, synonyms) are
  shared with data/, so preparation done for the pilot carries over.
* Pilot run IDs are 'P-NNN-Ck' with run_type 'Pilot'. Within-case order is the
  same randomized order as the main schedule.
* Whether pilot cases are re-run in the main study, and whether any pilot
  responses may be used, is decision D19 (default: pilot responses are never
  analysed with main-study data).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from . import prompts
from .common import ensure_dirs, images_dir, load_config, path, read_csv, write_csv
from .schedule import FIELDS as SCHED_FIELDS

PILOT_SEED = 20261004
README = """# PILOT DATA - kept separate from the main study

Created by `python -m oe pilot-setup`. Responses recorded here are pilot data.
They are never merged into data/collection or analysed with main-study runs
unless the team records that decision (DECISION_LOG D19).
"""


def key_ok(check: str) -> bool:
    """True when the answer key needs no human confirmation (or has been confirmed)."""
    if check.startswith("CONFIRMED"):
        return True
    rest = [x for x in check.replace("REVIEW: ", "").split("; ") if x and x != "OK" and "typed value" not in x]
    return not rest


def select_cases(main_root, n: int = 10, seed: int = PILOT_SEED) -> list[int]:
    """Seeded random choice among eligible cases, excluding retest-subset cases and
    cases whose answer key awaits confirmation."""
    reg = read_csv(path(main_root, "registry"))
    keys = {k["case_id"]: k for k in read_csv(path(main_root, "answer_key"))}
    sched = read_csv(path(main_root, "schedule"))
    retest = {r["case_id"] for r in sched if r["run_type"] == "Retest"}
    pool = [int(r["case_id"]) for r in reg if r["eligible"] == "Yes" and r["case_id"] not in retest
            and key_ok(keys.get(r["case_id"], {}).get("key_check", "OK"))]
    return sorted(random.Random(seed).sample(sorted(set(pool)), n))


def setup(main_root, pilot_root=None, case_ids=None, n: int = 10, seed: int = PILOT_SEED) -> dict:
    main_root = Path(main_root)
    pilot_root = Path(pilot_root or main_root / "pilot")
    if (pilot_root / "collection" / "collection_log.csv").exists() and any(
            (r.get("status") or "").strip() for r in read_csv(pilot_root / "collection" / "collection_log.csv")):
        raise SystemExit("Pilot already has recorded runs; refusing to rebuild. Delete data/pilot deliberately to start over.")
    cases = sorted(int(c) for c in case_ids) if case_ids else select_cases(main_root, n, seed)
    ensure_dirs(pilot_root)
    rel = Path("..") if pilot_root.parent.resolve() == main_root.resolve() else main_root.resolve()
    (pilot_root / "config_override.json").write_text(json.dumps({
        "shared_registry_root": str(rel),
        "pilot": {"case_ids": cases, "selection_seed": seed if not case_ids else None,
                  "selection_rule": "seeded random; eligible; not in retest subset; answer key not awaiting confirmation"
                  if not case_ids else "chosen by hand"}}, indent=2), encoding="utf-8")
    (pilot_root / "PILOT_README.md").write_text(README, encoding="utf-8")
    main = [r for r in read_csv(path(main_root, "schedule")) if r["run_type"] == "Main" and int(r["case_id"]) in cases]
    rows = []
    for r in main:
        rows.append({**r, "run_id": "P-" + r["run_id"], "run_type": "Pilot", "linked_main_run_id": "",
                     "retest_min_interval_days": "", "assignment_source": "main schedule order (pilot copy)"})
    write_csv(path(pilot_root, "schedule"), rows, SCHED_FIELDS)
    prompts.generate(pilot_root)
    from . import collection
    collection.init_log(pilot_root)
    return {"pilot_root": str(pilot_root), "cases": cases, "runs": len(rows)}


def pilot_cases(pilot_root) -> list[str]:
    cfg = load_config(pilot_root)
    return [str(c) for c in cfg.get("pilot", {}).get("case_ids", [])]


def signoff(pilot_root) -> dict:
    p = Path(pilot_root) / "pilot_signoff.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_signoff(pilot_root, values: dict) -> dict:
    cur = signoff(pilot_root)
    cur.update({k: v.strip() for k, v in values.items() if isinstance(v, str)})
    (Path(pilot_root) / "pilot_signoff.json").write_text(json.dumps(cur, indent=2), encoding="utf-8")
    return cur


def readiness(pilot_root) -> list[dict]:
    """Plain-language checklist: status is 'ready', 'blocking' (before collection)
    or 'before grading'."""
    cases = pilot_cases(pilot_root)
    cfg = load_config(pilot_root)
    arm = {a["case_id"]: a for a in read_csv(path(pilot_root, "image_arm"))}
    imgs = read_csv(path(pilot_root, "images"))
    ann = {a["case_id"]: a for a in read_csv(path(pilot_root, "annotations"))}
    keys = {k["case_id"]: k for k in read_csv(path(pilot_root, "answer_key"))}
    pr = read_csv(Path(pilot_root) / "prompts" / f"prompts_{cfg['prompt']['active_version']}.csv")
    out = []

    def item(name, ok, detail, when="blocking"):
        out.append({"item": name, "status": "ready" if ok else when, "detail": detail})

    item("Prompt settings recorded (source-exclusion OFF, answer lines at top)",
         not cfg["prompt"]["include_source_exclusion_instruction"] and cfg["prompt"]["include_answer_format_line"],
         f"prompt version {cfg['prompt']['active_version']}")
    t_ok = [p["case_id"] for p in pr if p["input"] == "text_only" and p["ready"] == "Yes"]
    item("Text-only prompts generated", len(t_ok) == len(cases), f"{len(t_ok)}/{len(cases)} cases")
    appr = [c for c in cases if arm.get(c, {}).get("status") == "approved" and arm[c].get("approved_by")]
    item("Image-arm text reviewed and approved", len(appr) == len(cases),
         f"{len(appr)}/{len(cases)} approved; waiting: {', '.join(c for c in cases if c not in appr) or 'none'}")
    have_img = []
    for c in cases:
        ci = [i for i in imgs if i["case_id"] == c]
        av = [i for i in ci if (i.get("availability") or "").lower() == "available"]
        unav = [i for i in ci if (i.get("availability") or "").lower().startswith("unavailable")]
        files_ok = all(i.get("prepared_filename") and (images_dir(pilot_root) / i["prepared_filename"]).exists()
                       and i.get("prepared_sha256") and i.get("modality") and i.get("label_or_caption_flag") == "cleared"
                       for i in av)
        if (av and files_ok) or (unav and not av):
            have_img.append(c)
    item("Images prepared, described and caption-checked", len(have_img) == len(cases),
         f"{len(have_img)}/{len(cases)} cases complete; waiting: {', '.join(c for c in cases if c not in have_img) or 'none'}")
    i_ok = [p["case_id"] for p in pr if p["input"] == "text_image" and p["ready"] == "Yes"]
    item("Image-arm prompts ready", len(i_ok) == len(cases), f"{len(i_ok)}/{len(cases)} cases")
    flagged = [c for c in cases if not key_ok(keys.get(c, {}).get("key_check", "OK"))]
    item("Answer keys of pilot cases confirmed", not flagged, f"needing confirmation: {', '.join(flagged) or 'none'}")
    syn = [c for c in cases if ann.get(c, {}).get("accepted_dx_synonyms", "").strip()]
    item("Accepted diagnosis synonyms written", len(syn) == len(cases),
         f"{len(syn)}/{len(cases)} cases", when="before grading")
    so = signoff(pilot_root)
    item("Model selector checked (Osler, Sackett, Snow visible; image upload works)", bool(so.get("selector_checked_by")),
         f"checked by {so['selector_checked_by']} on {so.get('selector_checked_date', '')}" if so.get("selector_checked_by")
         else "use the sign-off form at the bottom of the home page")
    people = all(so.get(k) for k in ("collectors", "grader_1", "grader_2", "adjudicator"))
    item("Collector(s), two graders and adjudicator named", people,
         (f"collectors {so.get('collectors')}; graders {so.get('grader_1')}, {so.get('grader_2')}; adjudicator {so.get('adjudicator')}")
         if people else "use the sign-off form at the bottom of the home page")
    return out
