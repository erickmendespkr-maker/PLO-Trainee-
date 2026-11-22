import unittest
from offline_conditional_decision import analyze_reviewed_call
from offline_review_gate import REQUIRED


def hand():
    return dict(table_id='1', hand_id='h1', start_s=1, end_s=9,
                hero_cards=['As', 'Kh', 'Qd', 'Jc', 'Tc'],
                board=['2s', '3h', '4d', '5c', '6s'], action='call',
                pot_before=100, cost_to_call=50, verified_fields=list(REQUIRED))


def run(h=None):
    return analyze_reviewed_call(h if h is not None else hand(),
                                 video_duration_s=20, variant='PLO5',
                                 equity_low=0.3, equity_high=0.5, scenario_id='range-A')


class Integration(unittest.TestCase):
    def test_ready(self):
        r = run()
        self.assertEqual(r['status'], 'CONDITIONAL_EV_ONLY')
        self.assertAlmostEqual(r['conditional_ev']['ev_low_chips'], -5)
        self.assertAlmostEqual(r['conditional_ev']['ev_high_chips'], 25)

    def test_no_review(self):
        h = hand()
        h['verified_fields'] = []
        self.assertEqual(run(h)['status'], 'INSUFFICIENT_DATA')

    def test_noncall(self):
        h = hand()
        h['action'] = 'raise'
        self.assertEqual(run(h)['reason'], 'ONLY_REVIEWED_CALL_SUPPORTED')

    def test_nonriver(self):
        h = hand()
        h['board'] = h['board'][:4]
        self.assertEqual(run(h)['reason'], 'FUTURE_BETTING_NOT_MODELED')

    def test_invalid_equity(self):
        self.assertEqual(analyze_reviewed_call(hand(), video_duration_s=20,
                         variant='PLO5', equity_low=0.9, equity_high=0.1,
                         scenario_id='a')['reason'], 'INVALID_CONDITIONAL_EQUITY_OR_POT')

    def test_duplicate(self):
        h = hand()
        h['board'][0] = 'As'
        self.assertEqual(run(h)['status'], 'INSUFFICIENT_DATA')

    def test_scenario_missing(self):
        self.assertEqual(analyze_reviewed_call(hand(), video_duration_s=20,
                         variant='PLO5', equity_low=.3, equity_high=.5,
                         scenario_id=' ')['reason'], 'MISSING_RANGE_SCENARIO')

    def test_plo6(self):
        h = hand()
        h['hero_cards'].append('9h')
        self.assertEqual(analyze_reviewed_call(h, video_duration_s=20,
                         variant='PLO6', equity_low=.3, equity_high=.5,
                         scenario_id='a')['status'], 'CONDITIONAL_EV_ONLY')


if __name__ == '__main__':
    unittest.main()
