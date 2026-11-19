"""Regression tests for conservative proposal-to-review handoff."""
import unittest
from offline_proposal_review_ledger import build_review_ledger

SHA = "a" * 64

def sample(**changes):
    p = dict(table_id=1, start_observed_seconds=1.0, end_observed_seconds=3.0,
             sample_count=2, minimum_confidence=.8,
             board_states_observed=["flop", "turn"], hand_verified=False,
             boundaries_verified=False)
    p.update(changes)
    return p

def source(proposals=None):
    return dict(schema_version=1, proposals=[sample()] if proposals is None else proposals,
                analysis_verified=False, hand_boundaries_verified=False)

def run(src=None, **options):
    return build_review_ledger(source() if src is None else src,
                               video_sha256=options.get("sha", SHA),
                               duration_seconds=options.get("duration", 10))

class LedgerTests(unittest.TestCase):
    def test_pending_only(self):
        entry = run()["entries"][0]
        self.assertFalse(entry["clip_export_allowed"])
        self.assertFalse(entry["hand_verified"])
        self.assertIsNone(entry["loss_bb"])
        self.assertIsNone(entry["ev"])
    def test_deterministic(self):
        self.assertEqual(run(), run())
    def test_sorted(self):
        entries = run(source([sample(table_id=2, start_observed_seconds=5, end_observed_seconds=7), sample()]))["entries"]
        self.assertEqual([e["table_id"] for e in entries], [1, 2])
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError): run(source([sample(), sample()]))
    def test_verified_hand_rejected(self):
        with self.assertRaises(ValueError): run(source([sample(hand_verified=True)]))
    def test_verified_boundary_rejected(self):
        with self.assertRaises(ValueError): run(source([sample(boundaries_verified=True)]))
    def test_outside_duration_rejected(self):
        with self.assertRaises(ValueError): run(source([sample(end_observed_seconds=12)]))
    def test_nan_rejected(self):
        with self.assertRaises(ValueError): run(source([sample(minimum_confidence=float("nan"))]))
    def test_invalid_digest_rejected(self):
        with self.assertRaises(ValueError): run(sha="bad")
    def test_fifth_table_rejected(self):
        with self.assertRaises(ValueError): run(source([sample(table_id=5)]))

if __name__ == "__main__":
    unittest.main()
