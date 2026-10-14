"""Pilot Desk: a local, point-and-click interface for the 10-case pilot.

Start it by double-clicking "Start Pilot Desk" (or `python -m oe app`). It
runs a small web server on THIS computer only (127.0.0.1) and opens a browser
tab. Nothing is sent to the internet. Standard library only.

Pages
  /                    readiness checklist + the 10 pilot cases
  /case/<id>           six run cards in randomized order: copy prompt, attach files,
                       stopwatch, record the result
  /image-text/<id>     prep team: compare original vs draft, edit, approve
  /images/<id>         prep team: describe the prepared image files for a case
  /keys                COORDINATOR ONLY: answer keys awaiting confirmation
  /checks              run all quality checks (pilot folder)
  /export              create blinded grading packets for completed runs
"""
from __future__ import annotations

import datetime as dt
import email.parser
import email.policy
import html
import re
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from . import collection, figures, grading, importer, legend, pilot, prompts, validate
from .common import (INPUT_LABEL, images_dir, load_config, path, read_csv, sha256_file,
                     write_csv)

E = html.escape
STATE = {"main": None, "pilot": None}
LOCK = threading.Lock()

CSS = """
:root{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#deded8;--ok:#1e7a3c;--warn:#a45a00;--bad:#b3261e;--acc:#2b5fa8;--hl:#fff2b3;--del:#ffd9d6}
@media (prefers-color-scheme: dark){:root{--bg:#17181a;--fg:#e9e9e6;--muted:#a3a39c;--card:#212326;--line:#36383c;--ok:#6fcf8f;--warn:#f0b35a;--bad:#ff8a80;--acc:#8ab4f8;--hl:#5a4d00;--del:#5c1f1a}}
*{box-sizing:border-box}body{font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--fg);margin:0}
main{max-width:980px;margin:auto;padding:16px}a{color:var(--acc)}h1{font-size:24px;margin:8px 0 4px}h2{font-size:19px;margin:24px 0 8px}
.top{background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px}.top b{margin-right:16px}.top a{margin-right:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.pill{display:inline-block;border-radius:99px;padding:1px 10px;font-size:13px;font-weight:600;border:1px solid currentColor}
.ready,.completed{color:var(--ok)}.blocking,.failed{color:var(--bad)}.before\\ grading,.pending,.unavailable,.withdrawn{color:var(--warn)}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
textarea{width:100%;font:13px/1.4 ui-monospace,monospace;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px}
input,select{font:inherit;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 8px}
button,.btn{font:inherit;font-weight:600;background:var(--acc);color:#fff;border:0;border-radius:8px;padding:8px 14px;cursor:pointer;text-decoration:none;display:inline-block}
button.secondary{background:transparent;color:var(--acc);border:1px solid var(--acc)}
button:disabled{opacity:.35;cursor:not-allowed}
.muted{color:var(--muted);font-size:14px}.big{font-size:20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px 16px}
label{display:block;font-size:14px;color:var(--muted)}label input,label select{display:block;width:100%;margin-top:2px}
.warnbox{border-left:4px solid var(--warn);padding:8px 12px;background:var(--card);margin:10px 0}.badbox{border-left:4px solid var(--bad);padding:8px 12px;background:var(--card);margin:10px 0}
mark{background:var(--hl);color:inherit}del{background:var(--del);text-decoration:line-through}.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:700px){.cols{grid-template-columns:1fr}}pre{white-space:pre-wrap;font-size:13px}
.timer{font:600 22px ui-monospace,monospace;margin:0 10px}
"""

JS = """
function cp(id,b){const t=document.getElementById(id);navigator.clipboard.writeText(t.value).then(()=>{b.textContent='Copied ✓';setTimeout(()=>b.textContent='Copy prompt',1600)})}
const T={};function tick(id){const s=(Date.now()-T[id])/1000;document.getElementById('t-'+id).textContent=s.toFixed(0)+' s'}
function startT(id){T[id]=Date.now();T['i'+id]=setInterval(()=>tick(id),500)}
function stopT(id){if(!T[id])return;clearInterval(T['i'+id]);const s=((Date.now()-T[id])/1000).toFixed(0);document.getElementById('d-'+id).value=s}
document.addEventListener('DOMContentLoaded',()=>{const n=new Date();const p=x=>String(x).padStart(2,'0');
document.querySelectorAll('.fill-date').forEach(e=>{if(!e.value)e.value=n.getFullYear()+'-'+p(n.getMonth()+1)+'-'+p(n.getDate())});
document.querySelectorAll('.fill-time').forEach(e=>{if(!e.value)e.value=p(n.getHours())+':'+p(n.getMinutes())});
document.querySelectorAll('.fill-tz').forEach(e=>{if(!e.value)e.value=Intl.DateTimeFormat().resolvedOptions().timeZone})});
"""


def page(title, body):
    nav = ("<div class='top'><b>Pilot Desk</b><a href='/'>Home</a><a href='/checks'>Run checks</a>"
           "<a href='/figures'>Figures</a><a href='/export'>Export for grading</a><a href='/keys'>Answer keys (coordinator)</a></div>")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{E(title)}</title><style>{CSS}</style><script>{JS}</script></head><body>{nav}<main>{body}</main></body></html>")


# ----------------------------------------------------------------------------- bootstrap

def bootstrap(main_root: Path) -> list[str]:
    """First start: import the workbook and create the pilot folder if needed."""
    log = []
    if not path(main_root, "registry").exists():
        if not list((main_root / "source").glob("*.xlsx")):
            raise SystemExit(f"Put the study workbook (.xlsx) in {main_root/'source'} and start again.")
        importer.import_workbook(main_root)
        from . import schedule
        schedule.build(main_root)
        legend.build_drafts(main_root)
        prompts.generate(main_root)
        collection.init_log(main_root)
        log.append("Imported the workbook and built the main schedule.")
    if not (main_root / "pilot" / "config_override.json").exists():
        r = pilot.setup(main_root)
        log.append(f"Created the pilot folder with cases {r['cases']}.")
    if not path(main_root, "image_arm").with_name("image_arm_review_DRAFT.csv").exists():
        legend.build_drafts(main_root)
    return log


def refresh_prompts():
    prompts.generate(STATE["pilot"])


# ----------------------------------------------------------------------------- views

