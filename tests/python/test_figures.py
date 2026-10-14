"""Figure downloader tests against a LOCAL SYNTHETIC article site (no real journal pages)."""
from __future__ import annotations

import shutil
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from oe import figures  # noqa: E402
from oe.common import images_dir, path, read_csv, write_csv  # noqa: E402


def png(w, h):
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


GOOD = """<html><head><title>SYNTHETIC article</title></head><body>
<header><img src="/static/journal-logo.png" alt="logo"></header>
<h1>SYNTHETIC Clinical Challenge</h1><h2>Case Presentation</h2>
<p>A patient ... (Figure 1). Further views (Figure 2).</p>
<div class="figure-section"><div class="graphic-wrap"><img class="content-image" src="/img/f1_medium.png" width="500"></div>
<a class="fig-view-orig" href="/img/f1_large.png">View Large</a>
<div class="fig-caption"><span class="fig-label">Figure 1.</span> SYNTHETIC fundus photograph of the right eye.</div></div>
<figure><img src="/img/f2a.png" width="400"><img src="/img/f2b.png" width="400">
<figcaption>Figure 2. SYNTHETIC OCT panels A and B.</figcaption></figure>
<aside class="related-articles"><img src="/img/related_cover.png" width="300"></aside>
<h2>Diagnosis</h2><p>SYNTHETIC answer.</p><h2>Discussion</h2>
<div class="figure-section"><img src="/img/f3.png" width="500"><div class="fig-caption">Figure 3. SYNTHETIC histology after surgery.</div></div>
<div class="figure-section"><img src="/img/e1.png" width="500"><div class="fig-caption">eFigure 1. SYNTHETIC supplement.</div></div>
</body></html>"""
PAYWALL = "<html><body><h1>SYNTHETIC</h1><p>Sign in to access this article. Purchase access.</p></body></html>"
CHALLENGE = "<html><head><title>Just a moment...</title></head><body>Checking your browser before accessing.</body></html>"
DENIED_IMG = """<html><body><h2>Case</h2><figure><img src="/img/denied.png" width="600"><figcaption>Figure 1. SYNTHETIC.</figcaption></figure></body></html>"""

IMAGES = {"/img/f1_medium.png": png(500, 400), "/img/f1_large.png": png(1600, 1280), "/img/f2a.png": png(800, 600),
          "/img/f2b.png": png(820, 600), "/img/f3.png": png(700, 500), "/img/e1.png": png(300, 300),
          "/img/related_cover.png": png(300, 300), "/static/journal-logo.png": png(100, 40)}
HITS: list[str] = []


