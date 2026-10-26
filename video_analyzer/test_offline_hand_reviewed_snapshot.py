"""Synthetic-only tests for immutable candidate snapshot derived from two reviews."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_hand_correction_overlay import build_overlay, digest
from offline_hand_independent_review import build_review
from offline_hand_reviewed_snapshot import build_snapshot, export_snapshot
from test_offline_hand_correction_overlay import fixture


def case():
    draft, submission = fixture()
    draft["hands"][0]["human_entry"].update({
        "source_pts_checked_by_human": False, "reviewer_attestation": False,
    })
    submission["source_draft_sha256"] = digest(draft)
    overlay = build_overlay(draft, submission)
    decisions = {"schema_version": 1, "job_id": draft["job_id"],
                 "source_draft_sha256": digest(draft), "overlay_sha256": digest(overlay),
                 "reviewer_label": "independent reviewer",
                 "decisions": [{"correction_sha256": digest(overlay["corrections"][0]),
                                "decision": "accept", "reason": "Checked manually"}]}
    review = build_review(draft, overlay, decisions)
    return draft, overlay, review


def add_proposal(draft, overlay, review, field, proposed, decision="accept"):
    old = draft["hands"][0]["human_entry"][field]
    sub = {"schema_version": 1, "job_id": draft["job_id"],
           "source_draft_sha256": digest(draft), "reviewer_label": "analista",
           "corrections": [{"table_id": 1, "hand_label_human_assigned": "h1",
                            "field": field, "expected_value_sha256": digest(old),
                            "proposed_value": proposed, "reason": "Manual", "confidence_subjective": .8}]}
    new_row = build_overlay(draft, sub)["corrections"][0]
    overlay["corrections"].append(new_row)
    overlay["corrections"].sort(key=lambda x: (x["table_id"], x["hand_label_human_assigned"], x["field"]))
    overlay["counts"]["pending"] += 1
    subreview = {"schema_version": 1, "job_id": draft["job_id"],
                 "source_draft_sha256": digest(draft), "overlay_sha256": digest(overlay),
                 "reviewer_label": review["reviewer_label"],
                 "decisions": review["decisions"] + [{"correction_sha256": digest(new_row),
                                    "decision": decision, "reason": "Checked manually"}]}
    return build_review(draft, overlay, subreview)


class ReviewedSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.draft, self.overlay, self.review = case()

    def build(self):
        return build_snapshot(self.draft, self.overlay, self.review)

    def test_accept_applies_to_derived_view_only(self):
        original = copy.deepcopy(self.draft)
        snap = self.build()
        self.assertEqual(snap["hands"][0]["human_entry_candidate"]["hero_cards"],
                         ["As", "Kh", "Qd", "Jc", "Tc"])
        self.assertIsNone(self.draft["hands"][0]["human_entry"]["hero_cards"])
        self.assertEqual(self.draft, original)

    def test_all_gates_stay_false(self):
        snap = self.build()
        for key in ("source_pts_verified", "hand_reconstruction_verified",
                    "ready_for_equity_or_ev", "automatic_clip_selection_authorized"):
            self.assertIs(snap[key], False)
            self.assertIs(snap["hands"][0][key], False)
        self.assertEqual(snap["counts"]["math_ready"], 0)

    def test_provenance_hashes(self):
        snap = self.build()
        row = snap["hands"][0]
        proof = row["applied_corrections"][0]
        self.assertEqual(proof["original_value_sha256"], digest(None))
        self.assertEqual(proof["candidate_value_sha256"], digest(row["human_entry_candidate"]["hero_cards"]))
        self.assertEqual(snap["source_review_sha256"], digest(self.review))
        self.assertEqual(row["original_human_entry_sha256"], digest(self.draft["hands"][0]["human_entry"]))

    def test_reject_keeps_original(self):
        self.review = build_review(self.draft, self.overlay, {
            "schema_version": 1, "job_id": self.draft["job_id"],
            "source_draft_sha256": digest(self.draft), "overlay_sha256": digest(self.overlay),
            "reviewer_label": "independent reviewer",
            "decisions": [{"correction_sha256": digest(self.overlay["corrections"][0]),
                           "decision": "reject", "reason": "Unclear image"}]})
        snap = self.build()
        self.assertIsNone(snap["hands"][0]["human_entry_candidate"]["hero_cards"])
        self.assertEqual(snap["counts"]["rejected_unapplied"], 1)
        self.assertEqual(len(snap["rejected_corrections"]), 1)

    def test_mixed_accept_reject(self):
        self.review = add_proposal(self.draft, self.overlay, self.review, "notes", "Wrong bet size", "reject")
        snap = self.build()
        self.assertEqual(snap["counts"]["accepted_applied"], 1)
        self.assertEqual(snap["counts"]["rejected_unapplied"], 1)
        self.assertEqual(snap["hands"][0]["human_entry_candidate"]["notes"], "")

    def test_tampered_review_counts(self):
        self.review["counts"]["accepted"] = 999
        with self.assertRaisesRegex(ValueError, "Tampered"):
            self.build()

    def test_tampered_review_gate(self):
        self.review["ready_for_equity_or_ev"] = True
        with self.assertRaisesRegex(ValueError, "Tampered"):
            self.build()

    def test_review_reason_is_not_cryptographically_authenticated(self):
        before = self.build()["source_review_sha256"]
        self.review["decisions"][0]["reason"] = "Altered"
        after = self.build()
        self.assertNotEqual(after["source_review_sha256"], before)
        self.assertEqual(after["hands"][0]["applied_corrections"][0]["review_reason"], "Altered")

    def test_wrong_review_hash(self):
        self.review["overlay_sha256"] = "0" * 64
        with self.assertRaises(ValueError): self.build()

    def test_wrong_overlay(self):
        self.overlay["corrections"][0]["proposed_value"] = ["As", "Ks", "Qs", "Js", "Ts"]
        with self.assertRaises(ValueError): self.build()

    def test_changed_draft(self):
        self.draft["hands"][0]["human_entry"]["notes"] = "Changed"
        with self.assertRaises(ValueError): self.build()

    def test_bad_original_action_amount(self):
        self.draft["hands"][0]["human_entry"]["actions"] = [{
            "street": "preflop", "actor": "hero", "action": "call",
            "amount": 0, "source_pts_seconds": 1}]
        self._rebind()
        with self.assertRaisesRegex(ValueError, "action amount"):
            self.build()

    def test_original_invalid_duplicate_cards(self):
        self.draft["hands"][0]["human_entry"]["board_by_street"] = {
            "flop": ["As", "2h", "3c"], "turn": None, "river": None}
        with self.assertRaisesRegex(ValueError, "Conflicting hero and community cards"):
            self._rebind()

    def test_original_partial_pts_rejected(self):
        self.draft["hands"][0]["human_entry"]["source_pts_start_seconds"] = 1
        self._rebind()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.build()

    def test_original_extra_field_rejected(self):
        self.draft["hands"][0]["human_entry"]["approve_math"] = True
        self._rebind()
        with self.assertRaisesRegex(ValueError, "Unexpected candidate"):
            self.build()

    def test_multiple_accepted_fields(self):
        self.review = add_proposal(self.draft, self.overlay, self.review, "notes", "Observed on video")
        snap = self.build()
        self.assertEqual(snap["counts"]["accepted_applied"], 2)
        self.assertEqual(snap["hands"][0]["human_entry_candidate"]["notes"], "Observed on video")

    def test_legacy_draft_without_attestation_is_supported_without_inference(self):
        self.draft["hands"][0]["human_entry"].pop("source_pts_checked_by_human")
        self.draft["hands"][0]["human_entry"].pop("reviewer_attestation")
        self._rebind()
        snap = self.build()
        row = snap["hands"][0]
        self.assertFalse(row["human_attestation_fields_present"])
        self.assertNotIn("reviewer_attestation", row["human_entry_candidate"])
        self.assertFalse(row["ready_for_equity_or_ev"])

    def test_partial_attestation_schema_rejected(self):
        self.draft["hands"][0]["human_entry"].pop("reviewer_attestation")
        self._rebind()
        with self.assertRaisesRegex(ValueError, "Unexpected candidate"):
            self.build()

    def test_original_incomplete_still_unverified(self):
        snap = self.build()
        self.assertIsNone(snap["hands"][0]["human_entry_candidate"]["source_pts_start_seconds"])
        self.assertFalse(snap["hands"][0]["hand_reconstruction_verified"])

    def test_export_writes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = [root / n for n in ("draft.json", "overlay.json", "review.json", "snapshot.json")]
            for path, data in zip(files, (self.draft, self.overlay, self.review)):
                path.write_text(json.dumps(data))
            result = export_snapshot(*files)
            self.assertEqual(result["counts"]["accepted_applied"], 1)
            self.assertEqual(json.loads(files[-1].read_text())["status"], result["status"])
            with self.assertRaisesRegex(ValueError, "Unsafe output"):
                export_snapshot(*files)

    def test_export_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = [root / n for n in ("draft.json", "overlay.json", "review.json", "snapshot.json")]
            for path, data in zip(files, (self.draft, self.overlay, self.review)):
                path.write_text(json.dumps(data))
            link = root / "link.json"
            link.symlink_to(files[0])
            with self.assertRaises(ValueError): export_snapshot(link, *files[1:])

    def test_export_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = [root / n for n in ("draft.json", "overlay.json", "review.json")]
            for path, data in zip(files, (self.draft, self.overlay, self.review)):
                path.write_text(json.dumps(data))
            with self.assertRaises(ValueError): export_snapshot(*files, files[0])

    def _rebind(self):
        # Rebuild a valid review chain around the altered source draft, so the
        # test exercises candidate validation rather than stale-hash rejection.
        sub = {"schema_version": 1, "job_id": self.draft["job_id"],
               "source_draft_sha256": digest(self.draft), "reviewer_label": "analista",
               "corrections": [{"table_id": 1, "hand_label_human_assigned": "h1",
                                "field": "hero_cards", "expected_value_sha256": digest(None),
                                "proposed_value": ["As", "Kh", "Qd", "Jc", "Tc"],
                                "reason": "Manual", "confidence_subjective": .8}]}
        self.overlay = build_overlay(self.draft, sub)
        decisions = {"schema_version": 1, "job_id": self.draft["job_id"],
                     "source_draft_sha256": digest(self.draft), "overlay_sha256": digest(self.overlay),
                     "reviewer_label": "independent reviewer",
                     "decisions": [{"correction_sha256": digest(self.overlay["corrections"][0]),
                                    "decision": "accept", "reason": "Checked"}]}
        self.review = build_review(self.draft, self.overlay, decisions)


if __name__ == "__main__":
    unittest.main()
