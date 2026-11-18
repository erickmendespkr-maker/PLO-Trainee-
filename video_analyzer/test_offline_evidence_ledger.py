import unittest
from offline_evidence_ledger import validate_observations

H = 'a' * 64
E = {'table_id': 1, 'pts': 1.5, 'field': 'pot', 'raw': '100', 'confidence': .7, 'roi': [0, 0, 10, 10], 'frame_sha256': H}

class EvidenceLedgerTests(unittest.TestCase):
    def test_valid_provisional(self):
        result = validate_observations([E], H, 100)
        self.assertIsNone(result['observations'][0]['value'])
        self.assertFalse(result['observations'][0]['verified_by_human'])
        self.assertFalse(result['strategy_validated'])
    def test_deterministic_order(self):
        second = dict(E, table_id=2)
        self.assertEqual(validate_observations([E, second], H, 100), validate_observations([second, E], H, 100))
    def test_duplicate(self):
        with self.assertRaises(ValueError): validate_observations([E, E], H, 100)
    def test_out_of_bounds(self):
        with self.assertRaises(ValueError): validate_observations([dict(E, pts=101)], H, 100)
    def test_invalid_confidence(self):
        with self.assertRaises(ValueError): validate_observations([dict(E, confidence=float('nan'))], H, 100)
    def test_invalid_roi(self):
        with self.assertRaises(ValueError): validate_observations([dict(E, roi=[0,0,0,5])], H, 100)
    def test_invalid_hash(self):
        with self.assertRaises(ValueError): validate_observations([E], 'x', 100)
    def test_no_forged_review(self):
        result = validate_observations([dict(E, verified_by_human=True, value=100)], H, 100)
        self.assertFalse(result['observations'][0]['verified_by_human'])
        self.assertIsNone(result['observations'][0]['value'])

if __name__ == '__main__': unittest.main()