class Site(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        HITS.append(self.path)
        self.server_cookie_seen = "Cookie" in self.headers
        if self.path == "/robots.txt":
            return self._send(200, "text/plain", b"User-agent: *\nDisallow: /private/\n")
        pages = {"/a/good": GOOD, "/a/paywall": PAYWALL, "/a/challenge": CHALLENGE, "/a/denied": DENIED_IMG,
                 "/private/a": GOOD}
        if self.path in pages:
            return self._send(200, "text/html; charset=utf-8", pages[self.path].encode())
        if self.path == "/a/slow":
            return self._send(429, "text/html", b"slow down")
        if self.path == "/img/denied.png":
            return self._send(403, "text/html", b"<html>Sign in</html>")
        if self.path in IMAGES:
            return self._send(200, "image/png", IMAGES[self.path])
        return self._send(404, "text/html", b"nope")

    def _send(self, code, ct, body):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Site)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "data"
        cases = {"2": "/a/good", "3": "/a/paywall", "4": "/a/denied", "5": "/private/a", "6": "/a/slow", "7": "/a/challenge"}
        reg = [{"case_id": c, "eligible": "Yes", "source_url": self.base + u,
                "text_only_input": "SYNTHETIC case (Figure 1) and (Figure 2). A, SYNTHETIC fundus photograph of the right eye."}
               for c, u in cases.items()]
        reg.append({"case_id": "8", "eligible": "Yes", "source_url": "A title, not a link", "text_only_input": ""})
        write_csv(path(self.root, "registry"), reg, ["case_id", "eligible", "source_url", "text_only_input"])
        HITS.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fetcher(self):
        return figures.Fetcher(min_interval=0, jitter=0)

    def man(self, cid):
        return [r for r in figures.read_manifest(self.root) if r["case_id"] == cid]

    def test_good_page_takes_case_figures_largest_version_only(self):
        r = figures.run_batch(self.root, ["2"], fetcher=self.fetcher())
        self.assertEqual(r["paused"], "")
        rows = {(x["figure_number"], x["part"]): x for x in self.man("2")}
        self.assertEqual(rows[("1", "")]["download_status"], "downloaded")
        self.assertEqual((rows[("1", "")]["width"], rows[("1", "")]["height"]), ("1600", "1280"))
        self.assertTrue(rows[("1", "")]["image_url"].endswith("f1_large.png"))
        self.assertEqual(rows[("2", "a")]["download_status"], "downloaded")  # two separate panel images -> two files
        self.assertEqual(rows[("2", "b")]["download_status"], "downloaded")
        self.assertEqual(rows[("3", "")]["download_status"], "skipped_answer_section")
        self.assertTrue(any(x["download_status"] == "skipped_supplement" for x in rows.values()))
        folder = figures.originals_dir(self.root) / "002"
        files = sorted(p.name for p in folder.glob("IMG-*"))
        self.assertEqual(files, ["IMG-002-1.png", "IMG-002-2a.png", "IMG-002-2b.png"])
        for bad in ("/static/journal-logo.png", "/img/related_cover.png", "/img/f3.png", "/img/e1.png"):
            self.assertNotIn(bad, HITS)
        self.assertTrue(all(x["review_status"] == "unreviewed" for x in rows.values()))
        self.assertGreater(float(rows[("1", "")]["caption_match_score"]), 0.5)

    def test_resume_no_duplicates_no_new_requests(self):
        figures.run_batch(self.root, ["2"], fetcher=self.fetcher())
        before = list(figures.read_manifest(self.root))
        HITS.clear()
        r = figures.run_batch(self.root, ["2"], fetcher=self.fetcher())
        self.assertEqual(r["todo"], 0)
        self.assertEqual(HITS, [])
        self.assertEqual(figures.read_manifest(self.root), before)
        # a deleted file is fetched again (from the cached page), without duplicating rows
        (figures.originals_dir(self.root) / "002" / "IMG-002-1.png").unlink()
        figures.run_batch(self.root, ["2"], fetcher=self.fetcher())
        self.assertNotIn("/a/good", HITS)  # page cache reused
        self.assertEqual(len(self.man("2")), len([x for x in before if x["case_id"] == "2"]))
        self.assertFalse(list((figures.originals_dir(self.root) / "002").glob("*.part")))

    def test_access_restrictions_are_flagged_not_bypassed(self):
        figures.run_batch(self.root, ["3", "4", "5", "8"], fetcher=self.fetcher())
        self.assertEqual(self.man("3")[0]["download_status"], "manual_needed")
        self.assertIn("sign-in", self.man("3")[0]["status_reason"])
        d = [x for x in self.man("4") if x["figure_number"] == "1"][0]
        self.assertEqual(d["download_status"], "manual_needed")
        self.assertIn("403", d["status_reason"])
        self.assertIn("robots.txt", self.man("5")[0]["status_reason"])
        self.assertNotIn("/private/a", HITS)
        self.assertIn("no usable article link", self.man("8")[0]["status_reason"])

    def test_rate_limit_and_challenge_pause_the_batch(self):
        r = figures.run_batch(self.root, ["6", "2"], fetcher=self.fetcher())
        self.assertIn("429", r["paused"])
        self.assertEqual(self.man("2"), [])  # nothing after the pause
        r = figures.run_batch(self.root, ["7", "2"], fetcher=self.fetcher())
        self.assertIn("automated-access check", r["paused"])
        self.assertFalse((figures.originals_dir(self.root) / "007" / "_article_page.html").exists())

    def test_unreachable_site_pauses_after_three(self):
        reg = [{"case_id": str(c), "eligible": "Yes", "source_url": "http://127.0.0.1:9/a/" + str(c), "text_only_input": ""}
               for c in range(10, 16)]
        write_csv(path(self.root, "registry"), reg, ["case_id", "eligible", "source_url", "text_only_input"])
        r = figures.run_batch(self.root, [x["case_id"] for x in reg], fetcher=self.fetcher())
        self.assertIn("could not reach", r["paused"])
        self.assertEqual(r["processed"], 3)
        self.assertTrue(all(x["download_status"] == "failed" for x in figures.read_manifest(self.root)))

    def test_request_spacing(self):
        waits = []
        f = figures.Fetcher(min_interval=6, jitter=0, sleep=waits.append)
        f.last = __import__("time").time()
        f.get(self.base + "/a/paywall")
        self.assertTrue(waits and waits[0] > 5.5)

    def test_no_cookies_sent_and_honest_agent(self):
        import urllib.request as u
        self.assertNotIn("Cookie", figures.USER_AGENT)
        self.assertFalse(any(isinstance(h, u.HTTPCookieProcessor) for h in u.build_opener().handlers))

    def test_image_info_jpeg(self):
        jpg = b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + \
            b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 900, 1200) + b"\x00" * 10
        self.assertEqual(figures.image_info(jpg), ("jpg", 1200, 900))
        self.assertEqual(figures.image_info(b"<html>"), ("", 0, 0))

    def test_review_gate_prepared_copy_and_manual_upload(self):
        figures.run_batch(self.root, ["2", "3"], fetcher=self.fetcher())
        msg = figures.make_prepared_copy(self.root, "2", "IMG-002-1.png")
        self.assertIn("must first confirm", msg)
        self.assertFalse((images_dir(self.root) / "IMG-002-1.png").exists())
        self.assertIn("saved", figures.save_review(self.root, "2", "IMG-002-1.png", "confirmed_case_figure", True, "TST", "label in corner"))
        self.assertIn("Copied", figures.make_prepared_copy(self.root, "2", "IMG-002-1.png"))
        orig = figures.originals_dir(self.root) / "002" / "IMG-002-1.png"
        self.assertEqual((images_dir(self.root) / "IMG-002-1.png").read_bytes(), orig.read_bytes())
        self.assertIn("not overwritten", figures.make_prepared_copy(self.root, "2", "IMG-002-1.png"))
        self.assertIn("not a recognised image", figures.add_manual_file(self.root, "3", "1", "", b"<html>", "x.html", "", "TST"))
        out = figures.add_manual_file(self.root, "3", "1", "", png(900, 700), "fig.png", "", "TST")
        self.assertIn("IMG-003-1.png", out)
        st = [x["download_status"] for x in self.man("3")]
        self.assertEqual(st, ["manual_downloaded"])
        self.assertEqual(self.man("3")[0]["review_status"], "unreviewed")

    def test_inspection_report(self):
        figures.run_batch(self.root, ["2"], fetcher=self.fetcher())
        rep = Path(figures.inspection_report(self.root, ["2", "3"])).read_text()
        self.assertIn("Figure 1", rep)
        self.assertIn("section: answer", rep)
        self.assertIn("Page not downloaded", rep)