def v_home():
    pr = STATE["pilot"]
    cfg = load_config(pr)
    items = pilot.readiness(pr)
    runs = collection.derive_runs(read_csv(path(pr, "schedule")), read_csv(path(pr, "collection")))
    arm = {a["case_id"]: a for a in read_csv(path(pr, "image_arm"))}
    imgs = read_csv(path(pr, "images"))
    reg = {r["case_id"]: r for r in read_csv(path(pr, "registry"))}
    blocking = [i for i in items if i["status"] == "blocking"]
    so = pilot.signoff(pr)
    rows = "".join(f"<tr><td><span class='pill {E(i['status'])}'>{E(i['status'])}</span></td><td>{E(i['item'])}<div class='muted'>{E(i['detail'])}</div></td></tr>" for i in items)
    crow = ""
    for c in pilot.pilot_cases(pr):
        done = sum(1 for r in runs.values() if r["schedule"]["case_id"] == c and r["status"] in ("completed", "unavailable"))
        ni = len([i for i in imgs if i["case_id"] == c])
        crow += (f"<tr><td class='big'>{E(c)}</td><td>{E(reg.get(c, {}).get('subspecialty', ''))}</td>"
                 f"<td><a href='/image-text/{c}'>{E(arm.get(c, {}).get('status', 'not_started'))}</a></td>"
                 f"<td><a href='/images/{c}'>{ni} file(s)</a></td><td>{done}/6</td>"
                 f"<td><a class='btn' href='/case/{c}'>Record runs</a></td></tr>")
    head = ("<div class='badbox'><b>Not ready for pilot collection yet.</b> Resolve the red items below.</div>" if blocking
            else "<div class='warnbox'><b>Ready to collect.</b> Items marked 'before grading' can wait until collection ends.</div>")
    return page("Pilot Desk", f"""
<h1>10-case pilot</h1>
<p class='muted'>Pilot data are stored separately in <code>{E(str(pr))}</code> and are never mixed with main-study data.
Prompt version <b>{E(cfg['prompt']['active_version'])}</b>: source-exclusion instruction <b>off</b>; answer lines requested <b>at the top</b>.</p>
{head}
<h2>Readiness</h2><div class='card'><table>{rows}</table></div>
<h2>Pilot cases</h2>
<p class='muted'>Work left to right: approve the image-arm text, describe the images, then record the six runs.</p>
<div class='card'><table><tr><th>Case ID</th><th>Subspecialty</th><th>Image-arm text</th><th>Images</th><th>Runs done</th><th></th></tr>{crow}</table></div>
<h2>Pilot sign-off</h2>
<form method='post' action='/signoff' enctype='multipart/form-data' class='card'>
<p class='muted'>Before the first run, open OpenEvidence, confirm Osler, Sackett and Snow appear in the model selector and that an image can be attached, and note any version text.</p>
<div class='grid'><label>Model selector checked by (initials)<input name='selector_checked_by' value='{E(so.get("selector_checked_by", ""))}'></label>
<label>Date checked<input name='selector_checked_date' class='fill-date' value='{E(so.get("selector_checked_date", ""))}'></label>
<label>What you saw (version text, upload limit)<input name='selector_notes' value='{E(so.get("selector_notes", ""))}'></label>
<label>Collector(s)<input name='collectors' value='{E(so.get("collectors", ""))}'></label>
<label>Grader 1 (G1)<input name='grader_1' value='{E(so.get("grader_1", ""))}'></label>
<label>Grader 2 (G2)<input name='grader_2' value='{E(so.get("grader_2", ""))}'></label>
<label>Adjudicator<input name='adjudicator' value='{E(so.get("adjudicator", ""))}'></label></div>
<p class='muted'>Graders should not grade runs they collected.</p><p><button>Save sign-off</button></p></form>
""")


def v_case(cid, msg=""):
    pr = STATE["pilot"]
    cfg = load_config(pr)
    if cid not in pilot.pilot_cases(pr):
        return page("Not a pilot case", f"<p>Case {E(cid)} is not in the pilot.</p>")
    sched = [s for s in read_csv(path(pr, "schedule")) if s["case_id"] == cid]
    runs = collection.derive_runs(sched, read_csv(path(pr, "collection")))
    pmap = {(p["case_id"], p["input"]): p for p in read_csv(Path(pr) / "prompts" / f"prompts_{cfg['prompt']['active_version']}.csv")}
    cards = ""
    for s in sorted(sched, key=lambda x: int(x["run_order"])):
        r = runs[s["run_id"]]
        p = pmap.get((cid, s["input"]), {})
        rid = s["run_id"]
        status = r["status"]
        hist = "".join(f"<li>attempt {E(str(a.get('attempt_no')))}: {E(a.get('status', ''))} {E(a.get('failure_reason', ''))}</li>"
                       for a in r["attempts"] if (a.get("status") or "").strip())
        head = (f"<h2>Run {E(s['run_order'])} of 6 &nbsp;·&nbsp; <span class='big'>{E(s['model'])}</span> &nbsp;·&nbsp; {E(INPUT_LABEL[s['input']])} "
                f"<span class='pill {status}'>{status}</span></h2><p class='muted'>Run ID {E(rid)}</p>")
        if status in ("completed", "unavailable", "withdrawn"):
            cards += f"<div class='card'>{head}<ul class='muted'>{hist}</ul></div>"
            continue
        if p.get("ready") != "Yes":
            unav = "unavailable" in (p.get("not_ready_reason") or "")
            cards += f"""<div class='card'>{head}<div class='badbox'>Not ready: {E(p.get('not_ready_reason', 'prompt missing'))}</div>
{form_unavailable(rid) if unav else ''}</div>"""
            continue
        files = ""
        if s["input"] == "text_image":
            files = f"<div class='warnbox'><b>Attach these files in the same message:</b> {E(p.get('prepared_files_to_upload', ''))}<br><span class='muted'>from {E(str(images_dir(pr)))}</span></div>"
        cards += f"""<div class='card'>{head}
<ol><li>Open a <b>new chat</b> in OpenEvidence (no earlier messages).</li>
<li>Select <b>{E(s['model'])}</b> in the model selector and check it is selected.</li>
<li>Copy the prompt below and paste it unchanged.{' Attach the image files.' if s['input'] == 'text_image' else ''}</li>
<li>Press <b>Start</b> as you submit; press <b>Stop</b> when the answer has finished.</li></ol>
{files}
<textarea id='p-{rid}' rows='6' readonly>{E(p['prompt_text'])}</textarea>
<p><button type='button' onclick="cp('p-{rid}',this)">Copy prompt</button>
<button type='button' class='secondary' onclick="startT('{rid}')">Start</button><span class='timer' id='t-{rid}'>0 s</span>
<button type='button' class='secondary' onclick="stopT('{rid}')">Stop</button></p>
{form_record(rid, s, p)}
{('<p class="muted">Earlier attempts:</p><ul class="muted">' + hist + '</ul>') if hist else ''}
</div>"""
    note = f"<div class='warnbox'>{msg}</div>" if msg else ""
    return page(f"Case {cid}", f"<p><a href='/'>← all cases</a></p><h1>Case {E(cid)}: record the six runs</h1>"
                f"<p class='muted'>Do the runs in the order shown (it is randomized). The case title and answers are deliberately not shown here.</p>{note}{cards}")


def form_record(rid, s, p):
    img = s["input"] == "text_image"
    return f"""<form method='post' action='/record' enctype='multipart/form-data'>
<input type='hidden' name='run_id' value='{E(rid)}'>
<div class='grid'>
<label>Result<select name='status'><option value='completed'>Completed - got an answer</option>
<option value='failed'>Failed - error / wrong model / upload problem (will retry)</option></select></label>
<label>Your initials<input name='collector' required></label>
<label>Date<input name='run_date' class='fill-date'></label><label>Time (24 h)<input name='run_time' class='fill-time'></label>
<label>Time zone<input name='timezone' class='fill-tz'></label>
<label>Response time (seconds)<input name='response_duration_s' id='d-{E(rid)}' inputmode='numeric'></label>
<label>Number of citations<input name='citation_count' inputmode='numeric'></label>
<label>Did any citation point to the source JAMA case, its answer, or a report of the same patient?
<select name='source_retrieved'><option value=''>- choose -</option><option>No</option><option>Yes</option><option>Unclear</option></select></label>
{"<label>Image IDs attached<input name='image_ids_uploaded' value='" + E(p.get('image_ids_to_upload', '')) + "'></label>" if img else ""}
<label>Screenshot (optional upload)<input type='file' name='screenshot' accept='image/*,.pdf'></label>
</div>
<label>Paste the FULL response, including the reference list<textarea name='response_text' rows='8'></textarea></label>
<label><input type='checkbox' name='model_selection_confirmed' value='Yes' style='display:inline;width:auto'> I confirmed the model was selected</label>
<label><input type='checkbox' name='new_session_confirmed' value='Yes' style='display:inline;width:auto'> This was a new chat</label>
<label>If failed: what went wrong? / any note (which citation was the source, banner messages, etc.)<input name='notes'></label>
<p><button>Save this run</button></p></form>"""


