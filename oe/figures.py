"""Download published case figures from the article links in the workbook.

What it does
* Fetches each article page (the `source_url` from the workbook), finds the
  figure blocks in the article body, and downloads the largest image offered
  for each case-presentation figure (all panels belonging to that figure).
* Saves the files UNCHANGED in data/images/original/<case>/IMG-<case>-<fig>.<ext>
  (an extra part letter only if a figure is split into several image files).
* Records every outcome in data/images/original/figure_manifest.csv.

What it never does
* It never signs in, sends browser cookies, solves bot checks, or retries around
  a refusal. Pages that ask for sign-in/purchase, robots.txt disallows, bot
  checks, HTTP 401/403 and non-image responses are flagged `manual_needed` with
  the article link so a person can download the figure in their own browser.
* It never approves anything. Every downloaded figure starts as `unreviewed`; a
  person confirms that it belongs to the case presentation before a prepared
  copy can be made.

Politeness: one request at a time, at least `min_interval_s` (default 6 s, plus
random 0-2 s) between requests, honest User-Agent, and the whole batch pauses on
HTTP 429/503 or any automated-access check.

Page structure: the parser is deliberately generic (figure/caption containers,
"View Large"/"Original"/"Download" image links, srcset, data-src). The first
run on three pilot cases writes an inspection report listing every image found
on each page and which one was chosen, so the rule can be checked by a person
before expanding.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html as htmlmod
import json
import random
import re
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path

from .common import norm_key, path, read_csv, registry_root, sha256_file, write_csv

MANIFEST_FIELDS = [
    "case_id", "figure_number", "part", "section", "cited_in_case_text", "source_article_url", "image_url",
    "candidate_urls", "local_filename", "width", "height", "bytes", "sha256", "caption_start",
    "caption_match_score", "download_status", "http_status", "status_reason", "downloaded_at",
    "review_status", "contains_revealing_text", "reviewed_by", "reviewed_date", "review_notes",
]
TERMINAL = {"downloaded", "manual_downloaded", "skipped_answer_section", "skipped_supplement"}
REVIEW_CHOICES = {
    "confirmed_case_figure": "Confirmed: belongs to this case's presentation",
    "answer_section_figure": "Belongs to the answer/discussion: exclude",
    "wrong_case": "Wrong case: exclude",
    "not_a_figure": "Not a case figure (logo, thumbnail, ad): exclude",
    "unsure": "Unsure: needs a second look",
}
USER_AGENT = "OE-JAMAOphth-study-figure-fetch/1.0 (academic research; one request per ~6 s)"
ANSWER_HEADINGS = re.compile(r"^\s*(diagnosis|discussion|what to do next|answer|references?|article information|"
                             r"comment|conclusion|back to top|related articles?)\b", re.I)
PAYWALL = re.compile(r"sign in to (access|view|read)|purchase (access|this article)|get access|subscribe (now|to)|"
                     r"institutional (login|sign in|access)|access through your institution|rent this article", re.I)
CHALLENGE = re.compile(r"just a moment\.\.\.|checking your browser|captcha|are you a robot|unusual traffic|"
                       r"verify you are human|request unsuccessful|incapsula|access denied", re.I)
BAD_URL = re.compile(r"(logo|icon|sprite|thumb(nail)?s?\b|_thumb|avatar|badge|banner|spinner|placeholder|"
                     r"blank\.gif|/ads?/|pixel|tracking|cover(image)?\.|journal-cover|data:)", re.I)
IMG_EXT = re.compile(r"\.(jpe?g|png|gif|tiff?|webp)(\?|#|$)", re.I)
LARGE_LINK = re.compile(r"view large|original|full[- ]?size|enlarge|high[- ]?res|download (image|figure)|open in new tab", re.I)
FIG_CLASS = re.compile(r"(^|[\s_-])(fig|figure|graphic)(s|-?section|-?wrap(per)?|-?container|-?content|-?box|-?item|-?group)?($|[\s_-])", re.I)
CAPTION_CLASS = re.compile(r"caption|legend|fig-?label|figure-?title|label", re.I)
FIG_LABEL = re.compile(r"\b(e?Figure|Fig\.?)\s*(\d+)?", re.I)

STATE = {"running": False, "stop": False, "log": [], "current": "", "done": 0, "total": 0, "phase": "", "started": None}


# ----------------------------------------------------------------------------- tiny DOM

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.children, self.parent, self.text = tag, attrs or {}, [], parent, ""

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.iter()

    def all_text(self) -> str:
        out = []
        for c in self.children:
            out.append(c.all_text() if isinstance(c, Node) else c)
        return " ".join(x for x in out if x)

    @property
    def cls(self) -> str:
        return self.attrs.get("class", "") or ""


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.cur = self.root
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
            return
        n = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            return
        self.cur.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
            return
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.cur.children.append(re.sub(r"\s+", " ", data))


def parse_html(text: str) -> Node:
    tb = TreeBuilder()
    tb.feed(text)
    return tb.root


# ----------------------------------------------------------------------------- page analysis

def _is_fig_container(n: Node) -> bool:
    return n.tag == "figure" or bool(FIG_CLASS.search(n.cls)) or n.attrs.get("data-type", "").lower() == "figure"


def _img_candidates(container: Node, base: str) -> list[list[dict]]:
    """Ranked candidate URLs, grouped into one set per separate image (= panel).
    Variants of the same image (src, data-src, srcset, a 'View Large' link) share a set."""
    def mk(url, kind, rank, width=0):
        if not url or url.strip().startswith("data:"):
            return None
        u = urllib.parse.urljoin(base, htmlmod.unescape(url.strip()))
        if BAD_URL.search(u.split("?")[0]):
            return None
        return {"url": u, "kind": kind, "rank": rank, "width_hint": width}

    img_sets, links = [], []
    for n in container.iter():
        if n.tag in ("img", "source"):
            cs = []
            try:
                w = int(re.sub(r"\D", "", n.attrs.get("width", "") or "0") or 0)
            except ValueError:
                w = 0
            if 0 < w < 120 and not any(n.attrs.get(k) for k in ("data-original", "data-full", "data-large")):
                continue  # tiny thumbnail
            for attr, rank in (("data-original", 2), ("data-full", 2), ("data-large", 2), ("data-zoom-src", 2),
                               ("data-src", 4), ("data-lazy-src", 4), ("src", 5)):
                c = mk(n.attrs.get(attr, ""), f"img@{attr}", rank, w)
                if c:
                    cs.append(c)
            for attr in ("srcset", "data-srcset"):
                for part in (n.attrs.get(attr) or "").split(","):
                    bits = part.strip().split()
                    if bits:
                        ww = int(re.sub(r"\D", "", bits[1]) or 0) if len(bits) > 1 and bits[1].endswith("w") else 0
                        c = mk(bits[0], f"img@{attr}", 3, ww)
                        if c:
                            cs.append(c)
            if cs:
                img_sets.append(cs)
        elif n.tag == "a":
            href = n.attrs.get("href", "")
            label = " ".join([n.all_text(), n.attrs.get("title", ""), n.cls, n.attrs.get("aria-label", "")])
            c = None
            if IMG_EXT.search(href):
                c = mk(href, "link@image-file", 1 if LARGE_LINK.search(label) else 2)
            elif LARGE_LINK.search(label) and href and not href.startswith("#"):
                c = mk(href, "link@view-large", 1)
            if c:
                links.append(c)
    if links:
        if len(links) == len(img_sets):
            for cs, l in zip(img_sets, links):
                cs.append(l)
        elif len(img_sets) <= 1:
            img_sets = [(img_sets[0] if img_sets else []) + links]
        else:
            # one "View Large" for several images: usually the whole composite figure
            img_sets = [links + [c for cs in img_sets for c in cs]]
            img_sets[0][0]["note"] = "several images but one full-size link: check all panels are in the downloaded file"
    out = []
    for cs in img_sets:
        seen, ranked = set(), []
        for c in sorted(cs, key=lambda c: (c["rank"], -c["width_hint"])):
            if c["url"] not in seen:
                seen.add(c["url"])
                ranked.append(c)
        out.append(ranked)
    return out


def analyse_page(text: str, base_url: str) -> dict:
    """Return figures (with section, label, caption, ranked candidate URLs) and page flags."""
    root = parse_html(text)
    body_text = root.all_text()
    heading, order = "", []
    def has_img(n):
        return any(x.tag in ("img", "source") for x in n.iter())

    def labels(n):
        return {m.group(0).lower().replace(" ", "") for m in FIG_LABEL.finditer(n.all_text()) if m.group(2)}

    tops = {}
    for n in root.iter():
        if _is_fig_container(n) and has_img(n):
            top = n
            while top.parent is not None and _is_fig_container(top.parent) and len(labels(top.parent)) <= 1:
                top = top.parent
            tops[id(top)] = top
    inner = list(tops.values())
    inner_ids = {id(n) for n in inner}
    figs = []
    for n in root.iter():  # document order -> track the section heading
        if n.tag in ("h1", "h2", "h3", "h4") or "section-title" in n.cls or "title-section" in n.cls:
            t = n.all_text().strip()
            if t:
                heading = t
        if id(n) in inner_ids:
            # label/caption: inside the container or up to two ancestors
            cap_all = [x for x in n.iter() if x.tag == "figcaption" or CAPTION_CLASS.search(x.cls)]
            ids_cap = {id(x) for x in cap_all}

            def _under_other(x):
                q = x.parent
                while q is not None and q is not n:
                    if id(q) in ids_cap:
                        return True
                    q = q.parent
                return False
            cap_nodes = [x for x in cap_all if not _under_other(x)]
            scope = n
            if not FIG_LABEL.search(n.all_text()):
                for _ in range(2):
                    if scope.parent is not None:
                        scope = scope.parent
                        if FIG_LABEL.search(scope.all_text()):
                            break
            txt = " ".join(x.all_text() for x in cap_nodes) or scope.all_text()
            m = FIG_LABEL.search(scope.all_text())
            label = m.group(0) if m else ""
            num = int(m.group(2)) if m and m.group(2) else None
            supplement = bool(m and m.group(1).lower().startswith("e"))
            in_answer = bool(ANSWER_HEADINGS.match(heading or ""))
            figs.append({"figure_number": num, "label": label, "caption": re.sub(r"\s+", " ", txt).strip()[:1200],
                         "section": "supplement" if supplement else ("answer" if in_answer else "case"),
                         "heading": heading[:80], "image_sets": _img_candidates(n, base_url)})
            figs[-1]["candidates"] = [c for cs in figs[-1]["image_sets"] for c in cs]
            order.append(n)
    # number unnumbered figures sequentially within the case section, merge duplicates of the same number
    k = 0
    for f in figs:
        if f["figure_number"] is None and f["section"] == "case":
            k += 1
            f["figure_number"] = k
            f["label"] = f["label"] or "Figure (unnumbered)"
    all_imgs = []
    for n in root.iter():
        if n.tag == "img":
            all_imgs.append(urllib.parse.urljoin(base_url, n.attrs.get("data-src") or n.attrs.get("src") or ""))
    flags = []
    if CHALLENGE.search(body_text[:5000]) and not figs:
        flags.append("challenge")
    if PAYWALL.search(body_text):
        flags.append("paywall_text")
    return {"figures": figs, "flags": flags, "n_img_tags": len(all_imgs), "all_img_urls": all_imgs[:200],
            "title": next((x.all_text() for x in root.iter() if x.tag == "title"), "")[:200]}


# ----------------------------------------------------------------------------- image helpers

def image_info(b: bytes) -> tuple[str, int, int]:
    """(format, width, height) from file bytes; ('', 0, 0) if not a recognised image."""
    try:
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", b[16:24])
            return "png", w, h
        if b[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", b[6:10])
            return "gif", w, h
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            return "webp", 0, 0
        if b[:4] in (b"II*\x00", b"MM\x00*"):
            return "tif", 0, 0
        if b[:2] == b"\xff\xd8":
            i = 2
            while i < len(b) - 9:
                if b[i] != 0xFF:
                    i += 1
                    continue
                marker = b[i + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                seg = struct.unpack(">H", b[i + 2:i + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", b[i + 5:i + 9])
                    return "jpg", w, h
                i += 2 + seg
            return "jpg", 0, 0
    except struct.error:
        pass
    return "", 0, 0


def caption_match(caption: str, case_text: str) -> float:
    """Share of the caption's words found in the case text (legends are part of the case text)."""
    cw = [w for w in norm_key(caption).split() if len(w) > 3]
    if not cw:
        return 0.0
    tw = set(norm_key(case_text).split())
    return round(sum(w in tw for w in cw) / len(cw), 2)


