"""Synthetic checks of sample provenance and confidence bounds."""
import unittest
from .offline_mc_sample_audit import audit_showdown_samples


def fixture(shares=(0., 0.5, 1.), **updates):
    data = dict(shares=list(shares), iterations=len(shares), attempts=len(shares), seed=7,
                gto_solution=False, range_uncertainty_included=False,
                ocr_uncertainty_included=False)
    data.update(updates)
    return data


class SampleAuditTests(unittest.TestCase):
    def test_ties_count_as_half_pot(self):
        result = audit_showdown_samples(fixture())
        self.assertEqual(result['equity_mean'], 0.5)
        self.assertFalse(result['gto_solution'])

    def test_rejections_reported(self):
        self.assertEqual(audit_showdown_samples(fixture(attempts=6))['acceptance_rate'], 0.5)

    def test_interval_shrinks_with_more_samples(self):
        small = audit_showdown_samples(fixture([0., 1.] * 10))
        large = audit_showdown_samples(fixture([0., 1.] * 1000))
        self.assertLess(large['confidence_interval_95'][1] - large['confidence_interval_95'][0],
                        small['confidence_interval_95'][1] - small['confidence_interval_95'][0])

    def test_reject_mismatched_count(self):
        with self.assertRaises(ValueError):
            audit_showdown_samples(fixture(iterations=4))

    def test_reject_invalid_share(self):
        for value in (-0.1, 1.1, float('nan'), True, '0.5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit_showdown_samples(fixture([value]))

    def test_reject_bad_provenance(self):
        for field in ('gto_solution', 'range_uncertainty_included', 'ocr_uncertainty_included'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit_showdown_samples(fixture(**{field: True}))

    def test_reject_invalid_attempts(self):
        with self.assertRaises(ValueError):
            audit_showdown_samples(fixture(attempts=2))

    def test_reject_empty(self):
        with self.assertRaises(ValueError):
            audit_showdown_samples(fixture([]))


if __name__ == '__main__':
    unittest.main()
