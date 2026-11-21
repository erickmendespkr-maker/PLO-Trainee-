"""Regression tests for imported and legacy rebuy flags."""
import unittest

try:
    from .poker_cortes_evidence_gate import join_financial_evidence
except ImportError:
    from poker_cortes_evidence_gate import join_financial_evidence


class RebuyNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.base = {'start_seconds': 0, 'end_seconds': 10}

    def check_flag(self, data, expected):
        flags = join_financial_evidence(data, [])['flags']
        self.assertEqual('REBUY_REQUIRES_RECONCILIATION' in flags, expected)

    def test_importer_lowercase(self):
        self.check_flag(dict(self.base, source_rebuy_seen='sim'), True)

    def test_importer_whitespace(self):
        self.check_flag(dict(self.base, source_rebuy_seen=' SIM  '), True)

    def test_legacy_fallback_when_empty(self):
        self.check_flag(dict(self.base, source_rebuy_seen='', rebuy_visto='YES'), True)

    def test_boolean(self):
        self.check_flag(dict(self.base, source_rebuy_seen=True), True)

    def test_negative(self):
        self.check_flag(dict(self.base, source_rebuy_seen='NAO'), False)

    def test_unverified_even_when_rebuy(self):
        result = join_financial_evidence(dict(self.base, source_rebuy_seen='sim'), [])
        self.assertIsNone(result['confirmed_loss_bb'])
        self.assertFalse(result['strategy_analysis_authorized'])


if __name__ == '__main__':
    unittest.main()