def cited_figures(case_text: str) -> set[int]:
    nums = set()
    for m in re.finditer(r"\bFigures?\s*(\d+)(?:\s*(?:and|-|–|,)\s*(\d+))?", case_text or ""):
        nums.add(int(m.group(1)))
        if m.group(2):
            nums.update(range(int(m.group(1)), int(m.group(2)) + 1))
    if not nums and re.search(r"\(Figure\b|\bFigure,", case_text or ""):
        nums.add(1)
    return nums


# ----------------------------------------------------------------------------- downloader

def originals_dir(root) -> Path:
    return registry_root(root) / "images" / "original"


def manifest_path(root) -> Path:
    return originals_dir(root) / "figure_manifest.csv"


def read_manifest(root) -> list[dict]:
    return read_csv(manifest_path(root))


def write_manifest(root, rows) -> None:
    rows = sorted(rows, key=lambda r: (int(r["case_id"]), int(r.get("figure_number") or 0) if str(r.get("figure_number") or "0").isdigit() else 0,
                                       r.get("part", "")))
    write_csv(manifest_path(root), rows, MANIFEST_FIELDS)


def gate_path(root) -> Path:
    return originals_dir(root) / "download_gate.json"


def gate(root) -> dict:
    p = gate_path(root)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_gate(root, **kv) -> dict:
    g = gate(root)
    g.update(kv)
    gate_path(root).parent.mkdir(parents=True, exist_ok=True)
    gate_path(root).write_text(json.dumps(g, indent=2), encoding="utf-8")
    return g


