"""Regression tests for the conditional EV envelope provenance gate."""
import copy
import unittest

from offline_ev_sensitivity import evaluate_call_scenarios
from offline_ev_binding_adapter import adapt_sensitivity


def sample():
    return evaluate_call_scenarios(150, 50, [
        {"range_id": "tight", "equity": .20, "equity_ci": [.18, .22], "iterations": 10000, "seed": 1},
        {"range_id": "loose", "equity": .30, "equity_ci": [.28, .32], "iterations": 10000, "seed": 2},
    ])


class EnvelopeIntegrityTests(unittest.TestCase):
    def test_valid_envelope(self):
        source = sample()
        result = adapt_sensitivity(source, "synthetic_envelope")
        self.assertEqual(len(result["range_results"]), 2)

    def test_reject_modified_envelope(self):
        source = sample()
        source["ev_envelope_bb"][0] += 5
        with self.assertRaisesRegex(ValueError, "inconsistent EV envelope"):
            adapt_sensitivity(source, "synthetic_envelope")

    def test_reject_missing_or_nonfinite_envelope(self):
        for value in (None, [float("nan"), 10], [0], "0,10"):
            with self.subTest(value=value):
                source = sample()
                source["ev_envelope_bb"] = copy.deepcopy(value)
                with self.assertRaises(ValueError):
                    adapt_sensitivity(source, "synthetic_envelope")


if __name__ == "__main__":
    unittest.main()