def form_unavailable(rid):
    return f"""<form method='post' action='/record' enctype='multipart/form-data'>
<input type='hidden' name='run_id' value='{E(rid)}'><input type='hidden' name='status' value='unavailable'>
<div class='grid'><label>Your initials<input name='collector' required></label>
<label>Reason<input name='notes' value='images cannot be uploaded' required></label></div>
<p><button class='secondary'>Mark this run as unavailable (not run, not wrong)</button></p></form>"""


def save_record(f: dict, files: dict) -> tuple[str, str]:
    pr = STATE["pilot"]
    cfg = load_config(pr)
    rid = f.get("run_id", "")
    sched = {s["run_id"]: s for s in read_csv(path(pr, "schedule"))}
    s = sched.get(rid)
    if not s:
        return "", "Unknown run."
    with LOCK:
        coll = read_csv(path(pr, "collection"))
        runs = collection.derive_runs([s], coll)
        if runs[rid]["status"] in ("completed", "unavailable", "withdrawn"):
            return s["case_id"], f"Run {rid} is already {runs[rid]['status']}; nothing saved. Ask the coordinator if this is a mistake."
        st = f.get("status", "")
        errs = []
        if not f.get("collector", "").strip():
            errs.append("your initials")
        if st == "completed":
            for k, lab in [("response_text", "the full response"), ("response_duration_s", "response time"),
                           ("citation_count", "number of citations"), ("source_retrieved", "the source-citation question")]:
                if not f.get(k, "").strip():
                    errs.append(lab)
            if f.get("model_selection_confirmed") != "Yes" or f.get("new_session_confirmed") != "Yes":
                errs.append("the two confirmation tick boxes")
            if f.get("response_duration_s") and not re.fullmatch(r"\d+(\.\d+)?", f["response_duration_s"].strip()):
                errs.append("response time as a number of seconds")
            if f.get("citation_count") and not f["citation_count"].strip().isdigit():
                errs.append("citations as a whole number")
        elif st in ("failed", "unavailable"):
            if not f.get("notes", "").strip():
                errs.append("what went wrong")
        else:
            errs.append("a valid result")
        if errs:
            return s["case_id"], "Not saved. Please add: " + ", ".join(errs) + "."
        recorded = [a for a in coll if a["run_id"] == rid and (a.get("status") or "").strip()]
        n = len(recorded) + 1
        p = {(x["case_id"], x["input"]): x for x in read_csv(Path(pr) / "prompts" / f"prompts_{cfg['prompt']['active_version']}.csv")}.get((s["case_id"], s["input"]), {})
        row = {h: s[h] for h in collection.HELPER}
        row.update({"run_id": rid, "attempt_no": n, "status": st, "collector": f.get("collector", "").strip(),
                    "failure_reason": f.get("notes", "") if st != "completed" else "",
                    "notes": f.get("notes", "") if st == "completed" else "",
                    "prompt_version": p.get("prompt_version", "") if st != "unavailable" else "",
                    "prompt_sha256": p.get("prompt_sha256", "") if st != "unavailable" else "",
                    "model_selection_confirmed": f.get("model_selection_confirmed", "No"),
                    "new_session_confirmed": f.get("new_session_confirmed", "No"),
                    "run_date": f.get("run_date", ""), "run_time": f.get("run_time", ""), "timezone": f.get("timezone", ""),
                    "response_duration_s": f.get("response_duration_s", ""), "citation_count": f.get("citation_count", ""),
                    "source_retrieved": f.get("source_retrieved", ""), "response_text": f.get("response_text", ""),
                    "retrieval_assessed_by": f.get("collector", "") if f.get("source_retrieved") else "",
                    "retrieval_notes": f.get("notes", "") if f.get("source_retrieved") == "Yes" else ""})
        if s["input"] == "text_image" and st == "completed":
            ids = [x.strip() for x in f.get("image_ids_uploaded", "").split(";") if x.strip()]
            row["image_ids_uploaded"] = ";".join(ids)
            row["n_images_uploaded"] = len(ids)
        if st == "completed":
            rd = Path(pr) / "collection" / "responses"
            rd.mkdir(parents=True, exist_ok=True)
            (rd / f"{rid}_a{n}.txt").write_text(f.get("response_text", ""), encoding="utf-8")
        shot = files.get("screenshot")
        if shot and shot[1]:
            sd = Path(pr) / "collection" / "screenshots"
            sd.mkdir(parents=True, exist_ok=True)
            ext = Path(shot[0]).suffix.lower()[:6] or ".png"
            fn = sd / f"{rid}_a{n}{ext}"
            fn.write_bytes(shot[1])
            row["screenshot_path"] = str(fn.relative_to(pr))
        # fill the pre-made blank attempt-1 row, otherwise append
        blank = next((a for a in coll if a["run_id"] == rid and not (a.get("status") or "").strip()), None)
        if blank is not None:
            blank.update({k: str(v) for k, v in row.items()})
        else:
            coll.append({k: str(v) for k, v in row.items()})
        write_csv(path(pr, "collection"), coll, collection.FIELDS)
    msg = {"completed": f"Saved run {rid} (attempt {n}).", "failed": f"Saved failed attempt {n} for {rid}. Do the run again in a new chat.",
           "unavailable": f"Run {rid} marked unavailable."}[st]
    return s["case_id"], msg