class Fetcher:
    def __init__(self, min_interval=6.0, jitter=2.0, timeout=40, sleep=time.sleep):
        self.min_interval, self.jitter, self.timeout, self.sleep = min_interval, jitter, timeout, sleep
        self.last = 0.0
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.requests = 0

    def _wait(self):
        gap = self.min_interval + random.uniform(0, self.jitter) - (time.time() - self.last)
        if gap > 0:
            self.sleep(gap)
        self.last = time.time()

    def allowed(self, url: str) -> bool:
        p = urllib.parse.urlsplit(url)
        key = f"{p.scheme}://{p.netloc}"
        if key not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._wait()
                self.requests += 1
                req = urllib.request.Request(key + "/robots.txt", headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    rp.parse(r.read().decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) or e.code >= 500:
                    rp.disallow_all = True   # conservative: treat as "not allowed"
                else:
                    rp.allow_all = True      # 404 etc.: no robots.txt
            except Exception:
                rp = None                    # unreachable: the page request itself will fail and be flagged
            self.robots[key] = rp
        rp = self.robots[key]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    def get(self, url: str, referer: str = "") -> tuple[int, str, bytes, str]:
        """(status, content_type, body, final_url). Never sends cookies or credentials."""
        self._wait()
        self.requests += 1
        h = {"User-Agent": USER_AGENT, "Accept": "text/html,image/*;q=0.9,*/*;q=0.5"}
        if referer:
            h["Referer"] = referer
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read(60_000_000), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", "") if e.headers else "", b"", url


class Paused(Exception):
    pass


def _log(msg):
    STATE["log"].append(f"{dt.datetime.now().strftime('%H:%M:%S')}  {msg}")
    STATE["log"] = STATE["log"][-300:]


def download_case(root, case: dict, fetcher: Fetcher, force_refetch_page: bool = False) -> list[dict]:
    """Download one case's figures; returns its manifest rows. Raises Paused to stop the batch."""
    cid = str(case["case_id"])
    url = (case.get("source_url") or "").strip()
    folder = originals_dir(root) / f"{int(cid):03d}"
    folder.mkdir(parents=True, exist_ok=True)
    old = [r for r in read_manifest(root) if r["case_id"] == cid]
    oldmap = {(r["figure_number"], r["part"]): r for r in old}
    now = dt.datetime.now().isoformat(timespec="seconds")
    base = {"case_id": cid, "source_article_url": url, "review_status": "unreviewed"}

    def manual(reason, http=""):
        keep = [r for r in old if r["download_status"] in ("downloaded", "manual_downloaded")]
        return keep or [dict(base, figure_number="", part="", download_status="manual_needed",
                             http_status=str(http), status_reason=reason, downloaded_at=now)]

    if not re.match(r"https?://", url):
        return manual("workbook has no usable article link; find the article on jamanetwork.com and download in a browser")
    if not fetcher.allowed(url):
        return manual("site's robots.txt does not allow automated access to this page; download in a browser")
    page_file = folder / "_article_page.html"
    if page_file.exists() and not force_refetch_page:
        text = page_file.read_text(encoding="utf-8", errors="replace")
    else:
        st, ct, body, final = fetcher.get(url)
        if st in (429, 503):
            raise Paused(f"the site asked us to slow down (HTTP {st}); try again later")
        if st in (401, 402, 403):
            return manual(f"article page refused automated access (HTTP {st}); likely needs sign-in or blocks scripts", st)
        if st != 200 or "html" not in ct.lower():
            return manual(f"article page not available automatically (HTTP {st}, {ct or 'no type'})", st)
        text = body.decode("utf-8", errors="replace")
        page_file.write_text(text, encoding="utf-8")
    info = analyse_page(text, url)
    if "challenge" in info["flags"]:
        page_file.unlink(missing_ok=True)
        raise Paused("the site showed an automated-access check (bot challenge). Not bypassing it: "
                     "remaining cases must be downloaded in a browser or retried later")
    case_figs = [f for f in info["figures"] if f["section"] == "case"]
    if not case_figs:
        why = ("page asks for sign-in or purchase and shows no case figures" if "paywall_text" in info["flags"]
               else "no figures found on the page (layout not recognised, or figures load only in a browser)")
        return manual(why)
    cited = cited_figures(case.get("text_only_input", ""))
    rows = []
    for f in info["figures"]:
        num = f["figure_number"] or 0
        sets = f["image_sets"] or [[]]
        cap = f["caption"]
        common = dict(base, figure_number=str(num), section=f["section"],
                      cited_in_case_text="yes" if num in cited else ("no" if cited else "unknown"),
                      caption_start=cap[:160], caption_match_score=caption_match(cap, case.get("text_only_input", "")))
        if f["section"] != "case":
            rows.append(dict(common, part="e" if f["section"] == "supplement" else "",
                             candidate_urls=" | ".join(c["url"] for c in f["candidates"][:6]),
                             download_status="skipped_answer_section" if f["section"] == "answer" else "skipped_supplement",
                             status_reason=f"appears under '{f['heading']}'" if f["section"] == "answer" else "supplementary eFigure",
                             downloaded_at=now))
            continue
        for si, cands in enumerate(sets):
            part = "" if len(sets) == 1 else "abcdefghij"[si]
            row = dict(common, part=part, candidate_urls=" | ".join(c["url"] for c in cands[:6]))
            prev = oldmap.get((str(num), part))
            if prev and prev.get("download_status") in ("downloaded", "manual_downloaded") and prev.get("local_filename") and \
                    (folder / prev["local_filename"]).exists() and sha256_file(folder / prev["local_filename"]) == prev["sha256"]:
                rows.append(prev)  # resume: keep, never re-download or duplicate
                continue
            best, tried = None, []
            for c in cands[:4]:
                if STATE["stop"]:
                    raise Paused("stopped by user")
                if not fetcher.allowed(c["url"]):
                    tried.append(f"{c['url']} (robots.txt disallows)")
                    continue
                st, ct, body, final = fetcher.get(c["url"], referer=url)
                if st in (429, 503):
                    raise Paused(f"the image server asked us to slow down (HTTP {st}); try again later")
                fmt, w, h = image_info(body) if st == 200 else ("", 0, 0)
                tried.append(f"{c['url']} -> HTTP {st} {ct.split(';')[0]} {w}x{h}")
                if st == 200 and fmt and ct.lower().startswith("image"):
                    if best is None or (w * h) > (best[2] * best[3]):
                        best = (c["url"], fmt, w, h, body)
                    if max(w, h) >= 1000 or (w == 0 and h == 0):
                        break  # large enough or size unknown; do not fetch more variants
                elif st in (401, 402, 403):
                    tried.append("access refused")
                    break
            if best is None:
                rows.append(dict(row, download_status="manual_needed",
                                 status_reason=("image could not be downloaded automatically: " + "; ".join(tried))[:600]
                                 if tried else "no downloadable image link found in this figure block",
                                 downloaded_at=now))
                continue
            img_url, fmt, w, h, body = best
            fn = f"IMG-{int(cid):03d}-{num}{part}.{fmt}"
            dest = folder / fn
            if dest.exists() and sha256_file(dest) != hashlib.sha256(body).hexdigest():
                rows.append(dict(row, download_status="manual_needed",
                                 status_reason=f"{fn} already exists with different content; kept the existing file"))
                continue
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(body)
            tmp.replace(dest)
            notes = [c["note"] for c in cands if c.get("note")]
            if max(w, h) and max(w, h) < 600:
                notes.append("small image (<600 px): check whether a larger version is offered")
            if row["cited_in_case_text"] == "no":
                notes.append("figure number not cited in the case text")
            rows.append(dict(row, image_url=img_url, local_filename=fn, width=w, height=h, bytes=len(body),
                             sha256=sha256_file(dest), download_status="downloaded", http_status="200",
                             status_reason="; ".join(notes), downloaded_at=now))
    # missing cited figures
    got = {int(r["figure_number"]) for r in rows if r["figure_number"] and r.get("section") == "case"}
    for n in sorted(cited - got):
        rows.append(dict(base, figure_number=str(n), part="", section="case", cited_in_case_text="yes",
                         download_status="manual_needed", status_reason="figure cited in case text but not found on the page",
                         downloaded_at=now))
    return rows


def inspection_report(root, case_ids) -> str:
    """Human-readable summary of what was found on each article page (for checking the rule)."""
    reg = {r["case_id"]: r for r in read_csv(path(root, "registry"))}
    out = ["# Figure-page inspection report", "",
           "For each test case: every figure block found on the cached article page, its section, and the image URLs considered "
           "(first = chosen if it downloaded). Check that (1) only case-presentation figures were taken, (2) the chosen URL is the "
           "largest version, (3) no thumbnails, logos or related-article images were taken.", ""]
    for cid in case_ids:
        cid = str(cid)
        pf = originals_dir(root) / f"{int(cid):03d}" / "_article_page.html"
        out.append(f"## Case {cid}  ({reg.get(cid, {}).get('source_url', '')})")
        if not pf.exists():
            out += ["Page not downloaded (see manifest for the reason).", ""]
            continue
        a = analyse_page(pf.read_text(encoding="utf-8", errors="replace"), reg[cid]["source_url"])
        out.append(f"- page flags: {', '.join(a['flags']) or 'none'}; <img> tags on page: {a['n_img_tags']}; figure blocks: {len(a['figures'])}")
        for f in a["figures"]:
            out.append(f"- **{f['label'] or 'Figure ?'}** - section: {f['section']} (heading: '{f['heading']}')")
            for c in f["candidates"][:6]:
                out.append(f"    - {c['kind']}: {c['url']}")
        out.append("")
    p = originals_dir(root) / "inspection_report.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(p)


def run_batch(root, case_ids, min_interval=6.0, jitter=2.0, retry_manual=False, fetcher=None) -> dict:
    """Download figures for the given cases, resuming where earlier runs stopped."""
    reg = {r["case_id"]: r for r in read_csv(path(root, "registry"))}
    todo = []
    man = read_manifest(root)
    for cid in [str(c) for c in case_ids]:
        rows = [r for r in man if r["case_id"] == cid]
        done_ok = rows and all(r["download_status"] in TERMINAL or (r["download_status"] == "manual_needed" and not retry_manual)
                               for r in rows) and all(
            (originals_dir(root) / f"{int(cid):03d}" / r["local_filename"]).exists()
            for r in rows if r["download_status"] in ("downloaded", "manual_downloaded"))
        if not done_ok:
            todo.append(cid)
    STATE.update(running=True, stop=False, done=0, total=len(todo), started=time.time(), phase="downloading")
    _log(f"Starting: {len(todo)} case(s) to fetch, {len(case_ids) - len(todo)} already complete (skipped).")
    fetcher = fetcher or Fetcher(min_interval, jitter)
    paused = ""
    net_fail = 0
    try:
        for cid in todo:
            if STATE["stop"]:
                paused = "stopped by user"
                break
            STATE["current"] = cid
            try:
                rows = download_case(root, {**reg[cid], "case_id": cid}, fetcher)
            except Paused as p:
                paused = str(p)
                break
            except Exception as e:  # network trouble: record, pause after 3 in a row
                net_fail += 1
                rows = [{"case_id": cid, "figure_number": "", "part": "", "source_article_url": reg[cid]["source_url"],
                         "download_status": "failed", "status_reason": f"network error: {e!r}"[:300],
                         "review_status": "unreviewed", "downloaded_at": dt.datetime.now().isoformat(timespec="seconds")}]
            man = [r for r in read_manifest(root) if r["case_id"] != cid] + rows
            write_manifest(root, man)
            n_dl = sum(r["download_status"] == "downloaded" for r in rows)
            n_man = sum(r["download_status"] == "manual_needed" for r in rows)
            if any(r["download_status"] == "failed" for r in rows):
                _log(f"Case {cid}: FAILED - {rows[0]['status_reason'][:160]}")
            else:
                net_fail = 0
                _log(f"Case {cid}: {n_dl} figure file(s) downloaded" + (f", {n_man} need manual download" if n_man else ""))
            STATE["done"] += 1
            if net_fail >= 3:
                paused = ("3 cases in a row could not reach the journal site (no internet connection, or the network "
                          "blocks it). Check the connection, then press Retry")
                break
    finally:
        STATE.update(running=False, current="", phase="paused: " + paused if paused else "finished")
        if paused:
            _log("Paused: " + paused)
        else:
            _log("Finished.")
    return {"processed": STATE["done"], "todo": len(todo), "paused": paused, "requests": fetcher.requests}


def start_background(root, case_ids, **kw) -> bool:
    if STATE["running"]:
        return False
    STATE["log"] = []
    threading.Thread(target=run_batch, args=(root, case_ids), kwargs=kw, daemon=True).start()
    return True


# ----------------------------------------------------------------------------- human steps

def save_review(root, cid, filename, status, revealing, who, notes) -> str:
    if status not in REVIEW_CHOICES or not who.strip():
        return "Not saved: choose a review decision and add initials."
    rows = read_manifest(root)
    hit = False
    for r in rows:
        if r["case_id"] == str(cid) and r.get("local_filename") == filename:
            r.update(review_status=status, contains_revealing_text="yes" if revealing else "no",
                     reviewed_by=who.strip(), reviewed_date=dt.date.today().isoformat(), review_notes=notes.strip())
            hit = True
    if not hit:
        return "Not saved: file not found in manifest."
    write_manifest(root, rows)
    return f"Review saved for {filename}."


def add_manual_file(root, cid, figure_number, part, data: bytes, orig_name: str, image_url: str, who: str) -> str:
    fmt, w, h = image_info(data)
    if not fmt:
        return "Not saved: the file is not a recognised image (JPG, PNG, GIF, TIFF, WebP)."
    if not str(figure_number).isdigit() or not who.strip():
        return "Not saved: figure number and initials are required."
    part = re.sub(r"[^a-j]", "", (part or "").lower())[:1]
    folder = originals_dir(root) / f"{int(cid):03d}"
    folder.mkdir(parents=True, exist_ok=True)
    fn = f"IMG-{int(cid):03d}-{int(figure_number)}{part}.{fmt}"
    if (folder / fn).exists():
        return f"Not saved: {fn} already exists. Use a part letter (a, b, ...) for additional panels."
    (folder / fn).write_bytes(data)
    reg = {r["case_id"]: r for r in read_csv(path(root, "registry"))}
    rows = [r for r in read_manifest(root) if not (r["case_id"] == str(cid) and r["download_status"] == "manual_needed"
                                                    and r.get("figure_number") in ("", str(figure_number)) and not r.get("local_filename"))]
    rows.append({"case_id": str(cid), "figure_number": str(int(figure_number)), "part": part, "section": "case",
                 "cited_in_case_text": "yes" if int(figure_number) in cited_figures(reg.get(str(cid), {}).get("text_only_input", "")) else "unknown",
                 "source_article_url": reg.get(str(cid), {}).get("source_url", ""), "image_url": image_url.strip(),
                 "local_filename": fn, "width": w, "height": h, "bytes": len(data), "sha256": sha256_file(folder / fn),
                 "download_status": "manual_downloaded", "status_reason": f"saved by {who.strip()} from browser download '{orig_name}'",
                 "downloaded_at": dt.datetime.now().isoformat(timespec="seconds"), "review_status": "unreviewed"})
    write_manifest(root, rows)
    return f"Saved {fn} ({w}x{h}). It still needs review."


def make_prepared_copy(root, cid, filename) -> str:
    """Copy a CONFIRMED original into images/prepared for cropping. Never approves it."""
    from .common import images_dir
    row = next((r for r in read_manifest(root) if r["case_id"] == str(cid) and r.get("local_filename") == filename), None)
    if not row:
        return "Not found in manifest."
    if row.get("review_status") != "confirmed_case_figure":
        return "Not copied: a reviewer must first confirm this figure belongs to the case presentation."
    src = originals_dir(root) / f"{int(cid):03d}" / filename
    dst = images_dir(root) / filename
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return f"{filename} already exists in the prepared folder; it was not overwritten."
    dst.write_bytes(src.read_bytes())
    return (f"Copied to prepared/{filename}. Now crop captions, panel letters or text that reveal the diagnosis "
            f"(keep arrows) in an image editor, then describe it on the Images page.")


def summary(root, case_ids) -> dict:
    man = read_manifest(root)
    ids = {str(c) for c in case_ids}
    rows = [r for r in man if r["case_id"] in ids]
    cases_with = {r["case_id"] for r in rows}
    return {"cases": len(ids), "cases_attempted": len(cases_with),
            "downloaded": sum(r["download_status"] in ("downloaded", "manual_downloaded") for r in rows),
            "manual_needed_cases": sorted({r["case_id"] for r in rows if r["download_status"] == "manual_needed"}, key=int),
            "failed_cases": sorted({r["case_id"] for r in rows if r["download_status"] == "failed"}, key=int),
            "skipped_answer": sum(r["download_status"] == "skipped_answer_section" for r in rows),
            "unreviewed": sum(r["download_status"] in ("downloaded", "manual_downloaded") and r.get("review_status") == "unreviewed" for r in rows)}
