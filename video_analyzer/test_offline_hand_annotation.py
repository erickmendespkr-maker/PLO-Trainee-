import copy
import json
import tempfile
import unittest
from pathlib import Path
from offline_hand_annotation import validate_annotations, write_annotations

DIGEST = 'a' * 64
BUNDLE = {'status': 'UNREVIEWED_EVIDENCE_REVIEW_BUNDLE', 'evidence_json_sha256': DIGEST}
HAND = {'table_id': 't1', 'hand_id': 'h1', 'variant': 'PLO5', 'start_seconds': 2, 'end_seconds': 12,
        'hero_cards': ['Ac', 'Kd', 'Qh', 'Js', 'Tc'], 'board_cards': ['2c', '3d', '4h'],
        'actions': [{'action': 'call', 'street': 'flop', 'seconds': 7, 'amount': 3}], 'human_confirmed': True}

class AnnotationTests(unittest.TestCase):
    def data(self):
        return {'evidence_json_sha256': DIGEST, 'hands': [copy.deepcopy(HAND)]}

    def test_valid(self):
        result = validate_annotations(BUNDLE, self.data())
        self.assertEqual(result['hands'][0]['status'], 'HUMAN_REVIEWED_CARDS_ONLY')
        self.assertFalse(result['equity_ev_verified'])

    def test_partial(self):
        data = self.data(); data['hands'][0]['hero_cards'] = ['Ac']
        self.assertEqual(validate_annotations(BUNDLE, data)['hands'][0]['status'], 'HUMAN_REVIEWED_PARTIAL')

    def test_four_tables(self):
        data = self.data(); data['hands'] = []
        for i in range(4):
            hand = copy.deepcopy(HAND); hand['table_id'] = str(i); data['hands'].append(hand)
        self.assertEqual(len(validate_annotations(BUNDLE, data)['hands']), 4)

    def test_mismatched_digest(self):
        data = self.data(); data['evidence_json_sha256'] = 'b'*64
        with self.assertRaises(ValueError): validate_annotations(BUNDLE, data)

    def test_duplicate_cards(self):
        data = self.data(); data['hands'][0]['board_cards'] = ['Ac']
        with self.assertRaises(ValueError): validate_annotations(BUNDLE, data)

    def test_duplicate_hand(self):
        data = self.data(); data['hands'].append(copy.deepcopy(HAND))
        with self.assertRaises(ValueError): validate_annotations(BUNDLE, data)

    def test_action_time(self):
        data = self.data(); data['hands'][0]['actions'][0]['seconds'] = 13
        with self.assertRaises(ValueError): validate_annotations(BUNDLE, data)

    def test_nan_amount(self):
        data = self.data(); data['hands'][0]['actions'][0]['amount'] = float('nan')
        with self.assertRaises(ValueError): validate_annotations(BUNDLE, data)

    def test_plo6(self):
        data = self.data(); data['hands'][0]['variant'] = 'PLO6'; data['hands'][0]['hero_cards'].append('9s')
        self.assertEqual(validate_annotations(BUNDLE, data)['hands'][0]['status'], 'HUMAN_REVIEWED_CARDS_ONLY')

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'bundle').write_text(json.dumps(BUNDLE)); (root/'annotations').write_text(json.dumps(self.data()))
            write_annotations(root/'bundle', root/'annotations', root/'out')
            with self.assertRaises(FileExistsError): write_annotations(root/'bundle', root/'annotations', root/'out')

if __name__ == '__main__': unittest.main()
