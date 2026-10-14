"""Shared helpers: paths, CSV I/O, normalisation, hashing and study constants.

Only the Python standard library is used here so that every module except the
workbook importer (which needs openpyxl) runs on a bare Python 3.9+ install.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO / "config" / "study_config.json"
PROMPT_DIR = REPO / "config" / "prompt_versions"

MODELS = ["Osler", "Sackett", "Snow"]
INPUTS = ["text_only", "text_image"]
INPUT_LABEL = {"text_only": "Text only", "text_image": "Text + image"}
WORKBOOK_INPUT = {"Text only": "text_only", "Text + image": "text_image"}

# Relative layout of a data root (real: data/, synthetic: synthetic/demo_data/)
LAYOUT = {
    "source": "source",
    "registry": "registry/case_registry.csv",          # generated, contains case text
    "answer_key": "registry/answer_key_PRIVATE.csv",     # generated, graders/coordinator only
    "annotations": "registry/case_annotations.csv",     # human-edited (synonyms, year, ...)
    "image_arm": "registry/image_arm_text.csv",         # human-edited (substitution text)
    "images": "registry/images.csv",                    # human-edited image metadata
    "registry_lock": "registry/registry_lock.csv",      # fingerprint at lock time
    "historical": "registry/historical_2026_PRIVATE.csv",
    "workbook_schedule": "schedule/workbook_run_log_assignments.csv",
    "schedule": "schedule/run_schedule.csv",
    "prompts_dir": "prompts",
    "collection": "collection/collection_log.csv",
    "extraction": "grading/extraction_auto.csv",
    "response_key": "grading/private/response_key_PRIVATE.csv",
    "packets_dir": "grading/packets",
    "returns_dir": "grading/returns",
    "adjudication_packet": "grading/adjudication/adjudication_packet.csv",
    "adjudication_return": "grading/adjudication/adjudication_return.csv",
    "grades_final": "grading/grades_final.csv",
    "analysis": "analysis/analysis_dataset.csv",
    "reports_dir": "reports",
    "worklists_dir": "worklists",
}


def _deep_update(base: dict, upd: dict) -> dict:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_config(root: str | Path | None = None) -> dict:
    """Study config; a data root may carry config_override.json (used only by synthetic demos)."""
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if root is not None and (Path(root) / "config_override.json").exists():
        with open(Path(root) / "config_override.json", encoding="utf-8") as fh:
            _deep_update(cfg, json.load(fh))
    return cfg


def conditions(cfg: dict | None = None) -> list[dict]:
    cfg = cfg or load_config()
    return [dict(c) for c in cfg["design"]["conditions"]]


def cond_lookup(cfg: dict | None = None) -> dict[int, dict]:
    return {c["condition"]: c for c in conditions(cfg)}


SHARED_KEYS = {"registry", "answer_key", "annotations", "image_arm", "images", "registry_lock",
               "historical", "workbook_schedule", "source"}


def registry_root(root: str | Path) -> Path:
    """A pilot root shares the main root's registry and images (config_override
    'shared_registry_root'), so approvals made during the pilot carry over, while
    its schedule, prompts, collection log and grading stay separate."""
    o = Path(root) / "config_override.json"
    if o.exists():
        with open(o, encoding="utf-8") as fh:
            rel = json.load(fh).get("shared_registry_root")
        if rel:
            return (Path(root) / rel).resolve()
    return Path(root)


def path(root: str | Path, key: str) -> Path:
    base = registry_root(root) if key in SHARED_KEYS else Path(root)
    return base / LAYOUT[key]


def images_dir(root: str | Path) -> Path:
    return registry_root(root) / "images" / "prepared"


def read_csv(p: str | Path) -> list[dict]:
    p = Path(p)
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8-sig") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_csv(p: str | Path, rows: list[dict], fieldnames: list[str] | None = None) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for r in rows:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
    return p


def write_if_absent(p: str | Path, rows: list[dict], fieldnames: list[str]) -> bool:
    """Seed a human-edited file. Never overwrites existing work."""
    if Path(p).exists():
        return False
    write_csv(p, rows, fieldnames)
    return True


def sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def sha256_file(p: str | Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_ws(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def norm_key(s: str | None) -> str:
    """Aggressive normalisation for leak/consistency matching (not for display)."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def words(s: str | None) -> list[str]:
    return norm_key(s).split()


def shingles(s: str | None, k: int = 10) -> set[str]:
    w = words(s)
    return {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)}


STOPWORDS = set("""a an the of and or with without in on to for from by at as is are was
were be been case patient man woman girl boy child infant year old years eye eyes
right left bilateral unilateral after before during due secondary associated
syndrome disease disorder type acute chronic""".split())


def content_tokens(s: str | None, min_len: int = 5) -> set[str]:
    return {w for w in words(s) if len(w) >= min_len and w not in STOPWORDS}


def parse_options(options_text: str) -> dict[str, str]:
    """Split the published 'A. ...\\n B. ...' block into {letter: text}. Order preserved."""
    parts = re.split(r"\n\s*(?=[B-H]\.\s)", (options_text or "").strip())
    out: dict[str, str] = {}
    for p in parts:
        m = re.match(r"^\s*([A-H])\.\s*(.*)$", p, re.S)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def case_tag(case_id) -> str:
    return f"{int(case_id):03d}"


def run_id_for(case_id, condition, run_type: str) -> str:
    return f"{case_tag(case_id)}-C{int(condition)}" + ("-R" if run_type == "Retest" else "")


def is_synthetic_root(root: str | Path) -> bool:
    return (Path(root) / "SYNTHETIC_DATA_README.md").exists()


def ensure_dirs(root: str | Path) -> None:
    for key, rel in LAYOUT.items():
        p = Path(root) / rel
        (p if key.endswith("_dir") or key == "source" else p.parent).mkdir(parents=True, exist_ok=True)


def env_root(default: str = "data") -> str:
    return os.environ.get("OE_DATA_ROOT", str(REPO / default))