def v_image_text(cid, msg=""):
    pr = STATE["pilot"]
    drafts = {d["case_id"]: d for d in read_csv(path(pr, "image_arm").with_name("image_arm_review_DRAFT.csv"))}
    arm = {a["case_id"]: a for a in read_csv(path(pr, "image_arm"))}
    d, a = drafts.get(cid), arm.get(cid, {})
    if not d:
        return page("Not found", "<p>No draft for this case.</p>")
    orig = E(d["text_only_input"])
    nonvis = re.findall(r"'([^']+)'", d["nonvisual_details_in_removed"])
    for seg in [x for x in d["removed_segments"].split("\n---\n") if x.strip()]:
        esc = E(seg)
        for nv in dict.fromkeys(nonvis):
            esc = esc.replace(E(nv), f"<mark>{E(nv)}</mark>")
        orig = orig.replace(E(seg), f"<del>{esc}</del>")
    current = a.get("image_arm_text") or d["draft_image_arm_text"]
    shown = E(current).replace("attached)", "<mark>attached</mark>)")
    flags = "".join(f"<li>{E(x)}</li>" for x in d["review_flags"].split(" | ") if x.strip())
    st = a.get("status", "not_started")
    note = f"<div class='warnbox'>{msg}</div>" if msg else ""
    return page(f"Image text {cid}", f"""<p><a href='/'>← all cases</a></p><h1>Case {E(cid)}: image-arm text</h1>{note}
<p>Status: <span class='pill {'ready' if st == 'approved' else 'blocking'}'>{E(st)}</span> {E(a.get('approved_by', ''))} {E(a.get('approved_date', ''))}</p>
<div class='card'><b>Rule (provisional design: substitution).</b> Remove the written figure legend because the image replaces it.
Keep everything that is not a visual finding (age, which eye, timing, history). Keep narrative sentences that cite a figure, written as "(Figure N attached)".
Do not rewrite clinical facts.</div>
<div class='card'><b>Please check:</b><ul>{flags or '<li>No automatic flags. Still read it once.</li>'}</ul>
<p class='muted'>Legend: <del>struck through</del> = proposed for removal; <mark>highlighted</mark> = needs your attention (non-visual detail inside a removed legend, or a figure reference to check).</p></div>
<div class='cols'><div class='card'><b>Original (text-only arm)</b><pre>{orig}</pre></div>
<div class='card'><b>Proposed image-arm text</b><pre>{shown}</pre></div></div>
<form method='post' action='/image-text/{E(cid)}' enctype='multipart/form-data' class='card'>
<label>Edit the image-arm text here if needed<textarea name='image_arm_text' rows='14'>{E(current)}</textarea></label>
<div class='grid'><label>Your initials<input name='who' required></label>
<label>Decision<select name='decision'><option value='draft_needs_review'>Save as draft</option><option value='approved'>Approve for collection</option></select></label></div>
<label>Notes (what you changed and why)<input name='notes' value='{E(a.get('review_notes', '') if not a.get('review_notes', '').startswith('AUTO') else '')}'></label>
<p><button>Save</button></p></form>""")


def save_image_text(cid, f):
    pr = STATE["pilot"]
    with LOCK:
        arm = read_csv(path(pr, "image_arm"))
        row = next((a for a in arm if a["case_id"] == cid), None)
        if row is None or not f.get("who", "").strip() or not f.get("image_arm_text", "").strip():
            return "Not saved: initials and text are required."
        row["image_arm_text"] = f["image_arm_text"].replace("\r\n", "\n")
        row["edited_by"] = f["who"].strip()
        row["review_notes"] = f.get("notes", "")
        if f.get("decision") == "approved":
            row.update(status="approved", approved_by=f["who"].strip(), approved_date=dt.date.today().isoformat())
        else:
            row.update(status="draft_needs_review", approved_by="", approved_date="")
        write_csv(path(pr, "image_arm"), arm, list(arm[0].keys()))
    refresh_prompts()
    return "Saved." + (" Approved for collection." if f.get("decision") == "approved" else "")


MODS = ["Fundus photography", "OCT", "Slit lamp / anterior segment", "Fluorescein / ICG angiography", "Visual fields",
        "CT / MRI", "External photography", "Histopathology", "Ultrasound", "Electrophysiology", "Other"]


def v_images(cid, msg=""):
    pr = STATE["pilot"]
    folder = images_dir(pr)
    folder.mkdir(parents=True, exist_ok=True)
    found = sorted(p.name for p in folder.glob(f"IMG-{int(cid):03d}-*") if p.is_file())
    rows = {i["prepared_filename"]: i for i in read_csv(path(pr, "images")) if i["case_id"] == cid}
    unav = any((i.get("availability") or "").startswith("unavailable") for i in read_csv(path(pr, "images")) if i["case_id"] == cid)
    trs = ""
    for k, fn in enumerate(found):
        r = rows.get(fn, {})
        mods = set((r.get("modality") or "").split(";"))
        opts = "".join(f"<label style='display:inline-block;margin-right:10px'><input type='checkbox' name='mod_{k}' value='{E(m)}' style='display:inline;width:auto' {'checked' if m in mods else ''}> {E(m)}</label>" for m in MODS)
        trs += f"""<div class='card'><b>{E(fn)}</b><input type='hidden' name='file_{k}' value='{E(fn)}'>
<div class='grid'><label>Figure number<input name='fig_{k}' value='{E(r.get('figure_number', ''))}'></label>
<label>Original file name (as downloaded)<input name='orig_{k}' value='{E(r.get('original_filename', ''))}'></label></div>
<p class='muted'>Imaging modality (tick all that apply)</p>{opts}
<label>Preparation steps (what you cropped, split, etc.)<input name='prep_{k}' value='{E(r.get('preparation_steps', ''))}'></label>
<label><input type='checkbox' name='clear_{k}' value='cleared' style='display:inline;width:auto' {'checked' if r.get('label_or_caption_flag') == 'cleared' else ''}>
I checked this image: no caption, panel label or text that names the diagnosis</label></div>"""
    note = f"<div class='warnbox'>{msg}</div>" if msg else ""
    return page(f"Images {cid}", f"""<p><a href='/'>← all cases</a></p><h1>Case {E(cid)}: image files</h1>{note}
<div class='card'><ol><li>Download the published figures at the highest resolution. Keep the originals unchanged in a separate folder.</li>
<li>Crop out panel letters, captions and any text naming a diagnosis. Keep arrows.</li>
<li>Save the prepared copies in <code>{E(str(folder))}</code> named <b>IMG-{int(cid):03d}-1.png</b>, <b>IMG-{int(cid):03d}-2.png</b>, ... (neutral names only).</li>
<li>Reload this page, describe each file and press Save. The same files will be used for all three models.</li></ol></div>
<form method='post' action='/images/{E(cid)}' enctype='multipart/form-data'>
{trs or "<div class='badbox'>No prepared files found yet for this case.</div>"}
<input type='hidden' name='n' value='{len(found)}'>
<div class='card'><label><input type='checkbox' name='unavailable' value='1' style='display:inline;width:auto' {'checked' if unav and not found else ''}>
The figures for this case cannot be uploaded (e.g. video only). The image runs will be marked unavailable, not wrong.</label>
<label>Your initials<input name='who' required></label><p><button>Save</button></p></div></form>""")


def save_images(cid, f, multi):
    pr = STATE["pilot"]
    who = f.get("who", "").strip()
    if not who:
        return "Not saved: initials required."
    with LOCK:
        allimg = [i for i in read_csv(path(pr, "images")) if i["case_id"] != cid]
        new = []
        n = int(f.get("n", "0") or 0)
        for k in range(n):
            fn = f.get(f"file_{k}", "")
            fp = images_dir(pr) / fn
            if not fn or not fp.exists():
                continue
            new.append({"case_id": cid, "image_id": Path(fn).stem, "figure_number": f.get(f"fig_{k}", ""),
                        "original_filename": f.get(f"orig_{k}", ""), "prepared_filename": fn,
                        "prepared_sha256": sha256_file(fp), "modality": ";".join(multi.get(f"mod_{k}", [])),
                        "availability": "available", "preparation_steps": f.get(f"prep_{k}", ""),
                        "label_or_caption_flag": "cleared" if f.get(f"clear_{k}") else "needs_review",
                        "label_review_by": who if f.get(f"clear_{k}") else ""})
        if f.get("unavailable") and not new:
            new.append({"case_id": cid, "image_id": f"IMG-{int(cid):03d}-0", "availability": "unavailable_video_only",
                        "unavailable_reason": "figures cannot be uploaded", "label_review_by": who})
        write_csv(path(pr, "images"), allimg + new, importer.IMAGE_FIELDS)
    refresh_prompts()
    return f"Saved {len(new)} image record(s)."


