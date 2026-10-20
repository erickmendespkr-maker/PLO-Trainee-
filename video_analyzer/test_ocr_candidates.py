import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ocr_candidates import parse_visible_amount, parse_visible_cards, candidate_from_ocr, scan_ocr_manifest


class OcrCandidateTests(unittest.TestCase):
    def test_unicode_suits_and_ten(self):
        self.assertEqual(parse_visible_cards('A♠ K♦ 10♥ 2♣ 3s', field='hero_cards'),
                         ['As', 'Kd', 'Th', '2c', '3s'])

    def test_six_cards(self):
        self.assertEqual(len(parse_visible_cards('As Kd Qc Jh Ts 9s', field='hero_cards')), 6)

    def test_board_three_cards(self):
        self.assertEqual(parse_visible_cards('As, Kd, Qc', field='board'), ['As', 'Kd', 'Qc'])

    def test_duplicate_cards_rejected(self):
        self.assertIsNone(parse_visible_cards('As As Qc', field='board'))

    def test_ocr_noise_rejected(self):
        self.assertIsNone(parse_visible_cards('Board As Kd Qc', field='board'))
        self.assertIsNone(parse_visible_cards('A? Kd Qc', field='board'))

    def test_wrong_card_count_rejected(self):
        self.assertIsNone(parse_visible_cards('As Kd Qc Jh', field='hero_cards'))

    def test_amount_formats(self):
        self.assertEqual(parse_visible_amount('Pot: R$ 1.234,50', field='pot'), 1234.5)
        self.assertEqual(parse_visible_amount('Bet: $12.50 BB', field='bet'), 12.5)
        self.assertEqual(parse_visible_amount('125', field='pot'), 125.)
        self.assertEqual(parse_visible_amount('1.234.567', field='pot'), 1234567.)

    def test_ambiguous_amount_rejected(self):
        self.assertIsNone(parse_visible_amount('1,234', field='pot'))
        self.assertIsNone(parse_visible_amount('Pot 1.2.3', field='pot'))
        self.assertIsNone(parse_visible_amount('Pot -25', field='pot'))
        self.assertIsNone(parse_visible_amount('Pot 1e3', field='pot'))

    def test_candidate_is_not_confirmed(self):
        result = {'text': 'As Kd Qc', 'mean_engine_confidence': .99, 'table_id': 1, 'timestamp': 10.}
        candidate = candidate_from_ocr(result, field='board')
        self.assertEqual(candidate['status'], 'candidate_unverified')
        self.assertEqual(candidate['parsed_candidate'], ['As', 'Kd', 'Qc'])

    def test_low_confidence_requires_review(self):
        result = {'text': '125', 'mean_engine_confidence': .4, 'table_id': 1, 'timestamp': 10.}
        self.assertEqual(candidate_from_ocr(result, field='pot')['status'], 'needs_manual_review')

    def test_invalid_confidence_threshold(self):
        with self.assertRaises(ValueError):
            candidate_from_ocr({'text': '12', 'mean_engine_confidence': 1, 'table_id': 1, 'timestamp': 1},
                               field='pot', min_engine_confidence=2)

    def test_manifest_scan_with_mock_ocr(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'tasks.json'
            dest = Path(folder) / 'out.json'
            source.write_text(json.dumps({'tasks': [{'field': 'pot', 'timestamp': 1.,
                       'region': {'table_id': 1, 'x': 0, 'y': 0, 'width': 100, 'height': 50}}]}))
            with patch('ocr_candidates.read_video_text', return_value={
                    'text': 'Pot: 50', 'mean_engine_confidence': .96,
                    'table_id': 1, 'timestamp': 1.}):
                result = scan_ocr_manifest('recorded.mp4', source, dest)
            self.assertEqual(result['candidates'][0]['parsed_candidate'], 50.)
            self.assertTrue(json.loads(dest.read_text())['requires_manual_review'])


if __name__ == '__main__':
    unittest.main()
