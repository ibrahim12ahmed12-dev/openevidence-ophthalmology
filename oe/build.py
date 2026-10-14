"""Assemble the long-format analysis dataset (one row per SCHEDULED run).

Rows are never dropped here: unperformed, failed, unavailable and withdrawn
runs stay in the file with their status so that every denominator in the R
analysis can be traced. Analysability flags say which rows enter which model.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .collection import derive_runs
from .common import is_synthetic_root, load_config, path, read_csv, write_csv

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


def parse_dt(date_s: str, time_s: str, tz: str):
    """Return an aware UTC datetime or None. Accepts YYYY-MM-DD and HH:MM[:SS]."""
    date_s, time_s, tz = (date_s or "").strip(), (time_s or "").strip(), (tz or "").strip()
    if not date_s:
        return None
    try:
        t = time_s or "00:00"
        fmt = "%Y-%m-%d %H:%M:%S" if t.count(":") == 2 else "%Y-%m-%d %H:%M"
        naive = dt.datetime.strptime(f"{date_s} {t}", fmt)
    except ValueError:
        return None
    if not tz or ZoneInfo is None:
        return None
    try:
        return naive.replace(tzinfo=ZoneInfo(tz)).astimezone(dt.timezone.utc)
    except Exception:
        return None


def build(root) -> dict:
    root = Path(root)
    cfg = load_config()
    sched = read_csv(path(root, "schedule"))
    runs = derive_runs(sched, read_csv(path(root, "collection")))
    reg = {r["case_id"]: r for r in read_csv(path(root, "registry"))}
    ann = {a["case_id"]: a for a in read_csv(path(root, "annotations"))}
    imgs = read_csv(path(root, "images"))
    grades = {(g["run_id"], g["attempt_no"]): g for g in read_csv(path(root, "grades_final"))}
    synthetic = is_synthetic_root(root)

    elig_counts: dict[str, int] = {}
    for r in reg.values():
        if r["eligible"] == "Yes":
            elig_counts[r["subspecialty"]] = elig_counts.get(r["subspecialty"], 0) + 1
    thr = cfg["analysis"]["min_subspecialty_n_for_covariate"]
    small = sorted(k for k, v in elig_counts.items() if v < thr)

    modalities: dict[str, set] = {}
    for i in imgs:
        for m in (i.get("modality") or "").split(";"):
            if m.strip():
                modalities.setdefault(i["case_id"], set()).add(m.strip())

    rows, utc_of = [], {}
    for s in sched:
        r = runs[s["run_id"]]
        a = r["designated"] or {}
        g = grades.get((s["run_id"], str(a.get("attempt_no") or "1")), {}) if a else {}
        cid = s["case_id"]
        rc = reg.get(cid, {})
        when = parse_dt(a.get("run_date"), a.get("run_time"), a.get("timezone")) if a else None
        utc_of[s["run_id"]] = when
        sub = rc.get("subspecialty", "")
        row = {
            "run_id": s["run_id"], "run_type": s["run_type"], "case_id": cid,
            "condition": s["condition"], "model": s["model"], "input": s["input"],
            "run_order": s["run_order"], "linked_main_run_id": s.get("linked_main_run_id", ""),
            "eligible": rc.get("eligible", "NOT_IN_REGISTRY"),
            "subspecialty": sub,
            "subspecialty_covariate": ("Pooled (<%d cases): " % thr + ", ".join(small)) if sub in small else sub,
            "publication_year": ann.get(cid, {}).get("publication_year", ""),
            "modalities": ";".join(sorted(modalities.get(cid, set()))),
            "run_status": r["status"], "n_attempts": r["n_attempts"],
            "attempt_no_used": a.get("attempt_no", "") if a else "",
            "collector": a.get("collector", ""), "prompt_version": a.get("prompt_version", ""),
            "run_datetime_utc": when.isoformat() if when else "",
            "response_duration_s": a.get("response_duration_s", ""),
            "citation_count": a.get("citation_count", ""),
            "source_retrieved": (a.get("source_retrieved") or "").strip(),
            "n_images_uploaded": a.get("n_images_uploaded", ""),
            "response_id": g.get("response_id", ""),
        }
        for o in ("dx", "partial", "mgmt"):
            for suf in ("g1", "g2", "adjudicated", "final", "final_source"):
                row[f"{o}_{suf}"] = g.get(f"{o}_{suf}", "")
        row["interp_final"] = g.get("interp_final", "")
        row["interp_g1"], row["interp_g2"] = g.get("interp_g1", ""), g.get("interp_g2", "")
        row["analyzable_dx"] = int(r["status"] == "completed" and row["dx_final"] in ("0", "1") and row["eligible"] == "Yes")
        row["analyzable_mgmt"] = int(r["status"] == "completed" and row["mgmt_final"] in ("0", "1") and row["eligible"] == "Yes")
        row["synthetic"] = "TRUE" if synthetic else "FALSE"
        rows.append(row)
    for row in rows:
        if row["run_type"] == "Retest":
            m, t = utc_of.get(row["linked_main_run_id"]), utc_of.get(row["run_id"])
            row["elapsed_days_since_main"] = round((t - m).total_seconds() / 86400, 2) if (m and t) else ""
        else:
            row["elapsed_days_since_main"] = ""
    out = write_csv(path(root, "analysis"), rows)
    return {"file": str(out), "rows": len(rows),
            "analyzable_dx_main": sum(r["analyzable_dx"] for r in rows if r["run_type"] == "Main"),
            "analyzable_mgmt_main": sum(r["analyzable_mgmt"] for r in rows if r["run_type"] == "Main"),
            "pooled_subspecialties": small}
