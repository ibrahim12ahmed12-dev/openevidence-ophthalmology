"""Blinded grading: neutral response IDs, per-grader packets, merge, adjudication.

Blinding rules implemented here
* Packets never contain model, input, condition, run type, run ID, collector,
  dates, durations or citation counts. The run link lives only in
  grading/private/response_key_PRIVATE.csv (coordinator only).
* Each grader gets their OWN packet file, independently shuffled, with no
  column for the other grader's score. Scores are compared only after both
  return their files; the adjudicator then sees both scores and reasons.
* Image-interpretation grading needs the images, so it is a separate packet
  limited to image-arm responses (input is necessarily unblinded there).
"""
from __future__ import annotations

import datetime as dt
import random
import secrets
from pathlib import Path

from .collection import derive_runs
from .common import load_config, path, read_csv, write_csv
from .extract import parse_response

FORBIDDEN_PACKET_COLUMNS = {"model", "input", "condition", "run_id", "run_type", "collector",
                            "run_date", "run_time", "timezone", "response_duration_s",
                            "citation_count", "source_retrieved", "attempt_no", "run_order",
                            "prompt_version", "image_ids_uploaded", "n_images_uploaded"}
PACKET_FIELDS = [
    "response_id", "case_id", "reference_diagnosis", "accepted_dx_synonyms", "answer_options",
    "correct_letter", "auto_diagnosis", "auto_letter", "extraction_flags", "response_file",
    # grader fills:
    "grader_id", "extracted_diagnosis_confirmed", "dx_correct", "dx_partial", "dx_reason",
    "mgmt_letter", "mgmt_correct", "mgmt_reason", "flag_for_discussion", "graded_date",
]
INTERP_FIELDS = ["response_id", "case_id", "image_files", "response_file",
                 "grader_id", "interp_category", "interp_reason", "graded_date"]
INTERP_CATEGORIES = ["Correct", "Partly correct", "Incorrect", "Invented findings", "Not described"]
OUTCOMES = {"dx": "dx_correct", "mgmt": "mgmt_correct", "partial": "dx_partial"}


def _new_id(rng: random.Random | None, used: set[str]) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        tok = "".join((rng.choice(alphabet) if rng else secrets.choice(alphabet)) for _ in range(6))
        rid = "RSP-" + tok
        if rid not in used:
            return rid


def _response_text(root: Path, attempt: dict) -> str:
    if (attempt.get("response_text") or "").strip():
        return attempt["response_text"]
    f = (attempt.get("response_file") or "").strip()
    if f:
        p = Path(f) if Path(f).is_absolute() else root / f
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


