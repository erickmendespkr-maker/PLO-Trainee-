"""Property and boundary regressions for hypothetical call EV (no video claims)."""
import math
import unittest
from offline_ev_sensitivity import evaluate_call_scenarios


def scenarios(a=.2, b=.3):
    return [dict(range_id='tight', equity=a, equity_ci=[a, a], iterations=100, seed=0),
            dict(range_id='loose', equity=b, equity_ci=[b, b], iterations=100, seed=1)]


class ConditionalEVProperties(unittest.TestCase):
    def test_zero_equity_loses_call(self):
        r = evaluate_call_scenarios(150, 50, scenarios(0, 0))
        self.assertEqual([x['ev_call_bb'] for x in r['scenarios']], [-50, -50])

    def test_full_equity_wins_pre_call_pot(self):
        r = evaluate_call_scenarios(150, 50, scenarios(1, 1))
        self.assertEqual([x['ev_call_bb'] for x in r['scenarios']], [150, 150])

    def test_break_even_equity_zero_ev(self):
        r = evaluate_call_scenarios(150, 50, scenarios(.25, .25))
        self.assertTrue(all(abs(x['ev_call_bb']) < 1e-12 for x in r['scenarios']))

    def test_range_order_does_not_change_envelope(self):
        a = evaluate_call_scenarios(150, 50, scenarios(.2, .3))
        b = evaluate_call_scenarios(150, 50, list(reversed(scenarios(.2, .3))))
        self.assertEqual(a['ev_envelope_bb'], b['ev_envelope_bb'])
        self.assertEqual(a['range_sensitive'], b['range_sensitive'])

    def test_range_uncertainty_not_claimed(self):
        r = evaluate_call_scenarios(150, 50, scenarios())
        self.assertIs(r['range_uncertainty_included_in_ci'], False)
        self.assertIs(r['gto_solution'], False)
        self.assertIs(r['strategic_error_established'], False)
        self.assertIs(r['automatic_clip_selection_authorized'], False)

    def test_reject_duplicate_range_id(self):
        rows = scenarios()
        rows[1]['range_id'] = rows[0]['range_id']
        with self.assertRaises(ValueError):
            evaluate_call_scenarios(150, 50, rows)

    def test_reject_boolean_metadata(self):
        rows = scenarios()
        rows[0]['iterations'] = True
        with self.assertRaises(ValueError):
            evaluate_call_scenarios(150, 50, rows)

    def test_reject_infinite_pot(self):
        with self.assertRaises(ValueError):
            evaluate_call_scenarios(math.inf, 50, scenarios())


if __name__ == '__main__':
    unittest.main()
