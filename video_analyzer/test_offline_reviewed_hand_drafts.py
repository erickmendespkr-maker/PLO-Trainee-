"""Synthetic unit tests for offline reviewed hand drafts; no live poker data."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_reviewed_hand_drafts import build


def sha(data):
    return hashlib.sha256(data).hexdigest()


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.review = self.root / "review.json"
        self.boundaries = self.root / "boundaries.json"
        self.obs = [
            self.o(0, 1, 2, "hero_cards", "As Ks Qs Js Ts"),
            self.o(1, 1, 4, "board", "2h 3h 4h"),
            self.o(2, 1, 5, "pot", "125.00"),
            self.o(3, 1, 6, "action", "call"),
            self.o(4, 2, 4, "hero_cards", "As Ks Qs Js Ts 9s"),
            self.o(5, 2, 5, "board", "2h 3h 4h"),
            self.o(6, 3, 4, "action", None, "pending"),
        ]
        self.hands = [
            {"hand_id": "H1", "table_id": 1, "variant": "PLO5",
             "start_seconds": 0, "end_seconds": 10, "note": "synthetic"},
            {"hand_id": "H2", "table_id": 2, "variant": "PLO6",
             "start_seconds": 0, "end_seconds": 10, "note": "synthetic"}]
        self.save()

    def o(self, index, table, time, field, value, decision="confirmed"):
        return {"proposal_index": index, "table_id": table,
                "decoded_source_pts_seconds": time, "field": field,
                "decision": decision, "normalized_value": value,
                "source_frame_sha256": "a" * 64, "roi_png_sha256": "b" * 64}

    def save(self):
        self.review.write_text(json.dumps({
            "schema_version": 1,
            "analysis_status": "offline_human_reviewed_ocr_observations_only",
            "ready_for_equity_or_ev": False, "hands_reconstructed": False,
            "source_roi_ocr_report_sha256": "c" * 64,
            "observations": self.obs}))
        self.boundaries.write_text(json.dumps({
            "schema_version": 1,
            "reviewed_report_sha256": sha(self.review.read_bytes()),
            "hands": self.hands}))

    def run_build(self):
        return build(self.review, self.boundaries, self.root / "output")

    def test_two_tables_and_unassigned(self):
        out = self.run_build()
        self.assertEqual(len(out["hands"]), 2)
        self.assertEqual(out["unassigned_observation_indices"], [6])
        self.assertFalse(out["ready_for_equity_or_ev"])
        self.assertEqual(out["hands"][0]["reviewed_fields"]["pot"][0]["value"], "125.00")
        self.assertTrue((self.root / "output" / "hand_drafts.json").exists())

    def test_pot_and_action_missing_in_second(self):
        out = self.run_build()
        self.assertIn("pot", out["hands"][1]["missing_fields"])
        self.assertIn("action", out["hands"][1]["missing_fields"])

    def test_stale_review_sha(self):
        self.save()
        doc = json.loads(self.boundaries.read_text())
        doc["reviewed_report_sha256"] = "d" * 64
        self.boundaries.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.run_build()
        self.assertFalse((self.root / "output").exists())

    def test_reject_overlapping_hands(self):
        self.hands.append({"hand_id": "H3", "table_id": 1, "variant": "PLO5",
                           "start_seconds": 8, "end_seconds": 12, "note": "overlap"})
        self.save()
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            self.run_build()

    def test_allow_simultaneous_different_tables(self):
        self.assertEqual(len(self.run_build()["hands"]), 2)

    def test_reject_wrong_variant(self):
        self.hands[0]["variant"] = "PLO6"
        self.save()
        with self.assertRaisesRegex(ValueError, "variant"):
            self.run_build()

    def test_detect_hero_board_collision(self):
        self.obs[1]["normalized_value"] = "As 3h 4h"
        self.save()
        out = self.run_build()
        self.assertIn("hero_board_card_collision", out["hands"][0]["consistency_warnings"])

    def test_detect_conflicting_hero(self):
        self.obs.append(self.o(7, 1, 7, "hero_cards", "Ah Kh Qh Jh Th"))
        self.save()
        out = self.run_build()
        self.assertIn("conflicting_hero_cards_observations", out["hands"][0]["consistency_warnings"])

    def test_reject_duplicate_observation(self):
        self.obs.append(dict(self.obs[0]))
        self.save()
        with self.assertRaisesRegex(ValueError, "observation"):
            self.run_build()

    def test_reject_unresolved_value(self):
        self.obs[6]["normalized_value"] = "call"
        self.save()
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            self.run_build()

    def test_reject_invalid_amount(self):
        self.obs[2]["normalized_value"] = "-125"
        self.save()
        with self.assertRaisesRegex(ValueError, "amount"):
            self.run_build()

    def test_reject_duplicate_json_keys(self):
        self.review.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.run_build()

    def test_reject_nonfinite_timestamp(self):
        self.obs[0]["decoded_source_pts_seconds"] = float("nan")
        self.save()
        with self.assertRaisesRegex(ValueError, "Nonfinite JSON"):
            self.run_build()

    def test_reject_existing_output(self):
        (self.root / "output").mkdir()
        with self.assertRaisesRegex(ValueError, "output"):
            self.run_build()

    def test_reject_symlink_input(self):
        link = self.root / "link.json"
        link.symlink_to(self.review)
        with self.assertRaisesRegex(ValueError, "Unsafe JSON"):
            build(link, self.boundaries, self.root / "output")

    def test_half_open_intervals(self):
        self.hands.append({"hand_id": "H3", "table_id": 1, "variant": "PLO5",
                           "start_seconds": 10, "end_seconds": 20, "note": "synthetic"})
        self.obs.append(self.o(7, 1, 10, "action", "check"))
        self.save()
        out = self.run_build()
        self.assertEqual(out["hands"][1]["observation_indices"], [7])

    def test_no_observations_warning(self):
        self.hands.append({"hand_id": "H3", "table_id": 4, "variant": "PLO6",
                           "start_seconds": 0, "end_seconds": 10, "note": "synthetic"})
        self.save()
        out = self.run_build()
        self.assertIn("no_observations_in_interval",
                      out["hands"][-1]["consistency_warnings"])

    def test_deterministic_output(self):
        a = self.run_build()
        b = build(self.review, self.boundaries, self.root / "output2")
        self.assertEqual(a, b)
        self.assertEqual((self.root / "output" / "hand_drafts.json").read_bytes(),
                         (self.root / "output2" / "hand_drafts.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