class TestFiguresApp(unittest.TestCase):
    def test_pages_and_original_serving(self):
        from oe import app
        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "data"
            pilot_root = root / "pilot"
            pilot_root.mkdir(parents=True)
            (pilot_root / "config_override.json").write_text('{"shared_registry_root": "..", "pilot": {"case_ids": [2]}}')
            write_csv(path(root, "registry"), [{"case_id": "2", "eligible": "Yes", "source_url": "http://127.0.0.1:9/a",
                                                 "text_only_input": "SYNTHETIC"}], ["case_id", "eligible", "source_url", "text_only_input"])
            d = figures.originals_dir(root) / "002"
            d.mkdir(parents=True)
            (d / "IMG-002-1.png").write_bytes(png(10, 10))
            figures.write_manifest(root, [{"case_id": "2", "figure_number": "1", "part": "", "local_filename": "IMG-002-1.png",
                                           "download_status": "downloaded", "review_status": "unreviewed", "source_article_url": "x"}])
            app.STATE.update(main=root, pilot=pilot_root)
            srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            u = f"http://127.0.0.1:{srv.server_address[1]}"
            self.assertIn("Download test cases", urlopen(u + "/figures").read().decode())
            self.assertIn("disabled title='Sign off", urlopen(u + "/figures").read().decode())
            self.assertIn("IMG-002-1.png", urlopen(u + "/figures/2").read().decode())
            self.assertEqual(urlopen(u + "/original/2/IMG-002-1.png").read()[:4], b"\x89PNG")
            with self.assertRaises(Exception):
                urlopen(u + "/original/2/..%2F..%2Fregistry%2Fcase_registry.csv")
            srv.shutdown()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
