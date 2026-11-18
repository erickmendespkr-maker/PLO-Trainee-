"""Independent analytic regression tests for the heads-up conditional call EV envelope.

These tests exercise the published module, not a duplicate implementation.
Run: python -m unittest discover -s video_analyzer -p 'test_offline_call_ev_analytic.py'
"""
import unittest

try:
    from video_analyzer.offline_call_ev_envelope import call_ev_envelope
except ModuleNotFoundError:
    from offline_call_ev_envelope import call_ev_envelope


class CallEVAnalyticTests(unittest.TestCase):
    def test_zero_equity_loses_call(self):
        out = call_ev_envelope(80, 20, [{"name": "zero", "equity_low": 0, "equity_high": 0}])
        self.assertAlmostEqual(out["ev_low"], -20)
        self.assertEqual(out["interpretation"], "fold_positive_all_scenarios")

    def test_certain_win_nets_existing_pot(self):
        out = call_ev_envelope(80, 20, [{"name": "nuts", "equity_low": 1, "equity_high": 1}])
        self.assertAlmostEqual(out["ev_high"], 80)

    def test_break_even_pot_odds(self):
        # q = C/(P+C) = 20/100.
        out = call_ev_envelope(80, 20, [{"name": "threshold", "equity_low": .2, "equity_high": .2}])
        self.assertAlmostEqual(out["ev_low"], 0)
        self.assertEqual(out["interpretation"], "range_sensitive_or_uncertain")

    def test_rake_changes_threshold(self):
        # Simplified fixed rake of 10 on winning outcomes: q=20/(80-10+20)=2/9.
        q = 2 / 9
        out = call_ev_envelope(80, 20, [{"name": "raked", "equity_low": q, "equity_high": q}], rake=10)
        self.assertAlmostEqual(out["ev_high"], 0)

    def test_range_envelope_is_not_statistical_confidence(self):
        out = call_ev_envelope(80, 20, [
            {"name": "tight", "equity_low": .1, "equity_high": .15},
            {"name": "loose", "equity_low": .35, "equity_high": .4},
        ])
        self.assertAlmostEqual(out["ev_low"], -10)
        self.assertAlmostEqual(out["ev_high"], 20)
        self.assertEqual(out["interpretation"], "range_sensitive_or_uncertain")
        self.assertEqual(out["status"], "HYPOTHETICAL_ONLY")
        self.assertFalse(out["gto_claim_permitted"])
        self.assertFalse(out["automatic_blunder_label_permitted"])

    def test_rejects_invalid_values(self):
        cases = [
            (80, 0, [{"name": "x", "equity_low": .5, "equity_high": .5}]),
            (80, 20, [{"name": "x", "equity_low": -.1, "equity_high": .5}]),
            (80, 20, [{"name": "x", "equity_low": .7, "equity_high": .6}]),
            (80, 20, [{"name": "x", "equity_low": True, "equity_high": .6}]),
            (80, 20, [{"name": "x", "equity_low": .5, "equity_high": .5},
                       {"name": "x", "equity_low": .5, "equity_high": .5}]),
        ]
        for pot, cost, scenarios in cases:
            with self.subTest(scenarios=scenarios):
                with self.assertRaises(ValueError):
                    call_ev_envelope(pot, cost, scenarios)


if __name__ == "__main__":
    unittest.main()
