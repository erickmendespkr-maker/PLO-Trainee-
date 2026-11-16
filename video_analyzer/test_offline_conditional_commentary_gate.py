"""Synthetic regression cases for conditional commentary eligibility."""
import unittest
from offline_conditional_commentary_gate import assess_conditional_commentary


def hand():
    return dict(table_id='t1', hand_id='h1', video_sha256='a'*64,
                hero_cards=['As', 'Ks', 'Qs', 'Js', 'Ts'], board_cards=['2h', '3h', '4h'],
                action='call', pot=100, call_cost=20, range_sources=['tight', 'loose'],
                human_reviewed=True, variant='PLO5', start_pts=10, end_pts=30)


def comparison():
    return dict(status='CONDITIONAL_ONLY', cross_range_comparison_available=True,
                hand_error_verified=False, gto_solution=False, stable_action=None,
                range_sensitive_or_inconclusive=True)


class ConditionalCommentaryTests(unittest.TestCase):
    def test_valid_is_conditional_not_error(self):
        result = assess_conditional_commentary(hand(), comparison())
        self.assertEqual(result['status'], 'CONDITIONAL_EXPLANATION_ALLOWED')
        self.assertFalse(result['verified_error'])

    def test_human_review_required(self):
        h = hand(); h['human_reviewed'] = False
        self.assertIn('human_review_required', assess_conditional_commentary(h, comparison())['reasons'])

    def test_bad_timestamps(self):
        for value in (float('nan'), -1, 31, True):
            h = hand(); h['start_pts'] = value
            self.assertEqual(assess_conditional_commentary(h, comparison())['status'], 'REVIEW_ONLY')

    def test_duplicate_cards(self):
        h = hand(); h['board_cards'] = ['As']
        self.assertIn('duplicate_cards', assess_conditional_commentary(h, comparison())['reasons'])

    def test_one_range_rejected(self):
        h = hand(); h['range_sources'] = ['tight']
        self.assertIn('invalid_range_sources', assess_conditional_commentary(h, comparison())['reasons'])

    def test_gto_claim_rejected(self):
        c = comparison(); c['gto_solution'] = True
        self.assertIn('unsupported_strategy_claim', assess_conditional_commentary(hand(), c)['reasons'])

    def test_missing_comparison(self):
        self.assertIn('scenario_comparison_required', assess_conditional_commentary(hand(), {})['reasons'])

    def test_plo6(self):
        h = hand(); h['variant'] = 'PLO6'; h['hero_cards'].append('9s')
        self.assertEqual(assess_conditional_commentary(h, comparison())['status'],
                         'CONDITIONAL_EXPLANATION_ALLOWED')


if __name__ == '__main__':
    unittest.main()