def v_keys(msg=""):
    pr = STATE["pilot"]
    conf = read_csv(path(pr, "answer_key").with_name("answer_key_confirmations.csv"))
    keys = {k["case_id"]: k for k in read_csv(path(pr, "answer_key"))}
    reg = {r["case_id"]: r for r in read_csv(path(pr, "registry"))}
    cards = ""
    for c in conf:
        k, r = keys.get(c["case_id"], {}), reg.get(c["case_id"], {})
        cards += f"""<div class='card'><h2>Case {E(c['case_id'])} <span class='pill {'ready' if c.get('confirmed_letter') else 'blocking'}'>{'confirmed ' + E(c.get('confirmed_letter', '')) if c.get('confirmed_letter') else 'awaiting confirmation'}</span></h2>
<p><b>Why flagged:</b> {E(c['issue'])}</p>
<table><tr><th>Workbook field</th><th>Content</th></tr>
<tr><td>H · answer options</td><td><pre>{E(r.get('answer_options', ''))}</pre></td></tr>
<tr><td>I · correct next step (first line)</td><td>{E(k.get('correct_answer_text', ''))}</td></tr>
<tr><td>I · remainder</td><td><pre>{E(k.get('answer_key_explanation', '')[:1200])}{'…' if len(k.get('answer_key_explanation', '')) > 1200 else ''}</pre></td></tr>
<tr><td>J · stored letter</td><td><b>{E(c['workbook_letter'])}</b></td></tr>
<tr><td>K · correct dx</td><td>{E(k.get('reference_diagnosis', ''))}</td></tr></table>
<form method='post' action='/keys' enctype='multipart/form-data'><input type='hidden' name='case_id' value='{E(c['case_id'])}'>
<div class='grid'><label>Confirmed correct letter<select name='letter'><option value=''>- choose -</option>{''.join(f"<option {'selected' if c.get('confirmed_letter') == L else ''}>{L}</option>" for L in 'ABCD')}</select></label>
<label>Your initials<input name='who' required></label><label>Evidence (e.g. checked the JAMA article answer)<input name='note' value='{E(c.get('evidence_note', ''))}'></label></div>
<p><button>Save confirmation</button></p></form></div>"""
    note = f"<div class='warnbox'>{msg}</div>" if msg else ""
    return page("Answer keys", f"""<h1>Answer keys awaiting confirmation</h1>
<div class='badbox'><b>Coordinator only.</b> This page shows answers. Do not open it on a collector's screen.</div>{note}
<p class='muted'>Check each against the published JAMA article. Your confirmation is stored in <code>answer_key_confirmations.csv</code>; the workbook is not changed.</p>{cards or "<p>No answer keys awaiting confirmation.</p>"}
{v_synonyms()}""")


def v_synonyms():
    pr = STATE["pilot"]
    keys = {k["case_id"]: k for k in read_csv(path(pr, "answer_key"))}
    ann = {a["case_id"]: a for a in read_csv(path(pr, "annotations"))}
    rows = ""
    for c in pilot.pilot_cases(pr):
        a = ann.get(c, {})
        rows += (f"<tr><td class='big'>{E(c)}</td><td>{E(keys.get(c, {}).get('reference_diagnosis', ''))}</td>"
                 f"<td><input name='syn_{E(c)}' value='{E(a.get('accepted_dx_synonyms', ''))}' style='width:100%'></td>"
                 f"<td><input name='year_{E(c)}' value='{E(a.get('publication_year', ''))}' size='5'></td></tr>")
    return f"""<h2>Accepted diagnosis synonyms (pilot cases)</h2>
<form method='post' action='/synonyms' enctype='multipart/form-data' class='card'>
<p class='muted'>Write these <b>before grading</b>, using the 2026 rules. Separate synonyms with semicolons. Graders see them in their packets.</p>
<table><tr><th>Case</th><th>Published diagnosis (col K)</th><th>Accepted synonyms</th><th>Year</th></tr>{rows}</table>
<label>Your initials<input name='who' required></label><p><button>Save synonyms</button></p></form>"""


def save_synonyms(f):
    pr = STATE["pilot"]
    who = f.get("who", "").strip()
    if not who:
        return "Not saved: initials required."
    with LOCK:
        ann = read_csv(path(pr, "annotations"))
        for a in ann:
            c = a["case_id"]
            if f"syn_{c}" in f:
                if f[f"syn_{c}"].strip() != a.get("accepted_dx_synonyms", ""):
                    a.update(accepted_dx_synonyms=f[f"syn_{c}"].strip(), synonyms_finalized_by=who,
                             synonyms_finalized_date=dt.date.today().isoformat())
                a["publication_year"] = f.get(f"year_{c}", a.get("publication_year", "")).strip()
        write_csv(path(pr, "annotations"), ann, importer.ANNOTATION_FIELDS)
    return "Synonyms saved."


def save_key(f):
    pr = STATE["pilot"]
    L, who = f.get("letter", "").strip().upper(), f.get("who", "").strip()
    if L not in ("A", "B", "C", "D") or not who:
        return "Not saved: choose a letter and add initials."
    p = path(pr, "answer_key").with_name("answer_key_confirmations.csv")
    with LOCK:
        rows = read_csv(p)
        for r in rows:
            if r["case_id"] == f.get("case_id"):
                r.update(confirmed_letter=L, confirmed_by=who, confirmed_date=dt.date.today().isoformat(), evidence_note=f.get("note", ""))
        write_csv(p, rows, importer.CONFIRM_FIELDS)
        importer.apply_confirmations(pr)
    return f"Case {f.get('case_id')}: letter {L} confirmed."


def v_checks():
    pr = STATE["pilot"]
    r = validate.run(pr, "collection")
    md = (Path(pr) / "reports" / "validation_report_collection.md").read_text(encoding="utf-8")
    body = E(md)
    body = re.sub(r"^## (ERROR.*)$", r"<h2 class='blocking'>\1</h2>", body, flags=re.M)
    body = re.sub(r"^## (WARNING.*)$", r"<h2 class='pending'>\1</h2>", body, flags=re.M)
    body = re.sub(r"^## (INFO.*)$", r"<h2 class='muted'>\1</h2>", body, flags=re.M)
    c = r["counts"]
    return page("Checks", f"<h1>Quality checks (pilot folder)</h1><p class='big'><b class='blocking'>{c.get('ERROR', 0)} errors</b> · "
                f"<b class='pending'>{c.get('WARNING', 0)} warnings</b> · {c.get('INFO', 0)} notes</p>"
                f"<p class='muted'>Errors must be fixed. Warnings need a decision. Saved to reports/validation_report_collection.md.</p>"
                f"<div class='card'><pre>{body}</pre></div>")


