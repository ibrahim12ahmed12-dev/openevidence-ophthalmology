"""Small coordinator utilities: registry lock and image hashing."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .common import images_dir, path, read_csv, sha256_file, sha256_text, write_csv


def lock_registry(root, by: str) -> dict:
    """Fingerprint case IDs, text, options and keys. Later changes are flagged (C04)."""
    reg = read_csv(path(root, "registry"))
    keys = {k["case_id"]: k for k in read_csv(path(root, "answer_key"))}
    when = dt.datetime.now().isoformat(timespec="seconds")
    rows = [{"case_id": r["case_id"], "eligible": r["eligible"], "options_sha256": r["options_sha256"],
             "text_only_sha256": r["text_only_sha256"],
             "title_sha256": sha256_text(keys.get(r["case_id"], {}).get("case_title", "")),
             "correct_letter": keys.get(r["case_id"], {}).get("correct_letter", ""),
             "locked_by": by, "locked_at": when} for r in reg]
    write_csv(path(root, "registry_lock"), rows)
    return {"locked_cases": len(rows), "locked_at": when}


def hash_images(root) -> dict:
    """Record SHA-256 of prepared images that do not have one yet (never overwrites)."""
    imgs = read_csv(path(root, "images"))
    n = 0
    for i in imgs:
        fp = images_dir(root) / (i.get("prepared_filename") or "")
        if i.get("prepared_filename") and fp.is_file() and not i.get("prepared_sha256"):
            i["prepared_sha256"] = sha256_file(fp)
            n += 1
    if imgs:
        write_csv(path(root, "images"), imgs, list(imgs[0].keys()))
    return {"hashed": n}
