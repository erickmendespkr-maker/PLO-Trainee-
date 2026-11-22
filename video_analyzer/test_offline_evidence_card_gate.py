"""Synthetic regression tests for the combined offline evidence/card gate."""
import copy
import unittest

try:
    from .offline_evidence_card_gate import assess_reviewed_hand
except ImportError:
    from offline_evidence_card_gate import assess_reviewed_hand


def reviewed(variant='PLO5'):
    cards = ['As', 'Kh', 'Qd', 'Jc', 'Tc', '9h'][:5 if variant == 'PLO5' else 6]
    values = dict(table_id='1', hand_start_s=1, hand_end_s=8,
                  hero_cards=cards, board=['2c', '3d', '4h'],
                  action='call', pot=100, amount=20)
    return {key: {'value': value, 'confidence': .99, 'human_verified': True}
            for key, value in values.items()}


class GateTests(unittest.TestCase):
    def test_valid_plo5(self):
        self.assertTrue(assess_reviewed_hand(reviewed(), 'PLO5')['conditional_analysis_allowed'])

    def test_valid_plo6(self):
        self.assertTrue(assess_reviewed_hand(reviewed('PLO6'), 'PLO6')['conditional_analysis_allowed'])

    def test_duplicate_card_blocks(self):
        h = reviewed()
        h['board']['value'][0] = 'As'
        r = assess_reviewed_hand(h, 'PLO5')
        self.assertFalse(r['conditional_analysis_allowed'])
        self.assertIn('duplicate_card', r['cards']['problems'])

    def test_unverified_blocks(self):
        h = reviewed()
        h['hero_cards']['human_verified'] = False
        self.assertFalse(assess_reviewed_hand(h, 'PLO5')['conditional_analysis_allowed'])

    def test_missing_cards_blocks_without_crashing(self):
        h = reviewed()
        del h['hero_cards']
        self.assertEqual(assess_reviewed_hand(h, 'PLO5')['status'], 'INSUFFICIENT_DATA')

    def test_unknown_card_blocks(self):
        h = reviewed()
        h['hero_cards']['value'][0] = '??'
        self.assertFalse(assess_reviewed_hand(h, 'PLO5')['conditional_analysis_allowed'])

    def test_unsupported_variant_blocks(self):
        self.assertFalse(assess_reviewed_hand(reviewed(), 'PLO4')['conditional_analysis_allowed'])

    def test_bad_interval_blocks(self):
        h = reviewed()
        h['hand_end_s']['value'] = 0
        self.assertFalse(assess_reviewed_hand(h, 'PLO5')['conditional_analysis_allowed'])

    def test_no_mutation_and_no_strategic_claim(self):
        h = reviewed()
        original = copy.deepcopy(h)
        r = assess_reviewed_hand(h, 'PLO5')
        self.assertEqual(h, original)
        self.assertFalse(r['strategic_verification'])
        self.assertTrue(r['ev_is_conditional'])
        self.assertFalse(r['hidden_cards_inferred'])

    def test_low_confidence_blocks(self):
        h = reviewed()
        h['pot']['confidence'] = .4
        self.assertFalse(assess_reviewed_hand(h, 'PLO5')['conditional_analysis_allowed'])


if __name__ == '__main__':
    unittest.main()
