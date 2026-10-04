"""Draft image-arm (substitution) text for human review.

This module NEVER approves text. It proposes which paragraphs look like figure
legends, removes them in a draft, and lists every non-visual detail found in a
removed segment (age, laterality, timing, acuity, ...) so a reviewer can decide
what to move back into the vignette. Clinical facts are never rewritten.

Default rule (methodology Option A, workbook README item 1): remove figure
legends; keep the narrative vignette, including sentences that cite a figure,
and mark figure citations as "(Figure N attached)". Narrative sentences that
cite a figure AND state its findings are flagged, not removed.
"""
from __future__ import annotations

import re

from .common import path, read_csv, write_csv

LEGEND_START = re.compile(
    r"^\s*(?:[A-H](?:\s*(?:and|-|–)\s*[A-H])?,\s|\(?[A-H]\)\s|Figure\b|"
    r"(?:Color |Colour |Wide-?field |Ultra-?widefield |Montage |Slit-?lamp |External |Clinical |Fundus |"
    r"Anterior segment |Gross |Intraoperative |Serial |Representative |Baseline |Initial |Follow-up )?"
    r"(?:fundus|photograph|photographs|optical coherence|OCT|slit-?lamp|external|clinical photo|"
    r"computed tomograph|CT\b|magnetic resonance|MRI|fluorescein|indocyanine|ICG|ultrasound|ultrasonograph|"
    r"B-scan|histopatholog|hematoxylin|immunohisto|visual field|Humphrey|Goldmann|autofluorescence|"
    r"angiograph|electroretinogra|ERG|gonioscop|specular|confocal|topograph|biomicroscop|axial|coronal|sagittal|"
    r"T1|T2|images?\b|imaging\b|photomicrograph|microscop|cytolog|smear|stain))",
    re.I)
FIG_REF = re.compile(r"\((?:see\s+)?(?:e?Figure|Figures|Fig\.?)(?:[^()]{0,40})\)")
NONVISUAL = {
    "age": re.compile(r"\b\d{1,3}[- ](?:year|month|week|day)s?[- ]old\b|\bin (?:his|her|their) (?:early |mid-?|late )?\d0s\b", re.I),
    "laterality": re.compile(r"\b(?:right|left|both) eyes?\b|\b(?:OD|OS|OU)\b|\bbilateral(?:ly)?\b|\bunilateral\b", re.I),
    "timing": re.compile(r"\b\d+(?:\.\d+)?\s*(?:hours?|days?|weeks?|months?|years?)\s+(?:later|after|before|prior|earlier|post\w*)\b|"
                         r"\b(?:at presentation|at follow-up|on follow-up|postoperative(?:ly)?|preoperative(?:ly)?|at baseline|initial(?:ly)?|subsequent(?:ly)?)\b", re.I),
    "acuity_or_iop": re.compile(r"\b20/\d+\b|\b\d+\s*mm\s*Hg\b|\bvisual acuity\b", re.I),
    "treatment_or_history": re.compile(r"\b(?:after|following|treated with|received|underwent|status post)\b", re.I),
}
PANEL = re.compile(r"\(([A-H])(?:\s*(?:and|-|–|,)\s*[A-H])*\)|(?:^|[.;]\s+)[A-H], [A-Z]|\b[A-H] and [A-H],\s")
POINTER = re.compile(r"\b(?:arrows?|arrowheads?|asterisks?|insets?|scale bar|original magnification|hematoxylin)\b", re.I)
PARTICIPLE = re.compile(r"\b(?:showing|demonstrating|revealing|depicting|shows|demonstrates|reveals|shown|seen)\b", re.I)
NARRATIVE = re.compile(r"\b(?:presented|was referred|denied|reported|complained|underwent|was started|was admitted|"
                       r"history of|medical history|on examination|visual acuity was|was performed|were performed|"
                       r"returned|was treated|was noted to have|workup)\b", re.I)


