import unittest
from video_analyzer.offline_reviewed_call_report import build_reviewed_call_report


def evidence(**changes):
    d = dict(video_sha256="a"*64, hand_id="h-01", table_id=2,
             start_pts=10.0, end_pts=31.0, hole_cards_verified=True,
             board_verified=True, action_verified=True, pot_verified=True,
             call_cost_verified=True, reviewed_by_human=True)
    d.update(changes)
    return d


def ranges():
    return [{"name":"tight", "range_assumption":"hypothetical tight range",
             "equity":0.4, "equity_ci":[0.35,0.45]}]


class ReviewedCallReportTests(unittest.TestCase):
    def test_conditional_report(self):
        r = build_reviewed_call_report(evidence(), 100, 50, ranges())
        self.assertEqual(r["status"], "CONDITIONAL_MODEL_ONLY")
        self.assertAlmostEqual(r["analysis"]["scenarios"][0]["call_ev_chips"], 10)
        self.assertFalse(r["gto_solution"])
        self.assertEqual(r["strategic_verdict"], "NOT_ESTABLISHED")

    def test_missing_field_blocks(self):
        d = evidence(); del d["action_verified"]
        r = build_reviewed_call_report(d, 100, 50, ranges())
        self.assertEqual(r["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(r["analysis"])

    def test_unreviewed_blocks(self):
        r = build_reviewed_call_report(evidence(reviewed_by_human=False), 100, 50, ranges())
        self.assertIn("reviewed_by_human", r["missing_fields"])
        self.assertIsNone(r["analysis"])

    def test_nonboolean_verification_blocks(self):
        r = build_reviewed_call_report(evidence(pot_verified=1), 100, 50, ranges())
        self.assertEqual(r["status"], "INSUFFICIENT_DATA")

    def test_invalid_table_rejected(self):
        with self.assertRaises(ValueError):
            build_reviewed_call_report(evidence(table_id=5), 100, 50, ranges())

    def test_invalid_pts_rejected(self):
        with self.assertRaises(ValueError):
            build_reviewed_call_report(evidence(end_pts=10), 100, 50, ranges())

    def test_bad_hash_rejected(self):
        with self.assertRaises(ValueError):
            build_reviewed_call_report(evidence(video_sha256="z"*64), 100, 50, ranges())

    def test_invalid_equity_rejected_after_review(self):
        with self.assertRaises(ValueError):
            build_reviewed_call_report(evidence(), 100, 50,
                [{"name":"x", "range_assumption":"hypothesis", "equity":1.5,
                  "equity_ci":[0,1]}])


if __name__ == "__main__":
    unittest.main()