def make_packets(root, graders=("G1", "G2"), seed: int | None = None, batch: str | None = None) -> dict:
    """Issue packets for every completed (designated) response not yet issued to each grader."""
    root = Path(root)
    cfg = load_config()
    rng = random.Random(seed) if seed is not None else None
    runs = derive_runs(read_csv(path(root, "schedule")), read_csv(path(root, "collection")))
    keyf = path(root, "response_key")
    rkey = read_csv(keyf)
    by_run = {(k["run_id"], k["attempt_no"]): k for k in rkey}
    used = {k["response_id"] for k in rkey}
    ans = {a["case_id"]: a for a in read_csv(path(root, "answer_key"))}
    ann = {a["case_id"]: a for a in read_csv(path(root, "annotations"))}
    reg = {r["case_id"]: r for r in read_csv(path(root, "registry"))}
    resp_dir = root / "grading" / "packets" / "responses"
    resp_dir.mkdir(parents=True, exist_ok=True)
    extraction = {e["response_id"]: e for e in read_csv(path(root, "extraction"))}
    new_ids = 0
    for rid_run, r in runs.items():
        a = r["designated"]
        if not a:
            continue
        k = (rid_run, str(a.get("attempt_no") or "1"))
        if k not in by_run:
            rid = _new_id(rng, used)
            used.add(rid)
            entry = {"response_id": rid, "run_id": rid_run, "attempt_no": k[1],
                     "case_id": r["schedule"]["case_id"], "issued_at": dt.datetime.now().isoformat(timespec="seconds")}
            rkey.append(entry)
            by_run[k] = entry
            new_ids += 1
        rid = by_run[k]["response_id"]
        text = _response_text(root, a)
        (resp_dir / f"{rid}.txt").write_text(text, encoding="utf-8")
        cid = r["schedule"]["case_id"]
        extraction[rid] = {"response_id": rid, "run_id": rid_run, "case_id": cid,
                           **parse_response(text, reg.get(cid, {}).get("answer_options", ""))}
    write_csv(keyf, rkey, ["response_id", "run_id", "attempt_no", "case_id", "issued_at"])
    write_csv(path(root, "extraction"), list(extraction.values()))

    issue_log_f = root / "grading" / "private" / "packet_issue_log.csv"
    issued = read_csv(issue_log_f)
    have = {(i["grader_id"], i["response_id"], i.get("packet_type", "primary")) for i in issued}
    batch = batch or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_of = {k["response_id"]: k["run_id"] for k in rkey}
    results = {}
    for gi, g in enumerate(graders):
        todo = [k["response_id"] for k in rkey if (g, k["response_id"], "primary") not in have]
        grng = random.Random((seed if seed is not None else secrets.randbits(32)) + 7919 * (gi + 1))
        grng.shuffle(todo)
        rows = []
        for rid in todo:
            cid = extraction[rid]["case_id"]
            a, n = ans.get(cid, {}), ann.get(cid, {})
            rows.append({"response_id": rid, "case_id": cid,
                         "reference_diagnosis": a.get("reference_diagnosis", ""),
                         "accepted_dx_synonyms": n.get("accepted_dx_synonyms", ""),
                         "answer_options": reg.get(cid, {}).get("answer_options", ""),
                         "correct_letter": a.get("correct_letter", ""),
                         "auto_diagnosis": extraction[rid]["auto_diagnosis"],
                         "auto_letter": extraction[rid]["auto_letter"],
                         "extraction_flags": extraction[rid]["extraction_flags"],
                         "response_file": f"responses/{rid}.txt", "grader_id": g})
            issued.append({"grader_id": g, "response_id": rid, "packet_type": "primary", "batch": batch})
        if rows:
            write_csv(root / "grading" / "packets" / f"grader_{g}_batch_{batch}.csv", rows, PACKET_FIELDS)
        # image-interpretation packet (image arm only)
        sched = {s["run_id"]: s for s in read_csv(path(root, "schedule"))}
        coll = {(c["run_id"], str(c.get("attempt_no") or "1")): c for c in read_csv(path(root, "collection"))}
        todo_i = [k for k in rkey if sched.get(k["run_id"], {}).get("input") == "text_image"
                  and (g, k["response_id"], "interp") not in have]
        grng.shuffle(todo_i)
        irows = []
        for k in todo_i:
            att = coll.get((k["run_id"], k["attempt_no"]), {})
            irows.append({"response_id": k["response_id"], "case_id": k["case_id"],
                          "image_files": att.get("image_ids_uploaded", ""),
                          "response_file": f"responses/{k['response_id']}.txt", "grader_id": g})
            issued.append({"grader_id": g, "response_id": k["response_id"], "packet_type": "interp", "batch": batch})
        if irows:
            write_csv(root / "grading" / "packets" / f"interp_{g}_batch_{batch}.csv", irows, INTERP_FIELDS)
        results[g] = {"primary": len(rows), "interp": len(irows)}
    write_csv(issue_log_f, issued, ["grader_id", "response_id", "packet_type", "batch"])
    return {"new_response_ids": new_ids, "per_grader": results, "batch": batch}


def _norm01(v):
    v = (v or "").strip()
    if v in ("1", "1.0", "Yes", "yes", "Y"):
        return "1"
    if v in ("0", "0.0", "No", "no", "N"):
        return "0"
    return "" if v == "" else "INVALID:" + v


def read_returns(root, kind: str = "grader") -> dict:
    """Return {(response_id, grader_id): row}; later files override earlier, duplicates noted."""
    rd = Path(root) / "grading" / "returns"
    out, dups = {}, []
    pattern = "grader_*.csv" if kind == "grader" else "interp_*.csv"
    for f in sorted(rd.glob(pattern)):
        for r in read_csv(f):
            if not r.get("response_id"):
                continue
            k = (r["response_id"], (r.get("grader_id") or "").strip())
            if k in out and any((r.get(x) or "") for x in ("dx_correct", "mgmt_correct", "interp_category")):
                dups.append(k)
            if any((r.get(x) or "").strip() for x in ("dx_correct", "mgmt_correct", "interp_category")):
                r["_file"] = f.name
                out[k] = r
    return {"rows": out, "duplicates": dups}