def v_export(done=None, merged=None):
    pr = STATE["pilot"]
    runs = collection.derive_runs(read_csv(path(pr, "schedule")), read_csv(path(pr, "collection")))
    n_c = sum(r["status"] == "completed" for r in runs.values())
    issued = len(read_csv(path(pr, "response_key")))
    res = ""
    if done:
        pg = done["per_grader"]
        res = (f"<div class='warnbox'><b>Done.</b> {done['new_response_ids']} new response(s) given neutral IDs. "
               + "; ".join(f"{g}: {v['primary']} to grade, {v['interp']} image-interpretation" for g, v in pg.items()) + "</div>")
    return page("Export", f"""<h1>Export for grading</h1>{res}
<p>{n_c} completed pilot run(s); {issued} already exported.</p>
<div class='card'><ol><li>Press the button. Each grader gets their own file with a different random order and no model or condition information.</li>
<li>Send <b>only</b> each grader's own files plus the <code>responses</code> folder from <code>{E(str(Path(pr) / 'grading' / 'packets'))}</code>.</li>
<li>Do <b>not</b> send anything from <code>grading/private</code> (it links responses to models).</li>
<li>Graders open their CSV in Excel, fill the grey columns, save it under the same name and return it; put returned files in <code>{E(str(Path(pr) / 'grading' / 'returns'))}</code>.</li></ol>
<form method='post' action='/export' enctype='multipart/form-data'><button>Create grading packets now</button></form></div>
<p class='muted'>Only new completed runs are exported each time; earlier responses keep their IDs.</p>
<h2>When graders send their files back</h2>
<div class='card'><p>Put the returned files in <code>{E(str(Path(pr) / 'grading' / 'returns'))}</code>, then press the button.
Disagreements go to the adjudicator in <code>{E(str(Path(pr) / 'grading' / 'adjudication' / 'adjudication_packet.csv'))}</code>;
the adjudicator saves a filled copy as <code>adjudication_return.csv</code> in the same folder. Press the button again afterwards.</p>
<form method='post' action='/merge' enctype='multipart/form-data'><button class='secondary'>Combine returned grades</button></form>{merged or ''}</div>""")




# ----------------------------------------------------------------------------- figure download + review

IMG_TYPES = {"jpg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp", "tif": "image/tiff"}


def _scope_ids(scope):
    pr = STATE["pilot"]
    if scope == "all":
        return [r["case_id"] for r in read_csv(path(pr, "registry")) if r["eligible"] == "Yes"]
    return pilot.pilot_cases(pr)


def v_figures(scope="pilot", msg=""):
    pr = STATE["pilot"]
    st = figures.STATE
    g = figures.gate(pr)
    test_default = g.get("test_cases") or ", ".join(pilot.pilot_cases(pr)[:3])
    ids = _scope_ids(scope)
    man = figures.read_manifest(pr)
    reg = {r["case_id"]: r for r in read_csv(path(pr, "registry"))}
    sm = figures.summary(pr, ids)
    rows = ""
    for c in ids:
        rr = [r for r in man if r["case_id"] == c]
        if not rr and scope == "all" and len(ids) > 60:
            continue
        dl = sum(r["download_status"] in ("downloaded", "manual_downloaded") for r in rr)
        mn = sum(r["download_status"] == "manual_needed" for r in rr)
        unrev = sum(r["download_status"] in ("downloaded", "manual_downloaded") and r.get("review_status") == "unreviewed" for r in rr)
        conf = sum(r.get("review_status") == "confirmed_case_figure" for r in rr)
        sk = sum(r["download_status"].startswith("skipped") for r in rr)
        state = "not started" if not rr else ("needs manual download" if mn else ("failed" if any(r["download_status"] == "failed" for r in rr) else "downloaded"))
        cls = {"not started": "pending", "needs manual download": "blocking", "failed": "blocking", "downloaded": "ready"}[state]
        rows += (f"<tr><td class='big'>{E(c)}</td><td><span class='pill {cls}'>{state}</span></td><td>{dl}</td><td>{sk}</td>"
                 f"<td>{conf} confirmed / {unrev} unreviewed</td><td><a class='btn' href='/figures/{c}'>Review</a></td></tr>")
    running = st["running"]
    refresh = "<meta http-equiv='refresh' content='4'>" if running else ""
    eta = ""
    if running and st["done"]:
        per = (time.time() - st["started"]) / st["done"]
        eta = f" · about {int(per * (st['total'] - st['done']) / 60) + 1} min left"
    prog = (f"<div class='card'><b>{'Downloading' if running else 'Last run'}:</b> {st['done']} of {st['total']} case(s)"
            f"{(' · now case ' + E(st['current'])) if st['current'] else ''}{eta} · {E(st['phase'])}"
            f"<progress max='{max(st['total'], 1)}' value='{st['done']}' style='width:100%'></progress>"
            + ("<form method='post' action='/figures/stop' enctype='multipart/form-data'><button class='secondary'>Stop after current case</button></form>" if running else "")
            + f"<pre class='muted'>{E(chr(10).join(st['log'][-12:]))}</pre></div>") if (running or st["log"]) else ""
    gated = not g.get("test_signed_by")
    manual = [r for r in man if r["case_id"] in ids and r["download_status"] in ("manual_needed", "failed")]
    mrows = "".join(f"<tr><td>{E(r['case_id'])}</td><td>{E(r.get('figure_number') or 'all')}</td><td>{E(r['status_reason'])}</td>"
                    f"<td><a href='{E(r['source_article_url'] or reg.get(r['case_id'], {}).get('source_url', ''))}' target='_blank' rel='noopener noreferrer'>open article</a> · "
                    f"<a href='/figures/{E(r['case_id'])}'>upload</a></td></tr>" for r in manual)
    note = f"<div class='warnbox'>{msg}</div>" if msg else ""
    disabled = "disabled title='Sign off the 3-case test first'" if gated else ""
    return page("Figures", f"""{refresh}<h1>Case figures</h1>{note}
<div class='card'><p>Downloads the published figures from each case's JAMA article link, slowly (one request every ~6-8 seconds),
into <code>{E(str(figures.originals_dir(pr)))}</code>. Originals are never edited. Figures that appear in the answer/discussion section are skipped.
Anything the site does not allow to be downloaded automatically (sign-in, purchase, bot check) is <b>not</b> worked around: it is listed below for download in your browser.</p>
<p class='muted'>Nothing is approved automatically. A person confirms each figure on its Review page before a prepared copy can be made.</p></div>
{prog}
<h2>Step 1 - test on three pilot cases</h2>
<form method='post' action='/figures/start' enctype='multipart/form-data' class='card'>
<input type='hidden' name='scope' value='test'><label>Test case IDs<input name='cases' value='{E(test_default)}'></label>
<p><button {'disabled' if running else ''}>Download test cases</button></p>
<p class='muted'>Then open each case's Review page, check every figure, and read the <a href='/figures/report'>inspection report</a>
(what was found on each page and which image was chosen).</p></form>
<form method='post' action='/figures/gate' enctype='multipart/form-data' class='card'>
<b>Step 2 - sign off the test</b> {('<span class="pill ready">signed off by ' + E(g['test_signed_by']) + ' ' + E(g.get('test_signed_date', '')) + '</span>') if g.get('test_signed_by') else ''}
<p class='muted'>Only when the test figures are correct (right case, all panels, full size, no answer-section figures, no logos or thumbnails).</p>
<div class='grid'><label>Your initials<input name='who' required></label><label>Notes<input name='notes'></label></div><p><button class='secondary'>I checked the test results</button></p></form>
<h2>Step 3 - expand</h2>
<div class='card'><form method='post' action='/figures/start' enctype='multipart/form-data' style='display:inline'>
<input type='hidden' name='scope' value='pilot'><button {disabled}>Download all 10 pilot cases</button></form>
<form method='post' action='/figures/start' enctype='multipart/form-data' style='display:inline'>
<input type='hidden' name='scope' value='all'><button {disabled}>Download all included cases (~1 h per 150 cases)</button></form>
<form method='post' action='/figures/start' enctype='multipart/form-data' style='display:inline'>
<input type='hidden' name='scope' value='{E(scope)}'><input type='hidden' name='retry' value='1'><button class='secondary' {disabled}>Retry failed / manual cases</button></form>
<p class='muted'>Interrupted runs resume where they stopped: finished cases and files are skipped, never duplicated.</p></div>
<h2>Status - {'all included cases' if scope == 'all' else 'pilot cases'} <span class='muted'>(<a href='/figures?scope={'pilot' if scope == 'all' else 'all'}'>show {'pilot' if scope == 'all' else 'all included'}</a>)</span></h2>
<p class='muted'>{sm['downloaded']} file(s) downloaded · {sm['skipped_answer']} answer-section figure(s) skipped · {sm['unreviewed']} unreviewed ·
{len(sm['manual_needed_cases'])} case(s) need manual download. Manifest: <code>{E(str(figures.manifest_path(pr)))}</code></p>
<div class='card'><table><tr><th>Case</th><th>Status</th><th>Files</th><th>Skipped</th><th>Review</th><th></th></tr>{rows or '<tr><td colspan=6>No cases attempted yet.</td></tr>'}</table></div>
<h2>Needs manual download in your browser</h2>
<div class='card'><table><tr><th>Case</th><th>Figure</th><th>Why</th><th></th></tr>{mrows or '<tr><td colspan=4>None.</td></tr>'}</table>
<p class='muted'>How: see "Manual download" in docs/PILOT_GUIDE.md. Use your normal browser and your own access; then upload the file on the case's Review page.</p></div>""")


