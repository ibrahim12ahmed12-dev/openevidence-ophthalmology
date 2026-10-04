"""Collection log (one row per ATTEMPT) and run-status derivation.

Status vocabulary
  pending      scheduled run with no attempt recorded (status cell blank)
  completed    a response was obtained under protocol
  failed       technical failure or protocol deviation (wrong model, reused
               session, upload error...). Kept for audit; retry with a new row.
  unavailable  the condition cannot be run (e.g. image-only content that cannot
               be uploaded). NOT an incorrect answer; excluded from that
               condition's denominator and reported.
  withdrawn    run removed by the coordinator with a documented reason.

Analysis attempt rule: the FIRST attempt (lowest attempt_no) with status
'completed'. Retries are allowed only after 'failed', never because an answer
looked wrong.
"""
from __future__ import annotations

from .common import load_config, path, read_csv, write_csv, write_if_absent

FIELDS = [
    "run_id", "attempt_no", "case_id", "run_type", "condition", "model", "input", "run_order",
    "status", "failure_reason", "collector", "prompt_version", "prompt_sha256",
    "model_selection_confirmed", "new_session_confirmed", "memory_personalization_off",
    "run_date", "run_time", "timezone", "response_duration_s",
    "image_ids_uploaded", "n_images_uploaded", "upload_limit_note",
    "response_text", "response_file", "screenshot_path",
    "citation_count", "source_retrieved", "retrieval_assessed_by", "retrieval_notes",
    "platform_notes", "notes",
]
HELPER = ["case_id", "run_type", "condition", "model", "input", "run_order"]


def init_log(root) -> dict:
    sched = read_csv(path(root, "schedule"))
    rows = [{**{h: s[h] for h in HELPER}, "run_id": s["run_id"], "attempt_no": 1} for s in sched]
    created = write_if_absent(path(root, "collection"), rows, FIELDS)
    return {"created": created, "rows": len(rows), "file": str(path(root, "collection"))}


def _attempt_no(a) -> int:
    try:
        return int(float(a.get("attempt_no") or 1))
    except ValueError:
        return 10**6


def derive_runs(schedule: list[dict], collection: list[dict]) -> dict[str, dict]:
    by: dict[str, list[dict]] = {}
    for a in collection:
        by.setdefault(a["run_id"], []).append(a)
    out = {}
    for s in schedule:
        atts = sorted(by.get(s["run_id"], []), key=_attempt_no)
        recorded = [a for a in atts if (a.get("status") or "").strip()]
        stats = [a["status"].strip().lower() for a in recorded]
        designated = next((a for a in recorded if a["status"].strip().lower() == "completed"), None)
        if designated:
            st = "completed"
        elif "withdrawn" in stats:
            st = "withdrawn"
        elif "unavailable" in stats:
            st = "unavailable"
        elif "failed" in stats:
            st = "failed"
        else:
            st = "pending"
        out[s["run_id"]] = {"schedule": s, "status": st, "designated": designated,
                            "n_attempts": len(recorded), "attempts": atts}
    return out


def progress(root) -> list[dict]:
    cfg = load_config()
    runs = derive_runs(read_csv(path(root, "schedule")), read_csv(path(root, "collection")))
    rows = {}
    for r in runs.values():
        s = r["schedule"]
        k = (s["run_type"], s["model"], s["input"])
        d = rows.setdefault(k, {"run_type": k[0], "model": k[1], "input": k[2], "scheduled": 0,
                                **{x: 0 for x in ["pending"] + cfg["collection"]["allowed_status"]}})
        d["scheduled"] += 1
        d[r["status"]] += 1
    return [rows[k] for k in sorted(rows)]
