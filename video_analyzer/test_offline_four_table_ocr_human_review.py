"""Synthetic/recorded-benchmark tests of human-reviewed OCR without math promotion."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import offline_four_table_ocr_human_review as m

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmark"


class OCRHumanReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = BENCH / "samples"
        self.video = BENCH / "synthetic_60s.mp4"
        self.ocr = BENCH / "ocr_proposals.json"
        self.out = self.root / "result.json"
        source = json.loads(self.ocr.read_text())
        self.decisions = []
        for i, c in enumerate(source["candidates"]):
            value = {"pot": "120", "stack": "80", "action": "call",
                     "board": "As Kd Qh"}[c["field"]]
            self.decisions.append({"candidate_index": i, "decision": "correct",
                                   "reviewed_text": value,
                                   "visual_evidence_checked": True, "note": "synthetic"})
        self.review_file = self.root / "review.json"
        self.manifest = {"schema_version": 1,
                         "source_ocr_sha256": hashlib.sha256(self.ocr.read_bytes()).hexdigest(),
                         "decisions": self.decisions}
        self.write()

    def write(self):
        self.review_file.write_text(json.dumps(self.manifest))

    def run_review(self, **kwargs):
        return m.review(self.bundle, kwargs.get("ocr", self.ocr), self.review_file,
                        self.out, recording_path=self.video)

    def reject(self):
        self.write()
        with self.assertRaises((ValueError, FileExistsError)):
            self.run_review()
        self.assertFalse(self.out.exists())

    def test_real_bundle_review_preserves_lineage_and_blocks_math(self):
        report = self.run_review()
        self.assertEqual(len(report["reviewed_candidates"]), 16)
        self.assertFalse(report["ready_for_equity_or_ev"])
        self.assertFalse(report["complete_hand_reconstructed"])
        self.assertFalse(report["reviewer_identity_authenticated"])
        self.assertEqual(report["reviewed_candidates"][0]["reviewed_value"], "120")
        self.assertEqual(json.loads(self.out.read_text()), report)

    def test_reject_entry_has_no_value(self):
        self.decisions[0].update(decision="reject", reviewed_text=None,
                                 visual_evidence_checked=False)
        self.write()
        report = self.run_review()
        self.assertIsNone(report["reviewed_candidates"][0]["reviewed_value"])

    def test_confirm_requires_exact_text(self):
        self.decisions[0].update(decision="confirm", reviewed_text="120")
        self.reject()

    def test_confirm_exact_semantically_valid_text(self):
        # A raw amount from OCR is not a numeric field; test action confirmation on a modified copy.
        copy = self.root / "ocr.json"
        data = json.loads(self.ocr.read_text())
        data["candidates"][0]["raw_ocr_text"] = "120"
        copy.write_text(json.dumps(data))
        self.manifest["source_ocr_sha256"] = m.sha(copy)
        self.decisions[0].update(decision="confirm", reviewed_text="120")
        self.write()
        result = self.run_review(ocr=copy)
        self.assertEqual(result["reviewed_candidates"][0]["review_decision"], "confirm")

    def test_false_visual_check_rejected(self):
        self.decisions[0]["visual_evidence_checked"] = False
        self.reject()

    def test_missing_review_rejected(self):
        self.decisions.pop()
        self.reject()

    def test_wrong_order_rejected(self):
        self.decisions[1]["candidate_index"] = 0
        self.reject()

    def test_bool_index_rejected(self):
        self.decisions[0]["candidate_index"] = False
        self.reject()

    def test_extra_approval_flag_rejected(self):
        self.decisions[0]["authorize_equity"] = True
        self.reject()

    def test_wrong_ocr_hash_rejected(self):
        self.manifest["source_ocr_sha256"] = "0" * 64
        self.reject()

    def test_invalid_amount_rejected(self):
        self.decisions[0]["reviewed_text"] = "-100"
        self.reject()

    def test_hidden_card_string_rejected(self):
        self.decisions[3]["reviewed_text"] = "As Kd Qh XX"
        self.reject()

    def test_duplicate_cards_rejected(self):
        self.decisions[3]["reviewed_text"] = "As As Qh"
        self.reject()

    def test_unrecognized_action_rejected(self):
        self.decisions[2]["reviewed_text"] = "auto_play"
        self.reject()

    def test_reject_must_have_null_value(self):
        self.decisions[0]["decision"] = "reject"
        self.reject()

    def test_duplicate_json_key_rejected(self):
        self.review_file.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            self.run_review()

    def test_symlink_review_rejected(self):
        target = self.root / "real.json"
        self.review_file.rename(target)
        self.review_file.symlink_to(target)
        with self.assertRaises(ValueError):
            self.run_review()

    def test_existing_output_preserved(self):
        self.out.write_text("original")
        with self.assertRaises(ValueError):
            self.run_review()
        self.assertEqual(self.out.read_text(), "original")

    def test_tampered_crop_rejected(self):
        copy = self.root / "bundle"
        shutil.copytree(self.bundle, copy)
        (copy / "tables/table_01_sample_00.png").write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            m.review(copy, self.ocr, self.review_file, self.out)
        self.assertFalse(self.out.exists())

    def test_wrong_video_rejected(self):
        fake = self.root / "fake.mp4"
        fake.write_bytes(b"fake")
        with self.assertRaises(ValueError):
            m.review(self.bundle, self.ocr, self.review_file, self.out,
                     recording_path=fake)

    def test_outside_bundle_enforced(self):
        with self.assertRaises(ValueError):
            m.review(self.bundle, self.ocr, self.review_file,
                     self.bundle / "bad.json", recording_path=self.video)

    def test_normalize_hero_cards_and_bounds(self):
        self.assertEqual(m.normalize("hero_cards", "As Kd Qh Jc Tc"), "As Kd Qh Jc Tc")
        self.assertEqual(m.normalize("hero_cards", "As Kd Qh Jc Tc 9s"), "As Kd Qh Jc Tc 9s")
        with self.assertRaises(ValueError):
            m.normalize("hero_cards", "As Kd")
        with self.assertRaises(ValueError):
            m.normalize("stack", "1000000000")


if __name__ == "__main__":
    unittest.main()
