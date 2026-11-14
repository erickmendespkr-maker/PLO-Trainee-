"""Synthetic tests for offline Monte Carlo -> conditional EV bridge."""
import unittest
from unittest.mock import patch
from .offline_omaha_call_bridge import analyze_hypothetical_call


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.kw = dict(hero=["As", "Ks", "Qs", "Js", "Ts"],
                       board=["2c", "3d", "4h", "5c", "6d"],
                       range_scenarios=[
                           {"name": "tight", "opponent_range": [["7c", "8c", "9c", "Tc", "Jc"]]},
                           {"name": "loose", "opponent_range": [["7d", "8d", "9d", "Td", "Jd"]]}],
                       pot_before_call=100, call_cost=50, iterations=5, seed=42)

    def test_repeatable_real_sampler(self):
        first = analyze_hypothetical_call(**self.kw)
        second = analyze_hypothetical_call(**self.kw)
        self.assertEqual(first, second)
        self.assertEqual([p["seed"] for p in first["sampling_provenance"]], [42, 43])
        self.assertEqual([p["iterations"] for p in first["sampling_provenance"]], [5, 5])
        self.assertFalse(first["video_hand_verified"])
        self.assertFalse(first["gto_solution"])

    def test_rejects_duplicate_names(self):
        self.kw["range_scenarios"][1]["name"] = "tight"
        with self.assertRaises(ValueError):
            analyze_hypothetical_call(**self.kw)

    def test_rejects_empty_scenarios(self):
        self.kw["range_scenarios"] = []
        with self.assertRaises(ValueError):
            analyze_hypothetical_call(**self.kw)

    def test_rejects_bool_seed(self):
        self.kw["seed"] = True
        with self.assertRaises(ValueError):
            analyze_hypothetical_call(**self.kw)

    def test_rejects_invalid_scenario_shape(self):
        self.kw["range_scenarios"] = [{"name": "x"}]
        with self.assertRaises(ValueError):
            analyze_hypothetical_call(**self.kw)

    def test_uses_independent_seeds_and_passes_shares(self):
        with patch("video_analyzer.offline_omaha_call_bridge.sample_showdown_shares") as sampler, patch(
                "video_analyzer.offline_omaha_call_bridge.evaluate_sampled_call_scenarios") as ev:
            sampler.side_effect = [
                {"shares": [0., 1.], "seed": 42, "iterations": 2, "attempts": 2,
                 "sampling_method": "synthetic"},
                {"shares": [0.5, 0.5], "seed": 43, "iterations": 2, "attempts": 3,
                 "sampling_method": "synthetic"}]
            ev.return_value = {"classification": "RANGE_SENSITIVE_OR_UNCERTAIN"}
            self.kw["iterations"] = 2
            result = analyze_hypothetical_call(**self.kw)
            self.assertEqual([call.kwargs["seed"] for call in sampler.call_args_list], [42, 43])
            self.assertEqual(ev.call_args.kwargs["scenarios"],
                             [{"name": "tight", "shares": [0., 1.]},
                              {"name": "loose", "shares": [0.5, 0.5]}])
            self.assertEqual(result["sampling_provenance"][1]["attempts"], 3)
            self.assertFalse(result["ocr_verified"])


if __name__ == "__main__":
    unittest.main()
