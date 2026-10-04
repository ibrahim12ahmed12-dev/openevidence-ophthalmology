"""Import the study workbook into transparent CSV files.

The workbook is opened read-only and is never modified. Two passes are made:
formulas (to audit how columns are built) and cached values (what Excel last
computed). Generated files are rewritten on every import; human-edited files
(annotations, image-arm text, image metadata) are only seeded when absent.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .common import (WORKBOOK_INPUT, content_tokens, ensure_dirs, norm_key, norm_ws,
                     parse_options, path, read_csv, sha256_file, sha256_text, shingles,
                     write_csv, write_if_absent)

CASE_COLS = {  # header text in the workbook -> internal name (checked on import)
    "A": ("Section", "subspecialty"),
    "C": ("Case Name", "case_title"),
    "D": ("Link", "source_url"),
    "E": ("Case", "original_text"),
    "F": ("Cases (only those that need rerunning", "leak_corrected_text"),
    "G": ("Discussion", "discussion"),
    "H": ("What would you do next?", "answer_options"),
    "I": ("Correct next step", "correct_answer_published"),
    "J": ("Correct next step (A,B,C,D)", "correct_letter_workbook"),
    "K": ("Correct dx", "reference_diagnosis"),
    "O": ("2026 – Dx correct (0/1)", "hist_dx_correct"),
    "Q": ("2026 – Next step correct (0/1)", "hist_mgmt_correct"),
    "N": ("2026 – Dx (ZS PS+)", "hist_dx_text"),
    "P": ("2026 – Next step", "hist_next_step"),
    "R": ("Case ID", "case_id"),
    "S": ("Include (Yes/No)", "include"),
    "T": ("Exclusion reason", "exclusion_reason"),
    "V": ("Image-arm case text (legend removed)", "wb_image_arm_text"),
    "W": ("Accepted dx synonyms", "wb_synonyms"),
    "X": ("Figures (n)", "wb_n_figures"),
    "Y": ("Primary imaging modality", "wb_primary_modality"),
    "Z": ("Image file name(s)", "wb_image_files"),
    "AA": ("Retest subset", "wb_retest"),
}

REGISTRY_FIELDS = [
    "case_id", "source_row", "eligible", "exclusion_reason", "subspecialty", "publication_year",
    "source_url", "original_text", "leak_corrected_text", "leak_corrected_identical_to_original",
    "text_only_input", "text_source", "answer_options", "n_options", "options_sha256",
    "text_only_sha256", "retest_subset_workbook", "hist_prompt_had_prefix_2026",
    "hist_text_truncated_2026", "hist_title_included_2026",
]
ANSWER_KEY_FIELDS = [
    "case_id", "case_title", "reference_diagnosis", "correct_letter", "correct_letter_workbook",
    "correct_letter_from_text", "key_check", "correct_answer_text", "answer_key_explanation",
    "discussion",
]
ANNOTATION_FIELDS = [
    "case_id", "publication_year", "accepted_dx_synonyms", "synonyms_finalized_by",
    "synonyms_finalized_date", "n_figures", "notes",
]
IMAGE_ARM_FIELDS = [
    "case_id", "image_arm_text", "status", "edited_by", "approved_by", "approved_date",
    "review_notes",
]
IMAGE_FIELDS = [
    "case_id", "image_id", "figure_number", "panels", "original_filename", "prepared_filename",
    "prepared_sha256", "modality", "availability", "unavailable_reason", "width_px", "height_px",
    "preparation_steps", "label_or_caption_flag", "label_review_by", "notes",
]


def _find_workbook(root: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    cands = sorted((root / "source").glob("*.xlsx"))
    if not cands:
        raise SystemExit(f"No workbook found in {root/'source'}. Copy the .xlsx there or pass --workbook.")
    if len(cands) > 1:
        raise SystemExit(f"Several workbooks in {root/'source'}; pass --workbook explicitly: {cands}")
    return cands[0]


def _cell(ws, ref):
    v = ws[ref].value
    return getattr(v, "text", v)


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def letter_from_text(correct_answer: str, options: dict[str, str]) -> str:
    """Best-matching option letter for the published correct-answer text (audit only)."""
    import difflib
    first = (correct_answer or "").strip().split("\n")[0]
    m = re.match(r"^([A-H])\.\s*(.*)$", first)
    body = m.group(2) if m else first
    if not options:
        return ""
    scores = {k: difflib.SequenceMatcher(None, norm_key(v), norm_key(body)).ratio() for k, v in options.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 0.45 else ""


def import_workbook(root: str | Path, workbook: str | None = None) -> dict:
    import openpyxl  # imported lazily: only this step needs it

    root = Path(root)
    ensure_dirs(root)
    wb_path = _find_workbook(root, workbook)
    wbf = openpyxl.load_workbook(wb_path)                    # formulas
    wbv = openpyxl.load_workbook(wb_path, data_only=True)    # cached values
    problems: list[str] = []

    # ---------------- header check (refuse silently-shifted columns) -------------
    cs, cv = wbf["Cases"], wbv["Cases"]
    for col, (expected, _) in CASE_COLS.items():
        got = _s(cs[f"{col}1"].value)
        if not got.startswith(expected[:20]):
            raise SystemExit(f"Cases!{col}1 is '{got}', expected '{expected}'. Workbook layout changed; update CASE_COLS.")

    # ---------------- 2026 prompt sheet: map to case IDs for comparability --------
    ps = wbf["2026 PS+ Prompts"]
    hist_prompt = {}
    title_rows: dict[str, list[int]] = {}
    for r in range(2, cs.max_row + 1):
        t = cs[f"C{r}"].value
        if t:
            title_rows.setdefault(t, []).append(r)
    for r in range(2, ps.max_row + 1):
        t, opts, prompt = ps[f"A{r}"].value, ps[f"C{r}"].value, ps[f"F{r}"].value or ""
        if not t:
            continue
        rows = [x for x in title_rows.get(t, []) if norm_ws(cs[f"H{x}"].value) == norm_ws(opts)] or title_rows.get(t, [])
        if len(rows) != 1:
            problems.append(f"2026 PS+ row {r}: could not map uniquely to a case ({t[:40]}...)")
            continue
        hist_prompt[rows[0]] = prompt

    registry, keys, hist, ann_seed, arm_seed, img_seed = [], [], [], [], [], []
    for r in range(2, cs.max_row + 1):
        if cs[f"R{r}"].value in (None, ""):
            continue
        g = {name: _cell(cs, f"{col}{r}") for col, (_, name) in CASE_COLS.items()}
        gv = {name: _cell(cv, f"{col}{r}") for col, (_, name) in CASE_COLS.items()}
        cid = int(g["case_id"])
        E, F = g["original_text"] or "", g["leak_corrected_text"] or ""
        text_only = F if F else E      # mirrors Cases!U  =IF(F<>"",F,E)
        u_formula = _s(cs[f"U{r}"].value)
        if not u_formula.startswith("=IF(F"):
            problems.append(f"Cases!U{r} formula differs from =IF(F..,F,E): {u_formula[:40]}")
        opts = parse_options(g["answer_options"])
        wb_letter = _s(gv["correct_letter_workbook"]).strip()
        txt_letter = letter_from_text(g["correct_answer_published"], opts)
        first_line = (g["correct_answer_published"] or "").strip().split("\n")[0]
        stated = re.match(r"^([A-H])\.", first_line)
        checks = []
        if not stated:
            checks.append("published answer has no 'X.' letter prefix")
        elif stated.group(1) != wb_letter:
            checks.append(f"letter prefix {stated.group(1)} != workbook J {wb_letter}")
        if txt_letter and txt_letter != wb_letter:
            checks.append(f"answer text best matches option {txt_letter}, workbook J says {wb_letter}")
        if not txt_letter:
            checks.append("answer text does not clearly match any option")
        if wb_letter not in opts:
            checks.append("workbook letter not among options")
        if not str(cs[f"J{r}"].value).startswith("="):
            checks.append("J is a typed value, not the =LEFT(I..) formula")
        prompt26 = hist_prompt.get(r, "")
        registry.append({
            "case_id": cid, "source_row": r,
            "eligible": "Yes" if _s(g["include"]).strip().lower() == "yes" else "No",
            "exclusion_reason": _s(g["exclusion_reason"]),
            "subspecialty": _s(g["subspecialty"]),
            "publication_year": "",
            "source_url": _s(g["source_url"]),
            "original_text": E, "leak_corrected_text": F,
            "leak_corrected_identical_to_original": ("" if not F else ("Yes" if F == E else "No")),
            "text_only_input": text_only,
            "text_source": "F (leak-corrected column)" if F else "E (original)",
            "answer_options": g["answer_options"], "n_options": len(opts),
            "options_sha256": sha256_text(norm_ws(g["answer_options"])),
            "text_only_sha256": sha256_text(text_only),
            "retest_subset_workbook": _s(g["wb_retest"]),
            "hist_prompt_had_prefix_2026": ("" if not prompt26 else
                                            ("Yes" if prompt26.startswith("You are an expert in ophthalmology") else "No")),
            "hist_text_truncated_2026": ("" if not prompt26 else ("No" if norm_ws(text_only) in norm_ws(prompt26) else "Yes")),
            "hist_title_included_2026": ("" if not prompt26 else ("Yes" if norm_ws(g["case_title"]) in norm_ws(prompt26) else "No")),
        })
        lines = (g["correct_answer_published"] or "").strip().split("\n")
        keys.append({
            "case_id": cid, "case_title": _s(g["case_title"]),
            "reference_diagnosis": _s(g["reference_diagnosis"]),
            "correct_letter": wb_letter, "correct_letter_workbook": wb_letter,
            "correct_letter_from_text": txt_letter,
            "key_check": "OK" if not checks else "REVIEW: " + "; ".join(checks),
            "correct_answer_text": lines[0].strip(),
            "answer_key_explanation": "\n".join(lines[1:]).strip(),
            "discussion": _s(g["discussion"]),
        })
        hist.append({"case_id": cid, "hist_dx_correct_2026": _s(g["hist_dx_correct"]),
                     "hist_mgmt_correct_2026": _s(g["hist_mgmt_correct"]),
                     "hist_dx_text_2026": _s(g["hist_dx_text"]),
                     "hist_next_step_2026": _s(g["hist_next_step"])})
        ann_seed.append({"case_id": cid, "accepted_dx_synonyms": _s(g["wb_synonyms"]),
                         "n_figures": _s(g["wb_n_figures"])})
        arm_seed.append({"case_id": cid, "image_arm_text": _s(g["wb_image_arm_text"]),
                         "status": "workbook_entry_pending_signoff" if g["wb_image_arm_text"] else "not_started"})
        for i, fn in enumerate([x.strip() for x in re.split(r"[;\n]", _s(g["wb_image_files"])) if x.strip()], 1):
            img_seed.append({"case_id": cid, "image_id": f"IMG-{cid:03d}-{i}", "original_filename": fn,
                             "modality": _s(g["wb_primary_modality"]) if i == 1 else "",
                             "availability": "", "label_or_caption_flag": "needs_review"})

    # ---------------- Run Log assignments (preserved exactly) -----------------
    rl = wbv["Run Log"]
    hdr = [_s(c.value) for c in rl[1]]
    need = ["Run ID", "Run type", "Case ID", "Condition", "Model", "Input", "Run order (within case)"]
    idx = {h: hdr.index(h) for h in need}
    sched = []
    for row in rl.iter_rows(min_row=2, values_only=True):
        if row[idx["Run ID"]] in (None, ""):
            continue
        sched.append({
            "run_id": row[idx["Run ID"]], "run_type": row[idx["Run type"]],
            "case_id": int(row[idx["Case ID"]]), "condition": int(row[idx["Condition"]]),
            "model": row[idx["Model"]], "input": WORKBOOK_INPUT.get(row[idx["Input"]], row[idx["Input"]]),
            "run_order": int(row[idx["Run order (within case)"]]),
        })
    filled_cols = [h for i, h in enumerate(hdr) if h and h not in need + ["Case Name", "Subspecialty"] and i < 27 and any(
        row[i] not in (None, "") for row in rl.iter_rows(min_row=2, values_only=True)
        if not (isinstance(row[i], str) and row[i].startswith("=")))]

    # ---------------- Settings (recorded, not silently applied) -----------------
    st = wbv["Settings"]
    settings = {_s(st[f"A{r}"].value): _s(st[f"B{r}"].value) for r in range(2, st.max_row + 1) if st[f"A{r}"].value}

    # ---------------- cached workbook prompts (for byte-level cross-check) ---------
    pr = wbv["Prompts"]
    wb_prompts = [{"case_id": int(pr[f"A{r}"].value), "wb_text_only_prompt": pr[f"D{r}"].value or "",
                   "wb_image_arm_prompt": pr[f"F{r}"].value or ""}
                  for r in range(2, pr.max_row + 1) if pr[f"A{r}"].value not in (None, "")]

    # ---------------- write -----------------
    write_csv(path(root, "registry"), registry, REGISTRY_FIELDS)
    write_csv(path(root, "answer_key"), keys, ANSWER_KEY_FIELDS)
    write_csv(path(root, "historical"), hist)
    write_csv(path(root, "workbook_schedule"), sched)
    write_csv(root / "registry" / "workbook_settings_snapshot.csv",
              [{"setting": k, "value": v} for k, v in settings.items()])
    write_csv(root / "registry" / "workbook_prompts_cached_PRIVATE.csv", wb_prompts)
    seeded = {
        "annotations": write_if_absent(path(root, "annotations"), ann_seed, ANNOTATION_FIELDS),
        "image_arm": write_if_absent(path(root, "image_arm"), arm_seed, IMAGE_ARM_FIELDS),
        "images": write_if_absent(path(root, "images"), img_seed, IMAGE_FIELDS),
    }
    manifest = root / "source" / "SOURCE_MANIFEST.csv"
    prev = read_csv(manifest)
    entry = {"file": wb_path.name, "sha256": sha256_file(wb_path), "bytes": wb_path.stat().st_size,
             "imported_at": dt.datetime.now().isoformat(timespec="seconds")}
    if not any(p["sha256"] == entry["sha256"] for p in prev):
        prev.append(entry)
    write_csv(manifest, prev, ["file", "sha256", "bytes", "imported_at"])

    audit = audit_workbook(registry, keys, hist, sched, settings, filled_cols, problems)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "workbook_audit.md").write_text(audit, encoding="utf-8")
    return {"cases": len(registry), "runs": len(sched), "seeded": seeded, "workbook": str(wb_path),
            "audit": str(root / "reports" / "workbook_audit.md")}


def audit_workbook(registry, keys, hist, sched, settings, filled_cols, problems) -> str:
    """Readable audit. Mentions case IDs and counts only, never answers."""
    n = len(registry)
    elig = [r for r in registry if r["eligible"] == "Yes"]
    excl = [r for r in registry if r["eligible"] != "Yes"]
    F = [r for r in registry if r["leak_corrected_text"]]
    F_same = [r for r in F if r["leak_corrected_identical_to_original"] == "Yes"]
    key_rev = [k for k in keys if k["key_check"] != "OK" and k["key_check"] != "REVIEW: J is a typed value, not the =LEFT(I..) formula"]
    typed = [k for k in keys if "typed value" in k["key_check"]]
    no_prefix = [r for r in registry if r["hist_prompt_had_prefix_2026"] == "No"]
    trunc = [r for r in registry if r["hist_text_truncated_2026"] == "Yes"]
    keyd = {k["case_id"]: k for k in keys}
    title_in_text = [r["case_id"] for r in registry if norm_key(keyd[r["case_id"]]["case_title"]) in norm_key(r["text_only_input"])]
    dx_in_text = [r["case_id"] for r in registry
                  if len(norm_key(keyd[r["case_id"]]["reference_diagnosis"])) >= 6
                  and norm_key(keyd[r["case_id"]]["reference_diagnosis"]) in norm_key(r["text_only_input"])]
    disc_overlap = [r["case_id"] for r in registry if shingles(r["text_only_input"]) & shingles(keyd[r["case_id"]]["discussion"])]
    main = [s for s in sched if s["run_type"] == "Main"]
    rt = [s for s in sched if s["run_type"] == "Retest"]
    h_dx = sum(1 for h in hist if h["hist_dx_correct_2026"] == "1")
    h_mg = sum(1 for h in hist if h["hist_mgmt_correct_2026"] == "1")
    h_n = sum(1 for h in hist if h["hist_dx_correct_2026"] in ("0", "1"))
    excl_s = ", ".join("%s (%s)" % (r["case_id"], r["exclusion_reason"] or "no reason recorded") for r in excl) or "none"
    key_s = ", ".join("%s (%s)" % (k["case_id"], k["key_check"][8:]) for k in key_rev) or "none"
    out = [
        "# Workbook audit (generated by `python -m oe import`)", "",
        "Contains case IDs and counts only - no answers, titles or case text.", "",
        f"- Cases: {n}; eligible: {len(elig)}; excluded: {excl_s}",
        f"- Run Log rows: {len(sched)} (main {len(main)}, retest {len(rt)}); retest cases: {len({s['case_id'] for s in rt})}",
        f"- Run Log data-entry columns already containing values: {', '.join(filled_cols) or 'none (no collection recorded)'}",
        f"- Historical 2026 scores in Cases!O/Q: dx {h_dx}/{h_n}, management {h_mg}/{h_n} (historical; archived only)",
        f"- Leak-corrected text column F filled for {len(F)} cases; identical to original column E for {len(F_same)} of them.",
        f"- Answer-key checks needing human review: {len(key_rev)} case(s): {key_s}",
        f"- Correct-letter column J typed as values instead of formula in {len(typed)} rows (values checked against text above).",
        f"- 2026 PS+ prompts stored without the instruction prefix: {len(no_prefix)} cases.",
        f"- 2026 prompts that did not contain the full case text (shortened for the old limit): {len(trunc)} cases: {', '.join(str(r['case_id']) for r in trunc)}",
        f"- Case title appears verbatim inside the case text (title leak risk): {', '.join(map(str, title_in_text)) or 'none'}",
        f"- Reference diagnosis appears verbatim inside the case text (review): {', '.join(map(str, dx_in_text)) or 'none'}",
        f"- Case text shares >=10-word passages with the discussion (review): {', '.join(map(str, disc_overlap)) or 'none'}",
        "", "## Workbook settings snapshot", "",
    ] + [f"- **{k}**: {v}" for k, v in settings.items()]
    if problems:
        out += ["", "## Import problems", ""] + [f"- {p}" for p in problems]
    return "\n".join(out) + "\n"
