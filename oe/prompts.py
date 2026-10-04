"""Deterministic prompt generation from approved case text and locked settings.

Same inputs -> byte-identical prompts (verified by SHA-256). Nothing here
rewrites clinical content: case text and answer options are inserted verbatim,
in published order.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .common import (PROMPT_DIR, load_config, path, read_csv, sha256_file, sha256_text,
                     write_csv)

PLACEHOLDER = "[NOT READY - image-arm text not approved]"


def load_version(version: str) -> dict:
    p = PROMPT_DIR / f"{version}.json"
    if not p.exists():
        raise SystemExit(f"Unknown prompt version {version}; files: {[x.stem for x in PROMPT_DIR.glob('*.json')]}")
    spec = json.loads(p.read_text(encoding="utf-8"))
    spec["_sha256"] = sha256_file(p)
    return spec


def _strip_title(text: str, title: str) -> str:
    # Mirrors the workbook: drop a leading title only if the text starts with it.
    if title and text.startswith(title):
        return text[len(title):].strip()
    return text


def build_prompt(spec: dict, settings: dict, case_text: str, options: str, input_type: str,
                 title: str = "") -> str:
    text = case_text
    if settings.get("include_case_title"):
        text = (title + " " + text) if title and not text.startswith(title) else text
    else:
        text = _strip_title(text, title)
    excl = spec.get("source_exclusion_instruction", "") if settings.get("include_source_exclusion_instruction") else ""
    prefix = spec["image_arm_prefix"] if input_type == "text_image" else spec["text_only_prefix"]
    if spec["version"].startswith("P1"):
        out = prefix + " " + (excl + " " if excl else "") + text + spec.get("case_stem_separator", "") \
            + spec["question_stem"] + "  " + options
        if settings.get("include_answer_format_line", True) and spec.get("answer_format_line"):
            out += " " + spec["answer_format_line"]
        return out
    if spec["version"].startswith("P0"):
        parts = [p for p in (prefix, excl) if p]
        parts += [text, spec["question_stem"] + "\n" + options, spec["closing_question"]]
        return "\n\n".join(parts)
    raise SystemExit(f"No assembly rule for prompt version {spec['version']}")


def generate(root, version: str | None = None, settings_override: dict | None = None,
             include_ineligible: bool = False) -> dict:
    cfg = load_config()
    settings = dict(cfg["prompt"])
    settings.update(settings_override or {})
    version = version or settings["active_version"]
    spec = load_version(version)
    reg = read_csv(path(root, "registry"))
    titles = {k["case_id"]: k["case_title"] for k in read_csv(path(root, "answer_key"))}
    arm = {a["case_id"]: a for a in read_csv(path(root, "image_arm"))}
    images = read_csv(path(root, "images"))
    rows = []
    for r in reg:
        if r["eligible"] != "Yes" and not include_ineligible:
            continue
        cid = r["case_id"]
        imgs = [i for i in images if i["case_id"] == cid and i.get("availability", "").lower() == "available"]
        unavailable = [i for i in images if i["case_id"] == cid and i.get("availability", "").lower().startswith("unavailable")]
        for inp in ("text_only", "text_image"):
            ready, reason = "Yes", ""
            if inp == "text_only":
                text = r["text_only_input"]
            elif settings["image_arm_option"] == "B":
                text = r["text_only_input"]
            else:
                a = arm.get(cid, {})
                text = a.get("image_arm_text", "")
                if a.get("status") != "approved" or not text.strip():
                    ready, reason = "No", f"image-arm text status '{a.get('status', 'missing')}' (needs 'approved')"
            if inp == "text_image":
                if unavailable and not imgs:
                    ready, reason = "No", "images unavailable (run will be logged as 'unavailable')"
                elif not imgs:
                    ready, reason = "No", (reason + "; " if reason else "") + "no prepared image marked available"
            text_ok = inp == "text_only" or settings["image_arm_option"] == "B" or \
                (arm.get(cid, {}).get("status") == "approved" and text.strip())
            prompt = build_prompt(spec, settings, text, r["answer_options"], inp, titles.get(cid, "")) if text_ok else PLACEHOLDER
            rows.append({
                "case_id": cid, "input": inp, "prompt_version": version,
                "prompt_sha256": sha256_text(prompt) if ready == "Yes" else "",
                "ready": ready, "not_ready_reason": reason,
                "image_ids_to_upload": ";".join(i["image_id"] for i in sorted(imgs, key=lambda x: x["image_id"])) if inp == "text_image" else "",
                "prepared_files_to_upload": ";".join(i.get("prepared_filename", "") for i in sorted(imgs, key=lambda x: x["image_id"])) if inp == "text_image" else "",
                "n_chars": len(prompt) if ready == "Yes" else "",
                "prompt_text": prompt,
            })
    out_dir = Path(root) / "prompts"
    out = write_csv(out_dir / f"prompts_{version}.csv", rows)
    manifest = {
        "prompt_version": version, "prompt_spec_sha256": spec["_sha256"],
        "settings": {k: v for k, v in settings.items() if not k.startswith("_")},
        "config_version": cfg["config_version"],
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "n_rows": len(rows), "n_ready": sum(r["ready"] == "Yes" for r in rows),
        "registry_sha256": sha256_file(path(root, "registry")),
        "note": "Collector-facing. Contains no titles, reference answers or discussions.",
    }
    (out_dir / f"prompt_manifest_{version}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"file": str(out), **{k: manifest[k] for k in ("n_rows", "n_ready")}}


def crosscheck_workbook(root) -> dict:
    """Rebuild text-only prompts with the WORKBOOK's settings and compare to the
    workbook's cached Prompts!D values. Proves the generator reproduces the
    workbook exactly (it is not the provisional collection setting)."""
    spec = load_version("P1-standardized")
    snap = {s["setting"]: s["value"] for s in read_csv(Path(root) / "registry" / "workbook_settings_snapshot.csv")}
    settings = {"include_case_title": snap.get("Include case title in prompt", "No") == "Yes",
                "include_source_exclusion_instruction": bool(snap.get("Source-exclusion instruction", "")),
                "include_answer_format_line": bool(snap.get("Answer-format instruction", ""))}
    spec = dict(spec)
    spec["text_only_prefix"] = snap.get("Text-only prompt prefix", spec["text_only_prefix"])
    spec["source_exclusion_instruction"] = snap.get("Source-exclusion instruction", "")
    spec["answer_format_line"] = snap.get("Answer-format instruction", "")
    spec["question_stem"] = snap.get("Question stem", spec["question_stem"])
    reg = {r["case_id"]: r for r in read_csv(path(root, "registry"))}
    titles = {k["case_id"]: k["case_title"] for k in read_csv(path(root, "answer_key"))}
    cached = read_csv(Path(root) / "registry" / "workbook_prompts_cached_PRIVATE.csv")
    same, diff = 0, []
    for c in cached:
        r = reg[c["case_id"]]
        mine = build_prompt(spec, settings, r["text_only_input"], r["answer_options"], "text_only", titles[c["case_id"]])
        if mine == c["wb_text_only_prompt"]:
            same += 1
        else:
            diff.append(c["case_id"])
    return {"identical": same, "total": len(cached), "different_case_ids": diff}
