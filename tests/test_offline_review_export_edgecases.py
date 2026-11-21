"""Additional synthetic integration checks for export -> manifest -> audit.

Run: python -m unittest discover -s tests -p 'test_offline_review_export_edgecases.py'
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from video_analyzer.offline_review_clip_export import export_review_clip
from video_analyzer.offline_review_export_audit import audit_review_export


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
class ExportAuditEdgeCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10",
                        "-t", "3", "-c:v", "mpeg4", str(self.source)],
                       check=True, capture_output=True, timeout=30)
        self.clip = self.root / "clip.mp4"

    def _export(self, **extra):
        return export_review_clip(self.source, self.clip,
                                  {"table_id": 4, "start_pts": 0.5, "end_pts": 1.5, **extra})

    def _edit(self, change):
        path = self.clip.with_suffix(".json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        change(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_missing_evidence_is_not_strategic_approval(self):
        manifest = self._export()
        self.assertEqual(manifest["evidence_gate"]["status"], "REVIEW_REQUIRED")
        self.assertFalse(manifest["evidence_gate"]["can_attach_conditional_ev"])
        result = audit_review_export(self.clip, source=self.source)
        self.assertFalse(result["hand_verified"])
        self.assertFalse(result["strategic_analysis_verified"])

    def test_conditional_gate_does_not_claim_gto(self):
        verified = {key: True for key in ("table_verified", "hand_verified",
                    "hero_cards_verified", "board_verified", "action_verified",
                    "amounts_verified")}
        verified["ev_assumptions"] = {"ranges": "synthetic range", "rake": 0,
                                      "future_actions": "none"}
        manifest = self._export(**verified)
        self.assertEqual(manifest["evidence_gate"]["status"], "APPROVED_CONDITIONAL")
        self.assertFalse(manifest["gto_solution"])
        self.assertFalse(audit_review_export(self.clip)["strategic_analysis_verified"])

    def test_unknown_status_rejected(self):
        self._export()
        self._edit(lambda m: m["evidence_gate"].update(status="UNVERIFIED_BUT_APPROVED"))
        with self.assertRaises(ValueError):
            audit_review_export(self.clip)

    def test_contradictory_approval_rejected(self):
        self._export()
        self._edit(lambda m: m["evidence_gate"].update(can_attach_conditional_ev=True))
        with self.assertRaises(ValueError):
            audit_review_export(self.clip)

    def test_tampered_source_duration_rejected_even_with_matching_hash(self):
        self._export()
        self._edit(lambda m: m.update(source_duration_seconds=99.0))
        with self.assertRaisesRegex(ValueError, "source duration mismatch"):
            audit_review_export(self.clip, source=self.source)

    def test_untampered_source_duration_accepted(self):
        self._export()
        result = audit_review_export(self.clip, source=self.source)
        self.assertTrue(result["source_checked"])
        self.assertTrue(result["integrity_verified"])

    def test_source_mismatch_rejected(self):
        self._export()
        other = self.root / "other.mp4"
        other.write_bytes(b"not the recorded source")
        with self.assertRaises(ValueError):
            audit_review_export(self.clip, source=other)


if __name__ == "__main__":
    unittest.main()
