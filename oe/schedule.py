"""Reproducible run schedule.

Algorithm (reverse-engineered from the workbook and verified to reproduce
its Run Log exactly):

* Retest subset: ``random.Random(retest_seed).sample(eligible_ids_in_registry_order, 50)``.
* Run order: one ``random.Random(run_order_seed)`` stream. For each eligible
  case in registry order, shuffle ``[1..6]``; element k-1 is the run order of
  condition k. The same stream then continues through the retest cases in
  ascending case-ID order.

If the workbook already holds assignments, they are preserved verbatim and the
regenerated schedule is only used to confirm reproducibility.
"""
from __future__ import annotations

import random

from .common import cond_lookup, load_config, path, read_csv, run_id_for, write_csv

FIELDS = ["run_id", "run_type", "case_id", "condition", "model", "input", "run_order",
          "linked_main_run_id", "retest_min_interval_days", "assignment_source",
          "collector_assigned", "batch"]


def select_retest(eligible_ids: list[int], seed: int, n: int) -> list[int]:
    return sorted(random.Random(seed).sample(list(eligible_ids), n))


def generate(eligible_ids: list[int], order_seed: int, retest_seed: int, n_retest: int,
             cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    cl = cond_lookup(cfg)
    rng = random.Random(order_seed)
    rows = []

    def block(cid, run_type):
        orders = list(range(1, 7))
        rng.shuffle(orders)
        blk = []
        for k in range(1, 7):
            blk.append({"run_id": run_id_for(cid, k, run_type), "run_type": run_type, "case_id": cid,
                        "condition": k, "model": cl[k]["model"], "input": cl[k]["input"],
                        "run_order": orders[k - 1],
                        "linked_main_run_id": run_id_for(cid, k, "Main") if run_type == "Retest" else ""})
        return sorted(blk, key=lambda x: x["run_order"])

    for cid in eligible_ids:
        rows += block(cid, "Main")
    for cid in select_retest(eligible_ids, retest_seed, n_retest):
        rows += block(cid, "Retest")
    return rows


def _key(r):
    return (r["run_id"], r["run_type"], int(r["case_id"]), int(r["condition"]), r["model"], r["input"], int(r["run_order"]))


def build(root) -> dict:
    cfg = load_config()
    reg = read_csv(path(root, "registry"))
    eligible = [int(r["case_id"]) for r in reg if r["eligible"] == "Yes"]
    gen = generate(eligible, cfg["randomization"]["run_order_seed"], cfg["randomization"]["retest_seed"],
                   cfg["design"]["retest_n_cases"], cfg)
    wb = read_csv(path(root, "workbook_schedule"))
    if wb:
        same = sorted(map(_key, wb)) == sorted(map(_key, gen))
        cl = cond_lookup(cfg)
        rows = []
        for r in wb:
            cid, k = int(r["case_id"]), int(r["condition"])
            rows.append({**r, "case_id": cid, "condition": k, "run_order": int(r["run_order"]),
                         "linked_main_run_id": run_id_for(cid, k, "Main") if r["run_type"] == "Retest" else ""})
            if cl[k]["model"] != r["model"] or cl[k]["input"] != r["input"]:
                raise SystemExit(f"Workbook run {r['run_id']}: condition {k} labelled {r['model']}/{r['input']}")
        source = "workbook Run Log (preserved); regenerated from seeds: " + ("IDENTICAL" if same else "DIFFERENT - investigate")
    else:
        rows, same, source = gen, True, "generated from config seeds"
    for r in rows:
        r["assignment_source"] = "workbook" if wb else "generated"
        r["retest_min_interval_days"] = cfg["design"]["retest_min_interval_days"] if r["run_type"] == "Retest" else ""
    old = {r["run_id"]: r for r in read_csv(path(root, "schedule"))}
    for r in rows:  # keep coordinator-entered collector/batch assignments
        for f in ("collector_assigned", "batch"):
            r[f] = old.get(r["run_id"], {}).get(f, "")
    write_csv(path(root, "schedule"), rows, FIELDS)
    return {"runs": len(rows), "main": sum(r["run_type"] == "Main" for r in rows),
            "retest": sum(r["run_type"] == "Retest" for r in rows), "source": source,
            "reproducible": same}