def merge(root, graders=("G1", "G2")) -> dict:
    root = Path(root)
    rkey = read_csv(path(root, "response_key"))
    rets = read_returns(root)["rows"]
    irets = read_returns(root, "interp")["rows"]
    adj_ret = {a["response_id"]: a for a in read_csv(path(root, "adjudication_return"))}
    ans = {a["case_id"]: a for a in read_csv(path(root, "answer_key"))}
    ann = {a["case_id"]: a for a in read_csv(path(root, "annotations"))}
    g1, g2 = graders
    final, adj_rows = [], []
    for k in rkey:
        rid = k["response_id"]
        a, b = rets.get((rid, g1), {}), rets.get((rid, g2), {})
        ia, ib = irets.get((rid, g1), {}), irets.get((rid, g2), {})
        adj = adj_ret.get(rid, {})
        row = {"response_id": rid, "run_id": k["run_id"], "attempt_no": k["attempt_no"], "case_id": k["case_id"]}
        need_adj = []
        for out_name, col in OUTCOMES.items():
            s1, s2 = _norm01(a.get(col)), _norm01(b.get(col))
            row[f"{out_name}_g1"], row[f"{out_name}_g2"] = s1, s2
            row[f"{out_name}_reason_g1"], row[f"{out_name}_reason_g2"] = \
                a.get("dx_reason" if out_name != "mgmt" else "mgmt_reason", ""), b.get("dx_reason" if out_name != "mgmt" else "mgmt_reason", "")
            sa = _norm01(adj.get(f"adj_{col}"))
            row[f"{out_name}_adjudicated"] = sa
            if s1 in ("0", "1") and s1 == s2:
                row[f"{out_name}_final"], row[f"{out_name}_final_source"] = s1, "agreement"
            elif s1 in ("0", "1") and s2 in ("0", "1"):
                if sa in ("0", "1"):
                    row[f"{out_name}_final"], row[f"{out_name}_final_source"] = sa, "adjudicated"
                else:
                    row[f"{out_name}_final"], row[f"{out_name}_final_source"] = "", "awaiting_adjudication"
                    need_adj.append(out_name)
            else:
                row[f"{out_name}_final"], row[f"{out_name}_final_source"] = "", "awaiting_grades"
        row["mgmt_letter_g1"], row["mgmt_letter_g2"] = a.get("mgmt_letter", ""), b.get("mgmt_letter", "")
        row["extracted_dx_g1"], row["extracted_dx_g2"] = a.get("extracted_diagnosis_confirmed", ""), b.get("extracted_diagnosis_confirmed", "")
        # image interpretation (categorical)
        c1, c2 = (ia.get("interp_category") or "").strip(), (ib.get("interp_category") or "").strip()
        row["interp_g1"], row["interp_g2"] = c1, c2
        ca = (adj.get("adj_interp_category") or "").strip()
        if c1 and c1 == c2:
            row["interp_final"], row["interp_final_source"] = c1, "agreement"
        elif c1 and c2:
            row["interp_final"], row["interp_final_source"] = (ca, "adjudicated") if ca else ("", "awaiting_adjudication")
            if not ca:
                need_adj.append("interp")
        elif c1 or c2:
            row["interp_final"], row["interp_final_source"] = "", "awaiting_second_grade"
        else:
            row["interp_final"], row["interp_final_source"] = "", ""
        final.append(row)
        if need_adj:
            cid = k["case_id"]
            adj_rows.append({
                "response_id": rid, "case_id": cid, "outcomes_in_disagreement": ";".join(need_adj),
                "reference_diagnosis": ans.get(cid, {}).get("reference_diagnosis", ""),
                "accepted_dx_synonyms": ann.get(cid, {}).get("accepted_dx_synonyms", ""),
                "correct_letter": ans.get(cid, {}).get("correct_letter", ""),
                "response_file": f"../packets/responses/{rid}.txt",
                "g1_dx": row["dx_g1"], "g2_dx": row["dx_g2"], "g1_dx_reason": a.get("dx_reason", ""), "g2_dx_reason": b.get("dx_reason", ""),
                "g1_partial": row["partial_g1"], "g2_partial": row["partial_g2"],
                "g1_mgmt_letter": a.get("mgmt_letter", ""), "g2_mgmt_letter": b.get("mgmt_letter", ""),
                "g1_mgmt": row["mgmt_g1"], "g2_mgmt": row["mgmt_g2"], "g1_mgmt_reason": a.get("mgmt_reason", ""), "g2_mgmt_reason": b.get("mgmt_reason", ""),
                "g1_interp": c1, "g2_interp": c2,
                "adjudicator_id": "", "adj_dx_correct": "", "adj_dx_partial": "", "adj_mgmt_correct": "",
                "adj_interp_category": "", "adj_reason": "",
            })
    write_csv(path(root, "grades_final"), final)
    write_csv(path(root, "adjudication_packet"), adj_rows, list(adj_rows[0].keys()) if adj_rows else
              ["response_id", "case_id", "outcomes_in_disagreement", "adjudicator_id", "adj_dx_correct",
               "adj_dx_partial", "adj_mgmt_correct", "adj_interp_category", "adj_reason"])
    summary = {}
    for out_name in list(OUTCOMES) + ["interp"]:
        for r in final:
            src = r.get(f"{out_name}_final_source", "")
            summary.setdefault(out_name, {}).setdefault(src or "n/a", 0)
            summary[out_name][src or "n/a"] += 1
    return {"responses": len(final), "awaiting_adjudication": len(adj_rows), "by_outcome": summary}
