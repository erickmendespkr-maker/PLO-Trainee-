"""Static offline page tests with synthetic, non-decodable MP4 fixture bytes."""
import json
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from offline_reviewed_decision_timeline_page import export, render
import test_offline_reviewed_decision_timeline as fixtures


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.video_sources = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "video":
            self.video_sources.append(dict(attrs).get("src"))


class PageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DecisionTimelineTests('test_success_and_blocked_sorted')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def test_success_and_blocked_page(self):
        self.fixture.make("first", 1, "h1", 2)
        self.fixture.make("blocked", 2, "h2", 3, blocked=True)
        output = self.root / "review.html"
        result = export(self.fixture.dirs, output)
        self.assertEqual((result["hands"], result["clips"]), (2, 1))
        text = output.read_text()
        self.assertIn("Bloqueada: sem cálculo", text)
        self.assertIn("Equity Monte Carlo: 50.00%", text)
        self.assertIn("default-src 'none'", text)
        self.assertIn("sem JavaScript", text)
        parser = Tags()
        parser.feed(text)
        self.assertEqual(parser.video_sources, ["./first/clip.mp4"])
        self.assertNotIn("script", parser.tags)

    def test_escapes_untrusted_hand_label(self):
        self.fixture.make("first", 1, '<img src=x onerror=alert(1)>', 2)
        output = self.root / "review.html"
        export(self.fixture.dirs, output)
        text = output.read_text()
        self.assertIn("&lt;img", text)
        parser = Tags(); parser.feed(text)
        self.assertNotIn("img", parser.tags)

    def test_overlap_warning_is_review_only(self):
        self.fixture.make("first", 1, "h1", 2)
        self.fixture.make("second", 1, "h2", 2.5)
        output = self.root / "review.html"
        export(self.fixture.dirs, output)
        self.assertIn("first / second", output.read_text())
        self.assertIn("Conferir manualmente", output.read_text())

    def test_create_only(self):
        self.fixture.make()
        output = self.root / "review.html"
        output.write_text("existing")
        with self.assertRaises(ValueError): export(self.fixture.dirs, output)
        self.assertEqual(output.read_text(), "existing")

    def test_reaudit_rejects_modified_clip(self):
        folder = self.fixture.make()
        (folder / "clip.mp4").write_bytes(b"tamper")
        with self.assertRaises(ValueError): export(self.fixture.dirs, self.root / "review.html")
        self.assertFalse((self.root / "review.html").exists())

    def test_no_output_outside_session(self):
        self.fixture.make()
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(ValueError): export(self.fixture.dirs, other / "review.html")

    def test_deterministic_html(self):
        self.fixture.make()
        from offline_reviewed_decision_timeline import build_index
        index = build_index(self.fixture.dirs)
        self.assertEqual(render(index), render(index))


if __name__ == "__main__":
    unittest.main()
