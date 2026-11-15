"""Regression tests for explicit EV assumptions in offline clip gate."""
import unittest
try:
    from .offline_clip_evidence_gate import classify_clip_evidence
except ImportError:
    from offline_clip_evidence_gate import classify_clip_evidence

BASE = dict(start_pts=1, end_pts=3, table_id=1, table_verified=True,
            hand_verified=True, hero_cards_verified=True, board_verified=True,
            action_verified=True, amounts_verified=True)

class GateAssumptionRegression(unittest.TestCase):
    def classify(self, **overrides):
        return classify_clip_evidence(dict(BASE, **overrides))

    def test_zero_rake_explicit(self):
        r = self.classify(ev_assumptions=dict(ranges='range A', rake=0, future_actions='none'))
        self.assertEqual(r['status'], 'APPROVED_CONDITIONAL')
        self.assertFalse(r['can_label_error'])

    def test_missing_rake(self):
        r = self.classify(ev_assumptions=dict(ranges='range A', future_actions='none'))
        self.assertEqual(r['status'], 'INSUFFICIENT_MODEL')

    def test_negative_rake(self):
        r = self.classify(ev_assumptions=dict(ranges='range A', rake=-1, future_actions='none'))
        self.assertEqual(r['status'], 'INSUFFICIENT_MODEL')

    def test_boolean_rake(self):
        r = self.classify(ev_assumptions=dict(ranges='range A', rake=True, future_actions='none'))
        self.assertEqual(r['status'], 'INSUFFICIENT_MODEL')

    def test_missing_visual_review(self):
        r = self.classify(hand_verified=False, ev_assumptions=dict(ranges='range A', rake=0, future_actions='none'))
        self.assertEqual(r['status'], 'REVIEW_REQUIRED')

    def test_invalid_timestamp(self):
        with self.assertRaises(ValueError):
            self.classify(end_pts=float('nan'))

    def test_invalid_table(self):
        with self.assertRaises(ValueError):
            self.classify(table_id=5)

    def test_empty_ranges(self):
        r = self.classify(ev_assumptions=dict(ranges='', rake=0, future_actions='none'))
        self.assertEqual(r['status'], 'INSUFFICIENT_MODEL')

if __name__ == '__main__':
    unittest.main()
