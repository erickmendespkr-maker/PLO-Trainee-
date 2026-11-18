import unittest
from video_analyzer.offline_showdown_sample_audit import audit_showdown_samples as audit

class ShowdownSampleAuditTests(unittest.TestCase):
    def test_zero_and_full_shares(self):
        self.assertEqual(audit(100, 50, [0]*100)['call_ev'], -50)
        self.assertEqual(audit(100, 50, [1]*100)['call_ev'], 100)

    def test_split_and_rake(self):
        self.assertEqual(audit(100, 50, [0.5]*100, rake=10)['call_ev'], 20)

    def test_interval_contains_estimate(self):
        x = audit(100, 50, [0, 0.5, 1]*100, seed=42, range_label='synthetic')
        self.assertLessEqual(x['call_ev_95pct_hoeffding_interval'][0], x['call_ev'])
        self.assertGreaterEqual(x['call_ev_95pct_hoeffding_interval'][1], x['call_ev'])
        self.assertFalse(x['gto_claim_permitted'])
        self.assertFalse(x['range_uncertainty_quantified'])

    def test_more_samples_narrow_interval(self):
        a = audit(100, 50, [0, 1]*10)['call_ev_95pct_hoeffding_interval']
        b = audit(100, 50, [0, 1]*1000)['call_ev_95pct_hoeffding_interval']
        self.assertLess(b[1]-b[0], a[1]-a[0])

    def test_reject_invalid(self):
        for shares in ([], [float('nan')], [float('inf')], [-0.1], [1.1], [True]):
            with self.subTest(shares=shares), self.assertRaises(ValueError):
                audit(100, 50, shares)
        for kwargs in ({'rake': 151}, {'seed': True}, {'range_label': ''}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                audit(100, 50, [0.5], **kwargs)

if __name__ == '__main__':
    unittest.main()