def v_figure_case(cid, msg=""):
    pr = STATE["pilot"]
    reg = {r["case_id"]: r for r in read_csv(path(pr, "registry"))}
    r0 = reg.get(cid)
    if not r0:
        return page("Not found", "<p>Unknown case.</p>")
    rows = [r for r in figures.read_manifest(pr) if r["case_id"] == cid]
    cards = ""
    for r in rows:
        fn = r.get("local_filename", "")
        if fn and r["download_status"] in ("downloaded", "manual_downloaded"):
            sel = "<option value=''>- choose -</option>" + "".join(
                f"<option value='{k}' {'selected' if r.get('review_status') == k else ''}>{E(v)}</option>" for k, v in figures.REVIEW_CHOICES.items())
            prepared = (images_dir(pr) / fn).exists()
            cards += f"""<div class='card'><h2>{E(fn)} <span class='pill {'ready' if r.get('review_status') == 'confirmed_case_figure' else 'pending'}'>{E(r.get('review_status', 'unreviewed'))}</span></h2>
<a href='/original/{E(cid)}/{E(fn)}' target='_blank'><img src='/original/{E(cid)}/{E(fn)}' alt='{E(fn)}' style='max-width:100%;max-height:640px;border:1px solid var(--line);background:#fff'></a>
<p class='muted'>Click the image to open it full size and zoom in on corners and panel labels.</p>
<table><tr><td>Figure</td><td>{E(r['figure_number'])}{E(r['part'])} · section: {E(r.get('section', ''))} · cited in case text: {E(r.get('cited_in_case_text', ''))}</td></tr>
<tr><td>Size</td><td>{E(r.get('width', ''))} × {E(r.get('height', ''))} px · {E(r.get('bytes', ''))} bytes</td></tr>
<tr><td>Published caption (start)</td><td>{E(r.get('caption_start', ''))} <span class='muted'>(word match with case text: {E(r.get('caption_match_score', ''))})</span></td></tr>
<tr><td>Source</td><td><a href='{E(r['source_article_url'])}' target='_blank' rel='noopener noreferrer'>article</a> · <span class='muted'>{E(r.get('image_url', '')[:120])}</span></td></tr>
<tr><td>Notes</td><td>{E(r.get('status_reason', ''))}</td></tr></table>
<form method='post' action='/figures/{E(cid)}/review' enctype='multipart/form-data'><input type='hidden' name='file' value='{E(fn)}'>
<div class='grid'><label>Does this figure belong to case {E(cid)}'s presentation?<select name='status'>{sel}</select></label>
<label>Your initials<input name='who' value='{E(r.get('reviewed_by', ''))}' required></label></div>
<label><input type='checkbox' name='revealing' value='1' style='display:inline;width:auto' {'checked' if r.get('contains_revealing_text') == 'yes' else ''}>
The image itself contains text or labels that could reveal the answer (must be cropped in the prepared copy)</label>
<label>Notes<input name='notes' value='{E(r.get('review_notes', ''))}'></label><p><button>Save review</button></p></form>
<form method='post' action='/figures/{E(cid)}/prepare' enctype='multipart/form-data'><input type='hidden' name='file' value='{E(fn)}'>
<button class='secondary' {'disabled' if r.get('review_status') != 'confirmed_case_figure' or prepared else ''}>{'Prepared copy exists' if prepared else 'Make prepared copy for cropping'}</button></form></div>"""
        else:
            cards += (f"<div class='card'><b>Figure {E(r.get('figure_number') or '?')}{E(r.get('part', ''))}</b> - "
                      f"<span class='pill {'blocking' if r['download_status'] in ('manual_needed', 'failed') else 'pending'}'>{E(r['download_status'])}</span>"
                      f"<p>{E(r.get('status_reason', ''))}</p></div>")
    note = f"<div class='warnbox'>{msg}</div>" if msg else ""
    return page(f"Figures {cid}", f"""<p><a href='/figures'>← all figures</a></p><h1>Case {E(cid)}: figures</h1>{note}
<p><a class='btn' href='{E(r0['source_url'])}' target='_blank' rel='noopener noreferrer'>Open the article in your browser</a></p>
<details class='card'><summary>Case text, for matching figures to this case (no title)</summary><pre>{E(r0['text_only_input'])}</pre></details>
{cards or "<div class='card'>Not downloaded yet. Use the Figures page, or upload below.</div>"}
<h2>Add a figure downloaded in your browser</h2>
<form method='post' action='/figures/{E(cid)}/upload' enctype='multipart/form-data' class='card'>
<div class='grid'><label>Image file<input type='file' name='file' accept='image/*' required></label>
<label>Figure number<input name='figure_number' required></label>
<label>Part letter if the figure has several files (a, b, ...)<input name='part'></label>
<label>Image address (optional; right-click the image → Copy image address)<input name='image_url'></label>
<label>Your initials<input name='who' required></label></div>
<p class='muted'>The file is stored unchanged as IMG-{int(cid):03d}-&lt;figure&gt;.ext and still needs review.</p><p><button>Upload</button></p></form>""")


def v_fig_report():
    pr = STATE["pilot"]
    p = figures.originals_dir(pr) / "inspection_report.md"
    body = E(p.read_text(encoding="utf-8")) if p.exists() else "No report yet: run the 3-case test first."
    return page("Inspection report", f"<p><a href='/figures'>← figures</a></p><div class='card'><pre>{body}</pre></div>")


