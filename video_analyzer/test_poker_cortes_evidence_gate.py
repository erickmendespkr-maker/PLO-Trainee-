import unittest
from poker_cortes_evidence_gate import join_financial_evidence


def sample(t, v):
    return {'time_seconds': t, 'stack_bb': v, 'source_frame': f'frame-{t}'}


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {'start_seconds': 10, 'end_seconds': 20, 'perda_bb': 300}

    def test_false_bust(self):
        result = join_financial_evidence(self.candidate, [sample(10, 320.5), sample(20, 0.5)])
        self.assertIn('LARGE_STACK_JUMP_RECHECK_OCR', result['flags'])
        self.assertIsNone(result['confirmed_loss_bb'])
        self.assertFalse(result['clip_loss_label_authorized'])

    def test_missing_samples(self):
        self.assertIn('INSUFFICIENT_STACK_SAMPLES', join_financial_evidence(self.candidate, [])['flags'])

    def test_rebuy(self):
        self.candidate['rebuy_visto'] = 'SIM'
        self.assertIn('REBUY_REQUIRES_RECONCILIATION', join_financial_evidence(self.candidate, [])['flags'])

    def test_outside_interval(self):
        with self.assertRaises(ValueError):
            join_financial_evidence(self.candidate, [sample(30, 100)])

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            join_financial_evidence(self.candidate, [sample(12, 100), sample(12, 90)])

    def test_invalid_number(self):
        with self.assertRaises(ValueError):
            join_financial_evidence(self.candidate, [sample(12, float('nan'))])

    def test_invalid_interval(self):
        self.candidate['end_seconds'] = 9
        with self.assertRaises(ValueError):
            join_financial_evidence(self.candidate, [])

    def test_ordering(self):
        r = join_financial_evidence(self.candidate, [sample(20, 99), sample(10, 100)])
        self.assertEqual([s['time_seconds'] for s in r['stack_samples']], [10, 20])

    def test_no_strategy_promotion(self):
        self.candidate['status'] = 'CONFIRMADO'
        r = join_financial_evidence(self.candidate, [sample(10, 100), sample(20, 0)])
        self.assertFalse(r['strategy_analysis_authorized'])
        self.assertFalse(r['verified_by_human'])


if __name__ == '__main__':
    unittest.main()
