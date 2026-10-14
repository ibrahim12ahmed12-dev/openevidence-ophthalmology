"""Parse the fixed answer-format lines from a response.

The parser only PRE-FILLS grading packets. Graders confirm or correct every
value. A missing or malformed format line is flagged for review; it is never
scored as wrong by software.
"""
from __future__ import annotations

import re

from .common import norm_key, parse_options

MD = re.compile(r"[*_`#>]+")
DX_LINE = re.compile(r"^\s*(?:[-•\d.)\s]*)?(?:most likely |final |primary )?diagnosis\s*[:\-–]\s*(.+)$", re.I)
NS_LINE = re.compile(r"^\s*(?:[-•\d.)\s]*)?(?:best |recommended )?next(?:\s|-)?step\s*[:\-–]\s*(.*)$", re.I)
LETTER_START = re.compile(r"^\(?\s*([A-Da-d])\s*(?:\)|\.|:|,|\s|$)")
MULTI = re.compile(r"^\(?([A-D])\)?\.?\s*(?:,|/|&|\b(?i:or|and)\b|\+)\s*\(?([A-D])\b")
LETTER_ANY = re.compile(r"(?:option|answer|choice)\s*\(?([A-D])\b|\b([A-D])\)", re.I)


def parse_response(text: str, options_text: str = "") -> dict:
    lines = [MD.sub("", ln).strip() for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    head = lines[:12]  # the format asks for the lines at the TOP
    dx = next((m.group(1).strip() for ln in head if (m := DX_LINE.match(ln))), "")
    ns_raw = next((m.group(1).strip() for ln in head if (m := NS_LINE.match(ln))), None)
    flags = []
    letter = ""
    if not dx:
        flags.append("no 'Diagnosis:' line near top")
    if ns_raw is None:
        flags.append("no 'Next step:' line near top")
    else:
        mm = MULTI.match(ns_raw) if ns_raw else None
        m1 = LETTER_START.match(ns_raw) if ns_raw else None
        if mm and mm.group(1).upper() != mm.group(2).upper():
            letter = "MULTIPLE"
            flags.append("more than one option named")
        elif m1:
            letter = m1.group(1).upper()
        else:
            m2 = LETTER_ANY.search(ns_raw or "")
            if m2:
                letter = (m2.group(1) or m2.group(2)).upper()
                flags.append("letter found inside text, not at start - confirm")
            else:
                inferred = _infer_from_option_text(ns_raw or "", options_text)
                if inferred:
                    letter = ""
                    flags.append(f"no letter; text resembles option {inferred} - grader decides")
                else:
                    letter = "NONE?"
                    flags.append("'Next step:' line has no recognisable option letter")
    return {"auto_diagnosis": dx[:500], "auto_letter": letter,
            "format_complete": "Yes" if dx and letter in ("A", "B", "C", "D") else "No",
            "extraction_flags": "; ".join(flags)}


def _infer_from_option_text(s: str, options_text: str) -> str:
    opts = parse_options(options_text)
    if not s or not opts:
        return ""
    sk = norm_key(s)
    hits = [k for k, v in opts.items() if norm_key(v) and (norm_key(v) in sk or sk in norm_key(v))]
    return hits[0] if len(hits) == 1 else ""
