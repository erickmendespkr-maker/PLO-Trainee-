"""Synthetic regressions for the conservative offline evidence gate."""
import unittest

try:
    from .offline_hand_evidence_gate import assess_hand_evidence, REQUIRED
except ImportError:
    from offline_hand_evidence_gate import assess_hand_evidence, REQUIRED


def reviewed():
    values = dict(table_id='1', hand_start_s=1., hand_end_s=8., hero_cards=['As','Kd','Qc','Jh','Ts'], board=['2c','3c','4c'], action='call', pot=100., amount=20.)
    return {key: {'value': values[key], 'confidence': 0.99, 'human_verified': True} for key in REQUIRED}


class EvidenceGateTests(unittest.TestCase):
    def test_reviewed_is_not_strategic_proof(self):
        result = assess_hand_evidence(reviewed())
        self.assertEqual(result['status'], 'EVIDENCE_REVIEWED')
        self.assertFalse(result['strategic_verification'])

    def test_missing_cards(self):
        hand = reviewed(); del hand['hero_cards']
        self.assertIn('hero_cards', assess_hand_evidence(hand)['missing_fields'])

    def test_ocr_only_does_not_pass(self):
        hand = reviewed(); hand['pot']['human_verified'] = False
        self.assertEqual(assess_hand_evidence(hand)['status'], 'INSUFFICIENT_DATA')

    def test_low_confidence(self):
        hand = reviewed(); hand['action']['confidence'] = 0.3
        self.assertIn('action', assess_hand_evidence(hand)['unverified_fields'])

    def test_bad_interval(self):
        hand = reviewed(); hand['hand_end_s']['value'] = 1.
        self.assertIn('hand_interval', assess_hand_evidence(hand)['invalid_fields'])

    def test_negative_pot(self):
        hand = reviewed(); hand['pot']['value'] = -5
        self.assertIn('pot', assess_hand_evidence(hand)['invalid_fields'])

    def test_nan_confidence(self):
        hand = reviewed(); hand['pot']['confidence'] = float('nan')
        self.assertIn('pot', assess_hand_evidence(hand)['invalid_fields'])

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError): assess_hand_evidence(reviewed(), minimum_confidence=True)


if __name__ == '__main__':
    unittest.main()
