"""Static HTML run cards for manual collection through the OpenEvidence web app.

No automation of OpenEvidence: the page only shows what to select, a
copy-to-clipboard button for the locked prompt, which image files to attach,
and a checklist. Collectors still type results into collection_log.csv.
"""
from __future__ import annotations

import html
from pathlib import Path

from .collection import derive_runs
from .common import INPUT_LABEL, load_config, path, read_csv

CHECKLIST = [
    "Open a NEW chat (no history); memory/personalisation off",
    "Select the model shown on this card and confirm it in the selector",
    "Paste the prompt exactly (use the Copy button; do not edit)",
    "Image arm: attach exactly the listed prepared files in the same message",
    "Start timer on submit; stop when the answer finishes",
    "Save full response text + screenshot; record citations and source check",
]


def build(root, collector: str | None = None, batch: str | None = None, limit: int = 60,
          include_retests: bool = False) -> dict:
    cfg = load_config()
    version = cfg["prompt"]["active_version"]
    prompts = {(p["case_id"], p["input"]): p for p in read_csv(Path(root) / "prompts" / f"prompts_{version}.csv")}
    runs = derive_runs(read_csv(path(root, "schedule")), read_csv(path(root, "collection")))
    cards = []
    for rid, r in runs.items():
        s = r["schedule"]
        if r["status"] not in ("pending", "failed"):
            continue
        if s["run_type"] == "Retest" and not include_retests:
            continue
        if collector and s.get("collector_assigned") and s["collector_assigned"] != collector:
            continue
        if batch and s.get("batch") != batch:
            continue
        p = prompts.get((s["case_id"], s["input"]), {})
        cards.append({"run_id": rid, "case_id": s["case_id"], "model": s["model"],
                      "input": INPUT_LABEL[s["input"]], "order": s["run_order"], "type": s["run_type"],
                      "attempt": r["n_attempts"] + 1, "ready": p.get("ready", "No"),
                      "why": p.get("not_ready_reason", "prompt file missing"),
                      "files": p.get("prepared_files_to_upload", ""), "image_ids": p.get("image_ids_to_upload", ""),
                      "sha": p.get("prompt_sha256", ""), "prompt": p.get("prompt_text", "")})
        if len(cards) >= limit:
            break
    title = f"Run cards - {collector or 'all collectors'} - prompt {version}"
    body = []
    for c in cards:
        warn = "" if c["ready"] == "Yes" else f"<p class='bad'>NOT READY: {html.escape(c['why'])}. Do not run; if images cannot be uploaded, log status 'unavailable'.</p>"
        files = f"<p><b>Attach:</b> {html.escape(c['files'] or '-')} <span class='muted'>(IDs: {html.escape(c['image_ids'])})</span></p>" if c["input"] != "Text only" else ""
        body.append(f"""
<section class="card">
  <h2>{html.escape(c['run_id'])} <span class="muted">attempt {c['attempt']} - {c['type']} - order {c['order']} within case</span></h2>
  <p class="big">Model: <b>{c['model']}</b> &nbsp; Input: <b>{c['input']}</b></p>
  {warn}{files}
  <p class="muted">prompt_version {version} - prompt_sha256 {c['sha'][:16]}...</p>
  <textarea readonly id="p-{c['run_id']}">{html.escape(c['prompt'])}</textarea>
  <button onclick="cp('p-{c['run_id']}', this)">Copy prompt</button>
  <ul>{''.join(f'<li><label><input type=checkbox> {html.escape(x)}</label></li>' for x in CHECKLIST)}</ul>
</section>""")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Run cards</title>
<style>
:root{{--bg:#fff;--fg:#1b1b1b;--muted:#666;--card:#f6f7f9;--bad:#a40000}}
@media (prefers-color-scheme: dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--muted:#9aa;--card:#22262c;--bad:#ff8a8a}}}}
body{{font:15px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:900px;margin:auto;padding:16px}}
.card{{background:var(--card);border-radius:8px;padding:12px 16px;margin:16px 0}}
.muted{{color:var(--muted);font-size:13px}} .big{{font-size:18px}} .bad{{color:var(--bad);font-weight:600}}
textarea{{width:100%;height:140px;font:12px monospace;background:var(--bg);color:var(--fg)}}
button{{padding:6px 14px;margin-top:4px}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="muted">{len(cards)} runs, in schedule order. Contains case text: keep local, do not share or upload.</p>
{''.join(body)}
<script>function cp(id,b){{const t=document.getElementById(id);navigator.clipboard.writeText(t.value).then(()=>{{b.textContent='Copied';setTimeout(()=>b.textContent='Copy prompt',1500)}})}}</script>
</body></html>"""
    out = Path(root) / "worklists" / f"run_cards_{(collector or 'all')}_{(batch or 'next')}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return {"file": str(out), "cards": len(cards)}
