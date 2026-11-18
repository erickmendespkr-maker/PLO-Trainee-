import unittest
from offline_ev_review_bridge import build_review_queue


def record(shares=None, **overrides):
    base = dict(hand_id='h1', decision_id='d1', observed_action='call',
                review_status='CONDITIONAL_ANALYSIS_PERMITTED', evidence_confidence=.99,
                scenarios=[dict(range_label='tight', pot_before_call=10, call_cost=10,
                                hero_shares=([0.0]*2000 if shares is None else shares), seed=42)])
    base.update(overrides)
    return base


class BridgeTests(unittest.TestCase):
    def test_robust_loss(self):
        result = build_review_queue([record()])
        self.assertEqual(result['selected_for_review'][0]['status'], 'MODELLED_LOSS_CANDIDATE')
        self.assertFalse(result['clip_export_authorized'])
        self.assertFalse(result['range_uncertainty_quantified'])
    def test_robust_gain(self):
        result = build_review_queue([record(shares=[1.0]*2000)])
        self.assertEqual(result['candidates'][0]['status'], 'MODELLED_GAIN_CANDIDATE')
    def test_sampling_uncertainty(self):
        result = build_review_queue([record(shares=[0.5]*10)])
        self.assertEqual(result['candidates'][0]['status'], 'RANGE_OR_SAMPLING_SENSITIVE')
    def test_range_disagreement(self):
        r=record()
        r['scenarios'].append(dict(range_label='loose', pot_before_call=10, call_cost=10,
                                   hero_shares=[1.0]*2000, seed=43))
        result=build_review_queue([r])
        self.assertEqual(result['candidates'][0]['status'], 'RANGE_OR_SAMPLING_SENSITIVE')
        self.assertEqual(len(result['scenario_audits']), 2)
    def test_review_gate(self):
        result=build_review_queue([record(review_status='INSUFFICIENT_DATA')])
        self.assertEqual(result['candidates'][0]['status'], 'INSUFFICIENT_DATA')
    def test_confidence_gate(self):
        result=build_review_queue([record(evidence_confidence=.1)])
        self.assertFalse(result['selected_for_review'])
    def test_missing_seed(self):
        r=record(); del r['scenarios'][0]['seed']
        with self.assertRaises(ValueError): build_review_queue([r])
    def test_invalid_share(self):
        with self.assertRaises(ValueError): build_review_queue([record(shares=[1.2])])
    def test_unsupported_raise(self):
        with self.assertRaises(ValueError): build_review_queue([record(observed_action='raise')])
    def test_duplicate_ranges(self):
        r=record(); r['scenarios'].append(dict(r['scenarios'][0]))
        with self.assertRaises(ValueError): build_review_queue([r])
    def test_no_scenarios(self):
        result=build_review_queue([record(scenarios=[])])
        self.assertEqual(result['candidates'][0]['status'], 'INSUFFICIENT_DATA')
    def test_deterministic(self):
        self.assertEqual(build_review_queue([record()]), build_review_queue([record()]))

if __name__ == '__main__':
    unittest.main()
