import copy
import unittest
from offline_evidence_ledger import validate_observations
from offline_hand_review import apply_reviews


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.ledger = validate_observations([{'table_id': 1, 'pts': 1.0, 'field': 'pot', 'raw': '10?', 'confidence': 0.5, 'roi': [0, 0, 20, 20], 'frame_sha256': 'b' * 64}], 'a' * 64, 30)
        self.review = {'observation_index': 0, 'corrected_value': '10', 'reviewer': 'human', 'review_note': 'visually checked'}

    def test_valid_review(self):
        result = apply_reviews(self.ledger, [self.review])
        self.assertEqual(result['unreviewed_count'], 0)
        self.assertFalse(result['strategy_validated'])
        self.assertFalse(self.ledger['observations'][0]['verified_by_human'])

    def test_unreviewed(self):
        self.assertEqual(apply_reviews(self.ledger, [])['unreviewed_count'], 1)

    def test_tampered_ledger(self):
        altered = copy.deepcopy(self.ledger)
        altered['observations'][0]['raw'] = 'AA'
        with self.assertRaises(ValueError): apply_reviews(altered, [self.review])

    def test_duplicate_review(self):
        with self.assertRaises(ValueError): apply_reviews(self.ledger, [self.review, self.review])

    def test_bad_index(self):
        with self.assertRaises(ValueError): apply_reviews(self.ledger, [dict(self.review, observation_index=True)])

    def test_empty_reason(self):
        with self.assertRaises(ValueError): apply_reviews(self.ledger, [dict(self.review, review_note='')])

    def test_deterministic(self):
        self.assertEqual(apply_reviews(self.ledger, [self.review]), apply_reviews(self.ledger, [self.review]))


if __name__ == '__main__': unittest.main()
