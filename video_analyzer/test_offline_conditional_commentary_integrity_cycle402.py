"""Fail-closed regressions for conditional commentary evidence."""
import unittest
from test_offline_conditional_commentary_gate import hand, comparison
from offline_conditional_commentary_gate import assess_conditional_commentary


class EvidenceIntegrityTests(unittest.TestCase):
    def test_invalid_card_notation(self):
        for card in ('1s', '10h', 'AX', '??', 'As ', '', 17, None):
            with self.subTest(card=card):
                h = hand()
                h['hero_cards'][0] = card
                result = assess_conditional_commentary(h, comparison())
                self.assertEqual(result['status'], 'REVIEW_ONLY')
                self.assertIn('invalid_card_notation', result['reasons'])

    def test_duplicate_range_labels_after_whitespace_normalization(self):
        h = hand()
        h['range_sources'] = ['tight', ' tight ']
        self.assertIn('invalid_range_sources',
                      assess_conditional_commentary(h, comparison())['reasons'])

    def test_unsupported_action(self):
        for action in ('all-in?', 'unknown', 2, {}, None):
            with self.subTest(action=action):
                h = hand()
                h['action'] = action
                self.assertIn('invalid_action',
                              assess_conditional_commentary(h, comparison())['reasons'])

    def test_valid_reviewed_hand_remains_conditional(self):
        self.assertEqual(assess_conditional_commentary(hand(), comparison())['status'],
                         'CONDITIONAL_EXPLANATION_ALLOWED')


if __name__ == '__main__':
    unittest.main()
