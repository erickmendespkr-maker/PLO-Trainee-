"""Security and epistemic integrity regressions for offline human annotations."""
import copy
import unittest
from offline_hand_annotation import validate_annotations

DIGEST = 'a' * 64
BUNDLE = {'status': 'UNREVIEWED_EVIDENCE_REVIEW_BUNDLE', 'evidence_json_sha256': DIGEST}
HAND = {'table_id': '1', 'hand_id': 'h1', 'variant': 'PLO5', 'start_seconds': 1,
        'end_seconds': 3, 'hero_cards': ['Ac', 'Kd', 'Qh', 'Js', 'Tc'], 'board_cards': []}

class HardeningTests(unittest.TestCase):
    def run_case(self, **changes):
        hand = dict(copy.deepcopy(HAND), **changes)
        return validate_annotations(copy.deepcopy(BUNDLE), {'evidence_json_sha256': DIGEST, 'hands': [hand]})

    def test_valid_reviewed_cards(self):
        result = self.run_case(human_confirmed=True)
        self.assertEqual(result['hands'][0]['status'], 'HUMAN_REVIEWED_CARDS_ONLY')
        self.assertFalse(result['equity_ev_verified'])

    def test_four_tables(self):
        hands = [dict(copy.deepcopy(HAND), table_id=str(i)) for i in range(1,5)]
        result = validate_annotations(BUNDLE, {'evidence_json_sha256': DIGEST, 'hands': hands})
        self.assertEqual(len(result['hands']), 4)

    def test_legacy_table_identifiers(self):
        for table in ['t1', '0', '01']:
            with self.subTest(table=table):
                self.assertEqual(self.run_case(table_id=table)['hands'][0]['table_id'], table)

    def test_reject_invalid_confirmation(self):
        for confirmation in [1, 'true', [], None]:
            with self.subTest(confirmation=confirmation), self.assertRaises(ValueError):
                self.run_case(human_confirmed=confirmation)

    def test_reject_unsupported_verification(self):
        for field in ('equity_ev_verified', 'gto_verified', 'cards_visually_verified', 'actions_visually_verified'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_case(**{field: True})

    def test_partial_remains_partial(self):
        result = self.run_case(hero_cards=['Ac'], human_confirmed=True)
        self.assertEqual(result['hands'][0]['status'], 'HUMAN_REVIEWED_PARTIAL')

if __name__ == '__main__':
    unittest.main()
