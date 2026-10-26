"""Synthetic file/HTML security tests; no real PLO video needed."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest

from offline_clip_temporal_review_page import export, load, render


class TagReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class TemporalPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / "source.mp4"
        self.clip = self.root / "clip.mp4"
        self.report = self.root / "tail.json"
        self.manifest = self.root / "session.json"
        self.output = self.root / "review.html"
        self.src.write_bytes(b"synthetic-source-video-bytes")
        self.clip.write_bytes(b"synthetic-clip-video-bytes")
        self.data = {
            "schema_version": 1, "status": "terminal_sequence_diagnostic_only",
            "source_sha256": hashlib.sha256(self.src.read_bytes()).hexdigest(),
            "clip_sha256": hashlib.sha256(self.clip.read_bytes()).hexdigest(),
            "classification": "possible_added_terminal_duplicate",
            "possible_added_terminal_duplicate": True,
            "possible_missing_terminal_frames": False,
            "visual_provenance_verified": False, "ocr_verified": False,
            "equity_ev_authorized": False,
            "terminal_frame_mae_0_to_255": 0.55,
            "source_container_duration_seconds": 5.0,
            "clip_container_duration_seconds": 3.0,
        }
        self.index = {"schema_version": 1, "session_label": "Synthetic session",
                      "source_recording": self.src.name,
                      "entries": [{"clip": self.clip.name, "tail_audit": self.report.name,
                                   "hand_label": "table-1/hand-1"}]}
        self.write()

    def write(self):
        self.report.write_text(json.dumps(self.data))
        self.manifest.write_text(json.dumps(self.index))

    def test_render_warning_without_authorizing_math(self):
        result = export(self.manifest, self.output)
        self.assertEqual(result["temporal_alerts_or_indeterminate"], 1)
        self.assertTrue(result["manual_review_required"])
        self.assertFalse(result["equity_ev_authorized"])
        page = self.output.read_text()
        self.assertIn("revisao-temporal-necessaria", page)
        self.assertIn("Possível duplicação terminal", page)
        self.assertNotIn("<script", page)
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("<video", page)

    def test_clean_tail_is_not_proof(self):
        self.data["classification"] = "no_anomaly_detected_in_compared_tail"
        self.data["possible_added_terminal_duplicate"] = False
        self.write()
        result = export(self.manifest, self.output)
        self.assertEqual(result["temporal_alerts_or_indeterminate"], 0)
        self.assertTrue(result["manual_review_required"])
        self.assertIn("não é prova", self.output.read_text())

    def test_html_escape_untrusted_hand_and_label(self):
        self.index["session_label"] = '<img src=x onerror="alert(1)">'
        self.index["entries"][0]["hand_label"] = '<script>alert(1)</script>'
        self.write()
        export(self.manifest, self.output)
        page = self.output.read_text()
        self.assertIn("&lt;script&gt;", page)
        doc = TagReader(); doc.feed(page)
        self.assertFalse(any(t in ("script", "img") for t, _ in doc.tags))

    def test_reject_tampered_clip(self):
        self.clip.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            export(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_reject_source_mismatch(self):
        self.src.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            export(self.manifest, self.output)

    def test_reject_traversal(self):
        self.index["entries"][0]["clip"] = "../clip.mp4"
        self.write()
        with self.assertRaisesRegex(ValueError, "Unsafe local filename"):
            export(self.manifest, self.output)

    def test_reject_symlink_clip(self):
        self.clip.unlink()
        self.clip.symlink_to(self.src)
        with self.assertRaises(ValueError):
            export(self.manifest, self.output)

    def test_reject_duplicate_keys(self):
        self.report.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            export(self.manifest, self.output)

    def test_reject_nan(self):
        self.report.write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, "Non-finite JSON"):
            export(self.manifest, self.output)

    def test_reject_report_verification_claim(self):
        self.data["equity_ev_authorized"] = True
        self.write()
        with self.assertRaisesRegex(ValueError, "Unexpected claim"):
            export(self.manifest, self.output)

    def test_reject_overwrite(self):
        self.output.write_text("existing")
        with self.assertRaisesRegex(ValueError, "must be new"):
            export(self.manifest, self.output)
        self.assertEqual(self.output.read_text(), "existing")

    def test_reject_output_outside_folder(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(ValueError, "beside the manifest"):
                export(self.manifest, Path(other) / "review.html")

    def test_reject_duplicate_entries(self):
        self.index["entries"].append(self.index["entries"][0].copy())
        self.write()
        with self.assertRaisesRegex(ValueError, "Duplicate input"):
            export(self.manifest, self.output)

    def test_reject_too_many_entries(self):
        self.index["entries"] *= 41
        self.write()
        with self.assertRaisesRegex(ValueError, "Invalid review manifest"):
            export(self.manifest, self.output)

    def test_reject_contradictory_flag(self):
        self.data["possible_added_terminal_duplicate"] = False
        self.write()
        with self.assertRaisesRegex(ValueError, "Contradictory duplicate"):
            export(self.manifest, self.output)

    def test_deterministic_html(self):
        label, rows, _ = load(self.manifest)
        self.assertEqual(render(label, rows), render(label, rows))


if __name__ == "__main__":
    unittest.main()
