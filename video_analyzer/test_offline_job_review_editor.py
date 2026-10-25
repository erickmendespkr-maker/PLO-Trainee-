"""Static offline editor tests, including browser-script syntax validation."""
import copy
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from offline_job_review_editor import render_editor, export_editor, MAX_BROWSER_HINTS


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job_id = "b" * 32
        self.handoff = {
            "analysis_status": "unapproved_offline_review_handoff",
            "job_id": self.job_id, "source_sha256": "a" * 64,
            "requires_manual_review": True, "ready_for_equity_or_ev": False,
            "frames": [{"table_id": 1, "nominal_timestamp_seconds": 2.0,
                        "image": "table_01/frame_00000.png",
                        "ocr_hints_unverified": [
                            {"field": "pot", "candidate_index": 0,
                             "unverified_text": "150"}]}]
        }

    def test_renders_offline_editor(self):
        html = render_editor(self.handoff)
        self.assertIn("OCR não verificado", html)
        self.assertIn("ocr_review_submission.json", html)
        self.assertIn("handoff_sha256", html)
        self.assertNotIn("fetch(", html)
        self.assertNotIn("XMLHttpRequest", html)

    def test_escapes_ocr_html_script(self):
        self.handoff["frames"][0]["ocr_hints_unverified"][0]["unverified_text"] = (
            '</script><script>alert("unsafe")</script>')
        html = render_editor(self.handoff)
        self.assertEqual(html.count("</script>"), 1)
        self.assertNotIn("<script>alert", html)
        self.assertIn("u003c", html)

    def test_rejects_unsafe_image_path(self):
        self.handoff["frames"][0]["image"] = "../../etc/passwd"
        with self.assertRaisesRegex(ValueError, "Unsafe"): render_editor(self.handoff)

    def test_rejects_nonhandoff(self):
        self.handoff["analysis_status"] = "verified"
        with self.assertRaises(ValueError): render_editor(self.handoff)

    def test_no_ocr_still_renders(self):
        self.handoff["frames"][0]["ocr_hints_unverified"] = []
        html = render_editor(self.handoff)
        self.assertIn('"rows": []', html)

    def test_limit_prevents_oversized_page(self):
        hint = self.handoff["frames"][0]["ocr_hints_unverified"][0]
        self.handoff["frames"][0]["ocr_hints_unverified"] = [
            dict(hint, candidate_index=i) for i in range(MAX_BROWSER_HINTS + 1)]
        with self.assertRaisesRegex(ValueError, "Too many"): render_editor(self.handoff)

    def test_export_write_once(self):
        folder = self.root / self.job_id / "review_handoff"
        folder.mkdir(parents=True)
        with patch("offline_job_review_editor.build_handoff", return_value=self.handoff):
            path = export_editor(Mock(), self.job_id, self.root)
            self.assertTrue(path.is_file())
            with self.assertRaises(FileExistsError):
                export_editor(Mock(), self.job_id, self.root)

    def test_node_script_syntax(self):
        if not shutil.which("node"):
            self.skipTest("Node not installed")
        html = render_editor(self.handoff)
        script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", encoding="utf-8") as file:
            file.write(script)
            file.flush()
            completed = subprocess.run(["node", "--check", file.name],
                                       capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
