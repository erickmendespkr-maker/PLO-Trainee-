import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from offline_math_input_gate import build, load, run


class GateTests(unittest.TestCase):
    def setUp(self):
        self.review = {'schema_version': 1, 'status': 'offline_human_reviewed_evidence_not_math_authorized',
                       'automatic_ocr_math_authorization': False, 'confidence_calibrated': False,
                       'variant': 'PLO5', 'hands': [
                           {'table_id': 'table_1', 'hand_id': 'hand_1',
                            'card_evidence_consistent': True, 'review_flags': [],
                            'automatic_math_authorization': False, 'events': [
                                {'kind': 'hero_cards', 'decision': 'confirm', 'reviewed_value': ['As','Kd','Qc','Jh','Ts']},
                                {'kind': 'board', 'decision': 'correct', 'reviewed_value': ['2c','3d','4h']},
                                {'kind': 'board', 'decision': 'confirm', 'reviewed_value': ['2c','3d','4h','5s']}]}
                       ]}
        self.assumptions = {'schema_version': 1, 'table_id': 'table_1', 'hand_id': 'hand_1',
                            'source_review_sha256': 'a'*64, 'reviewer_attestation': True,
                            'range_source': 'Manual hypothetical range, not OCR',
                            'villain_combos': [{'cards': ['6c','7d','8h','9s','Tc'], 'weight': 1.0}],
                            'pot_before_call': 100, 'to_call': 20, 'seed': 1234,
                            'trials': 1000, 'model': 'heads_up_call_all_in_no_future_betting_no_rake'}

    def build(self):
        return build(self.review, self.assumptions, 'a'*64, 'b'*64)

    def test_valid(self):
        r = self.build()
        self.assertEqual(r['status'], 'reviewed_math_candidate_manual_ranges_not_computed')
        self.assertEqual(len(r['board']), 4)
        self.assertFalse(r['automatic_ocr_math_authorization'])

    def test_plo6(self):
        self.review['variant'] = 'PLO6'
        self.review['hands'][0]['events'][0]['reviewed_value'].append('9c')
        self.assumptions['villain_combos'][0]['cards'].append('Jc')
        self.assertEqual(self.build()['variant'], 'PLO6')

    def test_rejected_card(self):
        self.review['hands'][0]['events'][0]['decision'] = 'reject'
        with self.assertRaises(ValueError): self.build()

    def test_missing_hero(self):
        self.review['hands'][0]['events'] = self.review['hands'][0]['events'][1:]
        with self.assertRaises(ValueError): self.build()

    def test_overlap(self):
        self.assumptions['villain_combos'][0]['cards'][0] = 'As'
        with self.assertRaises(ValueError): self.build()

    def test_duplicated_range(self):
        self.assumptions['villain_combos'] *= 2
        with self.assertRaises(ValueError): self.build()

    def test_missing_attestation(self):
        self.assumptions['reviewer_attestation'] = False
        with self.assertRaises(ValueError): self.build()

    def test_bad_sha(self):
        self.assumptions['source_review_sha256'] = 'b'*64
        with self.assertRaises(ValueError): self.build()

    def test_unsupported_model(self):
        self.assumptions['model'] = 'multiway_raise'
        with self.assertRaises(ValueError): self.build()

    def test_bad_street_progression(self):
        self.review['hands'][0]['events'][-1]['reviewed_value'] = ['2c','3d','6h','5s']
        with self.assertRaises(ValueError): self.build()

    def test_conflict_flag(self):
        self.review['hands'][0]['review_flags'] = ['hero_board_overlap']
        with self.assertRaises(ValueError): self.build()

    def test_nan(self):
        self.assumptions['pot_before_call'] = float('nan')
        with self.assertRaises(ValueError): self.build()

    def test_bool_numeric(self):
        self.assumptions['to_call'] = True
        with self.assertRaises(ValueError): self.build()

    def test_no_implicit_ev(self):
        self.assertNotIn('equity', self.build())
        self.assertNotIn('ev', self.build())

    def test_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            review = p/'review.json'
            review.write_text(json.dumps(self.review))
            self.assumptions['source_review_sha256'] = hashlib.sha256(review.read_bytes()).hexdigest()
            assumptions = p/'assumptions.json'
            assumptions.write_text(json.dumps(self.assumptions))
            result = run(review, assumptions, p/'output.json')
            self.assertEqual(load(p/'output.json'), result)
            with self.assertRaises(ValueError): run(review, assumptions, p/'output.json')

    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'duplicate.json'
            p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError): load(p)

    def test_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'nan.json'
            p.write_text('{"a":NaN}')
            with self.assertRaises(ValueError): load(p)


if __name__ == '__main__': unittest.main()
