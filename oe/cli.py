"""Command-line entry point:  python -m oe <command> [--root DATA_ROOT]

Daily order of use is documented in README.md.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import admin, build, collection, grading, legend, prompts, schedule, validate, worklist
from .common import env_root


def _print(obj):
    print(json.dumps(obj, indent=2, default=str))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m oe", description=__doc__)
    ap.add_argument("--root", default=None, help="data root (default: ./data or $OE_DATA_ROOT)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import", help="read the workbook (read-only) into CSV files + audit")
    p.add_argument("--workbook")
    sub.add_parser("draft-image-text", help="propose legend-removed text for review").add_argument(
        "--fill-empty", action="store_true", help="copy drafts into empty rows as status draft_needs_review")
    sub.add_parser("schedule", help="build run schedule (preserves workbook assignments)")
    p = sub.add_parser("prompts", help="generate collector-facing prompts")
    p.add_argument("--version")
    sub.add_parser("crosscheck-workbook-prompts", help="prove generator reproduces workbook Prompts!D")
    sub.add_parser("init-log", help="create the collection log (never overwrites)")
    p = sub.add_parser("worklist", help="HTML run cards for collectors")
    p.add_argument("--collector"); p.add_argument("--batch"); p.add_argument("--limit", type=int, default=60)
    p.add_argument("--retests", action="store_true")
    sub.add_parser("progress", help="collection progress by condition")
    p = sub.add_parser("packets", help="issue blinded grading packets for new responses")
    p.add_argument("--graders", default="G1,G2"); p.add_argument("--seed", type=int); p.add_argument("--batch")
    p = sub.add_parser("merge-grades", help="combine grader returns; write adjudication packet")
    p.add_argument("--graders", default="G1,G2")
    sub.add_parser("build-analysis", help="assemble analysis_dataset.csv for R")
    p = sub.add_parser("validate", help="run quality checks and write the issue report")
    p.add_argument("--stage", choices=["setup", "collection", "analysis"], default="collection")
    p.add_argument("--graders", default="G1,G2")
    p.add_argument("--strict", action="store_true", help="exit 1 if any ERROR")
    p = sub.add_parser("lock-registry", help="fingerprint case IDs/text/options/keys")
    p.add_argument("--by", required=True)
    sub.add_parser("hash-images", help="record SHA-256 of prepared images")
    p = sub.add_parser("pilot-setup", help="create the separate 10-case pilot folder (data/pilot)")
    p.add_argument("--cases", help="comma-separated case IDs (default: seeded random selection)")
    p = sub.add_parser("app", help="start Pilot Desk, the point-and-click interface")
    p.add_argument("--port", type=int, default=8765); p.add_argument("--no-browser", action="store_true")
    p = sub.add_parser("synthetic", help="build the SYNTHETIC demonstration data root")
    p.add_argument("--out", default="synthetic/demo_data"); p.add_argument("--seed", type=int, default=11)

    a = ap.parse_args(argv)
    root = a.root or env_root()
    if a.cmd == "import":
        _print(__import__("oe.importer", fromlist=["x"]).import_workbook(root, a.workbook))
    elif a.cmd == "draft-image-text":
        _print(legend.build_drafts(root, a.fill_empty))
    elif a.cmd == "schedule":
        _print(schedule.build(root))
    elif a.cmd == "prompts":
        _print(prompts.generate(root, a.version))
    elif a.cmd == "crosscheck-workbook-prompts":
        r = prompts.crosscheck_workbook(root)
        _print(r)
        sys.exit(0 if r["identical"] == r["total"] else 1)
    elif a.cmd == "init-log":
        _print(collection.init_log(root))
    elif a.cmd == "worklist":
        _print(worklist.build(root, a.collector, a.batch, a.limit, a.retests))
    elif a.cmd == "progress":
        for r in collection.progress(root):
            print(r)
    elif a.cmd == "packets":
        _print(grading.make_packets(root, tuple(a.graders.split(",")), a.seed, a.batch))
    elif a.cmd == "merge-grades":
        _print(grading.merge(root, tuple(a.graders.split(","))))
    elif a.cmd == "build-analysis":
        _print(build.build(root))
    elif a.cmd == "validate":
        r = validate.run(root, a.stage, tuple(a.graders.split(",")))
        _print({"counts": r["counts"], "report": f"{root}/reports/validation_report_{a.stage}.md"})
        if a.strict and r["counts"].get("ERROR"):
            sys.exit(1)
    elif a.cmd == "lock-registry":
        _print(admin.lock_registry(root, a.by))
    elif a.cmd == "hash-images":
        _print(admin.hash_images(root))
    elif a.cmd == "pilot-setup":
        from . import pilot
        _print(pilot.setup(root, case_ids=a.cases.split(",") if a.cases else None))
    elif a.cmd == "app":
        from . import app
        app.serve(root, a.port, not a.no_browser)
    elif a.cmd == "synthetic":
        from . import synthetic
        _print(synthetic.build(a.out, a.seed))
