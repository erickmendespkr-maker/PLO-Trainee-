"""Regression tests for independent reauditing of stored hypothetical EV reports."""
import unittest
from offline_bound_report_reaudit import reaudit_bound_report
from offline_mc_ev_integrated_audit import build_and_audit_conditional_report
from offline_ev_monetary_binding import bind_monetary_assumptions


class ReauditTests(unittest.TestCase):
    def setUp(self):
        self.samples = {'tight': [0.0, 0.5, 1.0], 'wide': [1.0, 0.0, 1.0]}
        scenarios = {name: {'seed': i, 'shares': shares,
                            'range_description': 'synthetic assumed range'}
                     for i, (name, shares) in enumerate(self.samples.items())}
        self.report = build_and_audit_conditional_report(
            video_sha256='a' * 64, hand_id='synthetic', reviewed=False,
            variant='PLO5', pot_before_call=100, call_cost=50,
            scenarios=scenarios)['report']

    def test_valid(self):
        result = reaudit_bound_report(self.report, self.samples)
        self.assertTrue(result['ev_arithmetic_verified'])
        self.assertFalse(result['video_observations_verified'])

    def test_external_digest(self):
        digest = self.report['monetary_binding']['sha256']
        self.assertTrue(reaudit_bound_report(self.report, self.samples,
            expected_binding_sha256=digest)['trusted_monetary_digest_checked'])

    def test_missing_binding(self):
        del self.report['monetary_binding']
        with self.assertRaises(ValueError):
            reaudit_bound_report(self.report, self.samples)

    def test_modified_money_without_digest(self):
        self.report['monetary_binding']['assumptions']['call_cost'] = 51
        with self.assertRaises(ValueError):
            reaudit_bound_report(self.report, self.samples)

    def test_coordinated_change_blocked_by_trusted_digest(self):
        trusted = self.report['monetary_binding']['sha256']
        self.report['monetary_binding'] = bind_monetary_assumptions(
            pot_before_call=100, call_cost=51)
        with self.assertRaises(ValueError):
            reaudit_bound_report(self.report, self.samples,
                                 expected_binding_sha256=trusted)

    def test_tampered_ev(self):
        self.report['calculation']['scenarios']['tight']['ev_estimate'] += 2
        with self.assertRaises(ValueError):
            reaudit_bound_report(self.report, self.samples)

    def test_tampered_shares(self):
        with self.assertRaises(ValueError):
            reaudit_bound_report(self.report, {'tight': [1.0], 'wide': self.samples['wide']})

    def test_rejects_legacy(self):
        self.report.pop('monetary_binding')
        with self.assertRaises(ValueError):
            reaudit_bound_report(self.report, self.samples)

    def test_invalid_external_digest(self):
        with self.assertRaises(ValueError):
            reaudit_bound_report(self.report, self.samples, expected_binding_sha256=123)

    def test_rejects_unsupported_source(self):
        self.report['monetary_binding']['source'] = 'video_verified'
        with self.assertRaises(ValueError):
            reaudit_bound_report(self.report, self.samples)


if __name__ == '__main__':
    unittest.main()