def legend_score(p: str) -> int:
    s = p.strip()
    if not s:
        return -9
    sc = 2 * bool(LEGEND_START.match(s)) + 2 * bool(PANEL.search(s)) + bool(POINTER.search(s)) \
        + bool(PARTICIPLE.search(s)) - 2 * bool(NARRATIVE.search(s))
    if len(s) < 160 and not NARRATIVE.search(s):
        sc += 1  # short trailing captions ("Results of extraocular motility testing.")
    return sc


FINDING_WORDS = re.compile(r"\b(?:show(?:s|ed|ing)?|reveal(?:s|ed|ing)?|demonstrat\w+|disclos\w+|note[ds]?|with|depict\w*)\b", re.I)


def draft_for_text(text: str) -> dict:
    paras = [p for p in (text or "").split("\n")]
    keep, removed, flags = [], [], []
    scores = [legend_score(p) for p in paras]
    for i, p in enumerate(paras):
        s = p.strip()
        looks_legend = i > 0 and scores[i] >= 2
        # Legends are trailing paragraphs; a legend-like paragraph followed by narrative is kept.
        trailing = all(scores[j] >= 2 for j in range(i, len(paras)) if paras[j].strip())
        if looks_legend and trailing:
            removed.append(s)
            if scores[i] <= 2:
                flags.append(f"paragraph {i+1} removed with low legend score ({scores[i]}) - confirm it is a legend")
        else:
            if looks_legend:
                flags.append(f"paragraph {i+1} looks legend-like but is not trailing: kept")
            keep.append(p)
    draft = "\n".join(keep)
    n_refs = len(FIG_REF.findall(draft))
    draft = FIG_REF.sub(lambda m: m.group(0)[:-1].rstrip() + " attached)", draft)
    nonvisual = []
    for seg in removed:
        for kind, rx in NONVISUAL.items():
            for m in rx.finditer(seg):
                nonvisual.append(f"{kind}: '{m.group(0)}'")
    if not removed:
        flags.append("no trailing legend detected - reviewer must locate legends manually")
    if not n_refs and not removed:
        flags.append("no figure citation found - confirm the case has figures")
    for sent in re.split(r"(?<=[.!?])\s+", draft):
        if "attached)" in sent and FINDING_WORDS.search(sent):
            flags.append("narrative sentence cites a figure and may state its findings: '" + sent.strip()[:90] + "...'")
            break
    if nonvisual:
        flags.append("removed legend contains non-visual details - move any needed ones into the vignette")
    confidence = "low" if (not removed or len(flags) > 2) else ("medium" if flags else "high")
    return {"draft_image_arm_text": draft, "removed_segments": "\n---\n".join(removed),
            "n_removed": len(removed), "n_figure_citations": n_refs,
            "nonvisual_details_in_removed": "; ".join(dict.fromkeys(nonvisual)),
            "review_flags": " | ".join(flags), "draft_confidence": confidence}


def build_drafts(root, fill_empty: bool = False) -> dict:
    reg = read_csv(path(root, "registry"))
    out = []
    for r in reg:
        d = draft_for_text(r["text_only_input"])
        out.append({"case_id": r["case_id"], "eligible": r["eligible"],
                    "text_only_input": r["text_only_input"], **d})
    p = write_csv(path(root, "image_arm").with_name("image_arm_review_DRAFT.csv"), out)
    filled = 0
    if fill_empty:
        arm = read_csv(path(root, "image_arm"))
        drafts = {o["case_id"]: o for o in out}
        for a in arm:
            if a.get("status") in ("", "not_started") and not a.get("image_arm_text"):
                a["image_arm_text"] = drafts[a["case_id"]]["draft_image_arm_text"]
                a["status"] = "draft_needs_review"
                a["review_notes"] = ("AUTO-DRAFT: " + drafts[a["case_id"]]["review_flags"])[:500]
                filled += 1
        if arm:
            write_csv(path(root, "image_arm"), arm, list(arm[0].keys()))
    conf = {}
    for o in out:
        conf[o["draft_confidence"]] = conf.get(o["draft_confidence"], 0) + 1
    return {"drafts": str(p), "filled_as_draft": filled, "confidence": conf}