def start_figures(f):
    pr = STATE["pilot"]
    scope = f.get("scope", "test")
    g = figures.gate(pr)
    if scope == "test":
        ids = [x for x in re.findall(r"\d+", f.get("cases", ""))]
        reg = {r["case_id"]: r for r in read_csv(path(pr, "registry"))}
        bad = [x for x in ids if reg.get(x, {}).get("eligible") != "Yes"]
        if not ids or bad:
            return "Not started: enter included case IDs" + (f" (not included: {', '.join(bad)})" if bad else "")
        figures.save_gate(pr, test_cases=", ".join(ids))

        def job():
            figures.run_batch(pr, ids)
            figures.inspection_report(pr, ids)
        if figures.STATE["running"]:
            return "A download is already running."
        figures.STATE["log"] = []
        threading.Thread(target=job, daemon=True).start()
        return f"Started test download for cases {', '.join(ids)}."
    if not g.get("test_signed_by"):
        return "Not started: sign off the 3-case test first."
    ids = _scope_ids(scope)
    ok = figures.start_background(pr, ids, retry_manual=bool(f.get("retry")))
    return f"Started: {len(ids)} case(s) in scope; finished cases are skipped." if ok else "A download is already running."


# ----------------------------------------------------------------------------- server

def parse_body(handler) -> tuple[dict, dict, dict]:
    n = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(n) if n else b""
    ctype = handler.headers.get("Content-Type", "")
    fields, files, multi = {}, {}, {}
    if "multipart/form-data" in ctype:
        msg = email.parser.BytesParser(policy=email.policy.default).parsebytes(
            b"Content-Type: " + ctype.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw)
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            fn = part.get_filename()
            data = part.get_payload(decode=True) or b""
            if fn is not None:
                files[name] = (fn, data)
            else:
                val = data.decode("utf-8", errors="replace")
                multi.setdefault(name, []).append(val)
                fields[name] = val
    return fields, files, multi


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body: str, code: int = 200):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = unquote(self.path.split("?")[0])
        try:
            if p == "/":
                return self.send(v_home())
            if m := re.fullmatch(r"/case/(\d+)", p):
                return self.send(v_case(m.group(1)))
            if m := re.fullmatch(r"/image-text/(\d+)", p):
                return self.send(v_image_text(m.group(1)))
            if m := re.fullmatch(r"/images/(\d+)", p):
                return self.send(v_images(m.group(1)))
            if p == "/keys":
                return self.send(v_keys())
            if p == "/figures":
                q = self.path.split("?", 1)[1] if "?" in self.path else ""
                return self.send(v_figures("all" if "scope=all" in q else "pilot"))
            if p == "/figures/report":
                return self.send(v_fig_report())
            if m := re.fullmatch(r"/figures/(\d+)", p):
                return self.send(v_figure_case(m.group(1)))
            if m := re.fullmatch(r"/original/(\d+)/(IMG-\d{3}-\d+[a-j]?\.(jpg|png|gif|webp|tif))", p):
                fp = figures.originals_dir(STATE["pilot"]) / f"{int(m.group(1)):03d}" / m.group(2)
                if not fp.is_file():
                    return self.send(page("Not found", "<p>No such file.</p>"), 404)
                b = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", IMG_TYPES[m.group(3)])
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if p == "/checks":
                return self.send(v_checks())
            if p == "/export":
                return self.send(v_export())
            return self.send(page("Not found", "<p>Not found.</p>"), 404)
        except Exception as e:  # show errors in the page rather than a blank tab
            return self.send(page("Error", f"<div class='badbox'><b>Something went wrong:</b> {E(repr(e))}</div>"), 500)

    def do_POST(self):
        p = unquote(self.path.split("?")[0])
        try:
            f, files, multi = parse_body(self)
            if p == "/record":
                cid, msg = save_record(f, files)
                return self.send(v_case(cid, msg) if cid else page("Error", E(msg)))
            if m := re.fullmatch(r"/image-text/(\d+)", p):
                return self.send(v_image_text(m.group(1), save_image_text(m.group(1), f)))
            if m := re.fullmatch(r"/images/(\d+)", p):
                return self.send(v_images(m.group(1), save_images(m.group(1), f, multi)))
            if p == "/keys":
                return self.send(v_keys(save_key(f)))
            if p == "/figures/start":
                return self.send(v_figures(f.get("scope") if f.get("scope") in ("pilot", "all") else "pilot", start_figures(f)))
            if p == "/figures/stop":
                figures.STATE["stop"] = True
                return self.send(v_figures(msg="Stopping after the current case."))
            if p == "/figures/gate":
                if not f.get("who", "").strip():
                    return self.send(v_figures(msg="Initials required."))
                figures.save_gate(STATE["pilot"], test_signed_by=f["who"].strip(), test_signed_date=dt.date.today().isoformat(),
                                  test_notes=f.get("notes", ""))
                return self.send(v_figures(msg="Test signed off. You can now expand."))
            if m := re.fullmatch(r"/figures/(\d+)/review", p):
                return self.send(v_figure_case(m.group(1), figures.save_review(STATE["pilot"], m.group(1), f.get("file", ""),
                                 f.get("status", ""), bool(f.get("revealing")), f.get("who", ""), f.get("notes", ""))))
            if m := re.fullmatch(r"/figures/(\d+)/prepare", p):
                return self.send(v_figure_case(m.group(1), figures.make_prepared_copy(STATE["pilot"], m.group(1), f.get("file", ""))))
            if m := re.fullmatch(r"/figures/(\d+)/upload", p):
                fn, data = files.get("file", ("", b""))
                return self.send(v_figure_case(m.group(1), figures.add_manual_file(STATE["pilot"], m.group(1), f.get("figure_number", ""),
                                 f.get("part", ""), data, fn, f.get("image_url", ""), f.get("who", ""))))
            if p == "/synonyms":
                return self.send(v_keys(save_synonyms(f)))
            if p == "/signoff":
                pilot.save_signoff(STATE["pilot"], f)
                return self.send(v_home())
            if p == "/export":
                return self.send(v_export(grading.make_packets(STATE["pilot"])))
            if p == "/merge":
                m = grading.merge(STATE["pilot"])
                summ = "".join(f"<li>{E(o)}: " + ", ".join(f"{E(k)} {v}" for k, v in d.items()) + "</li>" for o, d in m["by_outcome"].items())
                return self.send(v_export(merged=f"<div class='warnbox'><b>{m['responses']} responses combined; "
                                                 f"{m['awaiting_adjudication']} need adjudication.</b><ul>{summ}</ul></div>"))
            return self.send(page("Not found", "<p>Not found.</p>"), 404)
        except Exception as e:
            return self.send(page("Error", f"<div class='badbox'><b>Something went wrong:</b> {E(repr(e))}</div>"), 500)


def serve(main_root, port: int = 8765, open_browser: bool = True):
    main_root = Path(main_root)
    for line in bootstrap(main_root):
        print(line)
    STATE["main"], STATE["pilot"] = main_root, main_root / "pilot"
    refresh_prompts()
    url = f"http://127.0.0.1:{port}/"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        print(f"Pilot Desk seems to be running already. Opening {url} - use the window that is already open.")
        if open_browser:
            webbrowser.open(url)
        return
    print(f"Pilot Desk is running at {url}  (only on this computer). Close this window to stop it.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
