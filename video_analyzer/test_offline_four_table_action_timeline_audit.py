"""Fast offline synthetic tests; no poker site, network, or video required."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_four_table_action_timeline_audit import build

H = 'a' * 64

def obs(idx, t, field, value):
    return {"reviewed_candidate_index": idx, "pts_seconds": t, "field": field,
            "value": value, "source_crop_sha256": H,
            "source_crop_path": f"tables/table_01_sample_{idx:02}.png",
            "review_decision": "correct"}


def hand():
    return {"hand_id": "hand1", "table_id": 1, "declared_game_type": "PLO5",
            "start_pts_seconds": 0.0, "end_pts_seconds": 15.0,
            "boundaries_human_declared_and_visually_checked": True,
            "observations": [
                obs(0, 1.0, "hero_cards", "As Ks Qs Js Ts"),
                obs(1, 2.0, "action", "call"),
                obs(2, 4.0, "board", "2c 3d 4h"),
                obs(3, 5.0, "pot", "120"),
                obs(4, 6.0, "action", "check"),
                obs(5, 8.0, "board", "2c 3d 4h 5s"),
                obs(6, 9.0, "action", "bet"),
                obs(7, 11.0, "board", "2c 3d 4h 5s 6c"),
                obs(8, 12.0, "action", "fold")],
            "missing_observed_fields": ["bet"],
            "changing_card_fields_needing_street_review": ["board"],
            "same_timestamp_card_collisions": [],
            "complete_hand_reconstructed": False,
            "ready_for_equity_or_ev": False,
            "status": "incomplete_hand_candidate_requires_action_history_and_ranges"}


def report():
    return {"schema_version": 1,
            "analysis_status": "human_declared_incomplete_hand_candidates",
            "recording_sha256": H,
            "source_reviewed_fields_sha256": H,
            "hand_windows_manifest_sha256": H,
            "source_region_samples_sha256": H,
            "hands": [hand()],
            "complete_hand_reconstructed": False,
            "ready_for_equity_or_ev": False,
            "automatic_clip_selection_authorized": False,
            "warning": "synthetic"}


class TimelineAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "hands.json"
        self.output = self.root / "audit.json"
        self.data = report()

    def write(self):
        self.source.write_text(json.dumps(self.data), encoding="utf-8")

    def run_audit(self, **kw):
        self.write()
        return build(self.source, self.output, **kw)

    def invalid(self):
        with self.assertRaises(ValueError):
            self.run_audit()
        self.assertFalse(self.output.exists())

    def test_street_candidates_and_no_math_promotion(self):
        r = self.run_audit()
        actions = r["hands"][0]["observed_action_labels"]
        self.assertEqual([a["street_candidate"] for a in actions],
                         [None, "flop_candidate", "turn_candidate", "river_candidate"])
        self.assertEqual([a["actor"] for a in actions], [None] * 4)
        self.assertFalse(r["ready_for_equity_or_ev"])
        self.assertFalse(r["automatic_clip_selection_authorized"])
        self.assertEqual(json.loads(self.output.read_text()), r)

    def test_board_streets_and_provenance(self):
        r = self.run_audit()
        self.assertEqual([b["street_candidate"] for b in r["hands"][0]["board_snapshots"]],
                         ["flop_candidate", "turn_candidate", "river_candidate"])
        self.assertEqual(r["source_hand_candidates_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_no_actions_flag(self):
        self.data["hands"][0]["observations"] = [o for o in hand()["observations"] if o["field"] != "action"]
        r = self.run_audit()
        self.assertIn("no_observed_actions", [i["code"] for i in r["hands"][0]["review_flags"]])

    def test_no_board_flag(self):
        self.data["hands"][0]["observations"] = [o for o in hand()["observations"] if o["field"] != "board"]
        r = self.run_audit()
        self.assertIn("no_observed_board", [i["code"] for i in r["hands"][0]["review_flags"]])

    def test_board_shrink_flag(self):
        self.data["hands"][0]["observations"][7]["value"] = "2c 3d 4h"
        r = self.run_audit()
        self.assertIn("board_shrank_within_hand", [i["code"] for i in r["hands"][0]["review_flags"]])

    def test_board_prefix_conflict(self):
        self.data["hands"][0]["observations"][5]["value"] = "2c 3d 7h 5s"
        r = self.run_audit()
        self.assertIn("board_changed_not_prefix", [i["code"] for i in r["hands"][0]["review_flags"]])

    def test_partial_board_flag(self):
        self.data["hands"][0]["observations"][2]["value"] = "2c 3d"
        r = self.run_audit()
        self.assertIn("partial_board_not_a_street", [i["code"] for i in r["hands"][0]["review_flags"]])

    def test_pot_decrease_flag(self):
        self.data["hands"][0]["observations"].append(obs(9, 13, "pot", "80"))
        r = self.run_audit()
        self.assertIn("pot_decreased_review_context", [i["code"] for i in r["hands"][0]["review_flags"]])

    def test_same_timestamp_board_action_is_ambiguous(self):
        self.data["hands"][0]["observations"][4]["pts_seconds"] = 4.0
        self.data["hands"][0]["observations"].sort(key=lambda x: (x["pts_seconds"], x["reviewed_candidate_index"]))
        r = self.run_audit()
        self.assertIsNone(r["hands"][0]["observed_action_labels"][1]["street_candidate"])

    def test_same_timestamp_card_collision(self):
        self.data["hands"][0]["observations"][0]["pts_seconds"] = 4.0
        self.data["hands"][0]["observations"][0]["value"] = "2c Ks Qs Js Ts"
        self.data["hands"][0]["observations"].sort(key=lambda x: (x["pts_seconds"], x["reviewed_candidate_index"]))
        r = self.run_audit()
        self.assertIn("visible_hero_board_card_collision", [i["code"] for i in r["hands"][0]["review_flags"]])

    def test_board_six_cards_rejected(self):
        self.data["hands"][0]["observations"][7]["value"] = "2c 3d 4h 5s 6c 7d"
        self.invalid()

    def test_hero_changes_flag(self):
        self.data["hands"][0]["observations"].append(obs(9, 13, "hero_cards", "Ac Kc Qc Jc Tc"))
        r = self.run_audit()
        self.assertIn("hero_cards_changed_within_hand", [i["code"] for i in r["hands"][0]["review_flags"]])

    def test_conflicting_board_blocks_street_candidate(self):
        self.data["hands"][0]["observations"][5]["value"] = "2c 3d 7h 5s"
        r = self.run_audit()
        self.assertIsNone(r["hands"][0]["observed_action_labels"][2]["street_candidate"])

    def test_wrong_hero_count(self):
        self.data["hands"][0]["observations"][0]["value"] = "As Ks Qs Js"
        self.invalid()

    def test_wrong_plo6_count(self):
        self.data["hands"][0]["declared_game_type"] = "PLO6"
        self.invalid()

    def test_duplicate_cards_rejected(self):
        self.data["hands"][0]["observations"][2]["value"] = "2c 2c 4h"
        self.invalid()

    def test_unknown_action_rejected(self):
        self.data["hands"][0]["observations"][1]["value"] = "muck"
        self.invalid()

    def test_negative_amount_rejected(self):
        self.data["hands"][0]["observations"][3]["value"] = "-20"
        self.invalid()

    def test_boolean_pts_rejected(self):
        self.data["hands"][0]["observations"][0]["pts_seconds"] = True
        self.invalid()

    def test_duplicate_source_index_rejected(self):
        self.data["hands"][0]["observations"][1]["reviewed_candidate_index"] = 0
        self.invalid()

    def test_unsorted_source_rejected(self):
        self.data["hands"][0]["observations"].reverse()
        self.invalid()

    def test_wrong_table_rejected(self):
        self.data["hands"][0]["table_id"] = 5
        self.invalid()

    def test_math_promotion_rejected(self):
        self.data["ready_for_equity_or_ev"] = True
        self.invalid()

    def test_extra_fields_rejected(self):
        self.data["hands"][0]["actions_reconstructed"] = True
        self.invalid()

    def test_symlink_input_rejected(self):
        self.write()
        other = self.root / "other.json"
        self.source.rename(other)
        self.source.symlink_to(other)
        with self.assertRaises(ValueError):
            build(self.source, self.output)

    def test_existing_output_preserved(self):
        self.output.write_text("keep")
        with self.assertRaises(ValueError):
            self.run_audit()
        self.assertEqual(self.output.read_text(), "keep")

    def test_recording_hash_mismatch(self):
        video = self.root / "recording.mp4"
        video.write_bytes(b"synthetic")
        with self.assertRaises(ValueError):
            self.run_audit(recording_path=video)

    def test_recording_hash_matches(self):
        video = self.root / "recording.mp4"
        video.write_bytes(b"synthetic")
        self.data["recording_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
        r = self.run_audit(recording_path=video)
        self.assertTrue(r["recording_hash_checked_in_this_run"])

    def test_duplicate_json_key_rejected(self):
        self.source.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            build(self.source, self.output)

    def test_two_tables_separate(self):
        second = copy.deepcopy(self.data["hands"][0])
        second["hand_id"] = "hand2"
        second["table_id"] = 2
        for i, o in enumerate(second["observations"]):
            o["reviewed_candidate_index"] = 12 + i
        self.data["hands"].append(second)
        r = self.run_audit()
        self.assertEqual([h["table_id"] for h in r["hands"]], [1, 2])

    def test_overlapping_same_table_rejected(self):
        second = copy.deepcopy(self.data["hands"][0])
        second["hand_id"] = "hand2"
        for i, o in enumerate(second["observations"]):
            o["reviewed_candidate_index"] = 12 + i
        self.data["hands"].append(second)
        self.invalid()

    def test_cross_hand_reuse_rejected(self):
        second = copy.deepcopy(self.data["hands"][0])
        second["hand_id"] = "hand2"
        second["table_id"] = 2
        self.data["hands"].append(second)
        self.invalid()

    def test_unreviewed_observation_rejected(self):
        self.data["hands"][0]["observations"][0]["review_decision"] = "reject"
        self.invalid()


if __name__ == "__main__":
    unittest.main()
