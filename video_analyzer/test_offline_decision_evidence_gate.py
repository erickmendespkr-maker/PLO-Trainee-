"""Synthetic regression tests for conservative offline evidence gating."""
import copy
import unittest
from offline_decision_evidence_gate import evaluate

SHA = 'a' * 64

def fixture():
    values = dict(table_id=2, hand_id='hand-1', start_seconds=2,
                  end_seconds=12, hero_cards=['As', 'Ks', 'Qs', 'Js', 'Ts'],
                  board_cards=['2c', '3d', '4h'], action='call',
                  pot=100, call_cost=50)
    return {key: {'value': value, 'confidence': 0.9, 'human_verified': True}
            for key, value in values.items()}

class EvidenceGateTests(unittest.TestCase):
    def test_visual_only(self):
        result = evaluate(fixture(), duration=60, video_sha256=SHA)
        self.assertTrue(result['clip_export_allowed'])
        self.assertFalse(result['conditional_analysis_attachment_allowed'])
    def test_audited(self):
        result = evaluate(fixture(), duration=60, video_sha256=SHA,
                          audit={'ev_arithmetic_verified': True, 'sample_hashes_verified': 2})
        self.assertTrue(result['conditional_analysis_attachment_allowed'])
        self.assertFalse(result['strategic_verdict_allowed'])
    def test_unreviewed_pot(self):
        data = fixture()
        data['pot']['human_verified'] = False
        self.assertEqual(evaluate(data, duration=60, video_sha256=SHA)['status'], 'REVIEW_REQUIRED')
    def test_missing_action(self):
        data = fixture()
        del data['action']
        self.assertIn('action', evaluate(data, duration=60, video_sha256=SHA)['missing_fields'])
    def test_invalid_timestamp(self):
        data = fixture()
        data['end_seconds']['value'] = 61
        with self.assertRaises(ValueError):
            evaluate(data, duration=60, video_sha256=SHA)
    def test_nonfinite_confidence(self):
        data = fixture()
        data['pot']['confidence'] = float('nan')
        with self.assertRaises(ValueError):
            evaluate(data, duration=60, video_sha256=SHA)
    def test_stable_hash(self):
        data = fixture()
        self.assertEqual(evaluate(data, duration=60, video_sha256=SHA)['evidence_sha256'],
                         evaluate(copy.deepcopy(data), duration=60, video_sha256=SHA)['evidence_sha256'])
    def test_changed_hash(self):
        data = fixture()
        changed = copy.deepcopy(data)
        changed['pot']['value'] = 101
        self.assertNotEqual(evaluate(data, duration=60, video_sha256=SHA)['evidence_sha256'],
                            evaluate(changed, duration=60, video_sha256=SHA)['evidence_sha256'])
    def test_math_cannot_override_unreviewed_cards(self):
        data = fixture()
        data['hero_cards']['human_verified'] = False
        result = evaluate(data, duration=60, video_sha256=SHA,
                          audit={'ev_arithmetic_verified': True, 'sample_hashes_verified': 1})
        self.assertFalse(result['conditional_analysis_attachment_allowed'])
    def test_invalid_table(self):
        data = fixture()
        data['table_id']['value'] = 5
        with self.assertRaises(ValueError):
            evaluate(data, duration=60, video_sha256=SHA)

if __name__ == '__main__':
    unittest.main()
