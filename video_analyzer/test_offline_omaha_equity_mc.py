"""Offline synthetic unit tests for PLO5/PLO6 equity hypotheses."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_omaha_equity_mc as m


def scenario(game="PLO5"):
    return {"schema_version": 1, "game_type": game,
            "hero_hole": ["As", "Ad", "Kh", "Qh", "Jc"] + (["Tc"] if game == "PLO6" else []),
            "known_board": ["2c", "7d", "9s"],
            "explicit_villain_hands": [["3c", "4d", "5h", "6s", "8c"] + (["8d"] if game == "PLO6" else []),
                                       ["2h", "3d", "4c", "5s", "6d"] + (["8h"] if game == "PLO6" else [])],
            "samples": 100, "seed": 42,
            "range_assumption": "Synthetic two-combination uniform heads-up range; not observed."}


class TestRanking(unittest.TestCase):
    def test_rank_categories(self):
        hands = [
            ["As", "Ks", "Qs", "Js", "Ts"],
            ["Ac", "Ad", "Ah", "As", "2d"],
            ["Kc", "Kd", "Kh", "2s", "2d"],
            ["Ac", "Jc", "8c", "4c", "2c"],
            ["As", "2d", "3c", "4h", "5s"],
            ["Qh", "Qs", "Qc", "2d", "7h"],
            ["Kh", "Kd", "3c", "3d", "2s"],
            ["Ah", "Ad", "9c", "5s", "3d"],
            ["As", "Kd", "Jh", "8s", "2c"],
        ]
        self.assertEqual([m.rank_five(tuple(x))[0] for x in hands], list(range(8, -1, -1)))

    def test_wheel_below_six_high(self):
        self.assertLess(m.rank_five(("As", "2d", "3c", "4h", "5s")),
                        m.rank_five(("2c", "3d", "4c", "5h", "6s")))

    def test_full_house_tiebreak(self):
        self.assertGreater(m.rank_five(("Ac", "Ad", "Ah", "2s", "2d")),
                           m.rank_five(("Kc", "Kd", "Kh", "Qs", "Qd")))

    def test_board_royal_cannot_be_played_alone(self):
        hero = ("2c", "3d", "4c", "5s", "6d")
        board = ("Ah", "Kh", "Qh", "Jh", "Th")
        self.assertLess(m.best_omaha(hero, board)[0], 5)

    def test_two_hole_three_board_can_make_flush(self):
        hero = ("2h", "3h", "4c", "5s", "6d")
        board = ("Ah", "Kh", "Qh", "Jd", "Tc")
        self.assertEqual(m.best_omaha(hero, board)[0], 5)

    def test_omaha_duplicate_cards_rejected(self):
        with self.assertRaises(ValueError):
            m.best_omaha(("As", "Ad", "Kh", "Qh", "Jc"), ("As", "2d", "3c", "4h", "5s"))


class TestContract(unittest.TestCase):
    def test_both_games_run(self):
        for game in ("PLO5", "PLO6"):
            with self.subTest(game=game):
                r = m.estimate(scenario(game))
                self.assertEqual(r["wins"] + r["ties"] + r["losses"], 100)
                self.assertFalse(r["ready_for_ev"])
                self.assertFalse(r["video_evidence_verified"])
                self.assertEqual(r["game_type"], game)

    def test_seed_reproducibility(self):
        self.assertEqual(m.estimate(scenario()), m.estimate(scenario()))

    def test_seed_changes_sampling(self):
        a, b = scenario(), scenario()
        b["seed"] = 123
        self.assertNotEqual((m.estimate(a)["wins"], m.estimate(a)["ties"]),
                            (m.estimate(b)["wins"], m.estimate(b)["ties"]))

    def test_confidence_bound_contains_estimate(self):
        r = m.estimate(scenario())
        lo, hi = r["equity_95pct_hoeffding_interval"]
        self.assertLessEqual(lo, r["equity_estimate"])
        self.assertLessEqual(r["equity_estimate"], hi)
        self.assertGreaterEqual(lo, 0)
        self.assertLessEqual(hi, 1)

    def test_blocked_range_filtered(self):
        a = scenario()
        a["explicit_villain_hands"].append(["As", "2h", "3s", "4s", "5c"])
        r = m.estimate(a)
        self.assertEqual(r["blocked_opponent_combinations"], 1)
        self.assertEqual(r["eligible_opponent_combinations"], 2)

    def test_all_range_blocked(self):
        a = scenario()
        a["explicit_villain_hands"] = [["As", "2h", "3s", "4s", "5c"]]
        with self.assertRaises(ValueError): m.estimate(a)

    def test_duplicate_range_order_insensitive(self):
        a = scenario()
        a["explicit_villain_hands"].append(list(reversed(a["explicit_villain_hands"][0])))
        with self.assertRaises(ValueError): m.estimate(a)

    def test_overlap_hero_board(self):
        a = scenario(); a["known_board"][0] = "As"
        with self.assertRaises(ValueError): m.estimate(a)

    def test_invalid_board_lengths(self):
        for length in (1, 2, 6):
            a = scenario(); a["known_board"] = ["2c", "7d", "9s", "Ts", "Js", "Qc"][:length]
            with self.subTest(length=length), self.assertRaises(ValueError): m.estimate(a)

    def test_no_hypothesis(self):
        a = scenario(); a["range_assumption"] = "  "
        with self.assertRaises(ValueError): m.estimate(a)

    def test_boolean_samples_rejected(self):
        a = scenario(); a["samples"] = True
        with self.assertRaises(ValueError): m.estimate(a)

    def test_samples_bounded(self):
        for n in (99, 10001):
            a = scenario(); a["samples"] = n
            with self.subTest(n=n), self.assertRaises(ValueError): m.estimate(a)

    def test_seed_bounded(self):
        for n in (-1, 2**32):
            a = scenario(); a["seed"] = n
            with self.subTest(n=n), self.assertRaises(ValueError): m.estimate(a)

    def test_bad_game(self):
        a = scenario(); a["game_type"] = "PLO4"
        with self.assertRaises(ValueError): m.estimate(a)

    def test_oversized_range(self):
        a = scenario(); a["explicit_villain_hands"] *= 257
        with self.assertRaises(ValueError): m.estimate(a)

    def test_extra_fields_rejected(self):
        a = scenario(); a["ready_for_ev"] = True
        with self.assertRaises(ValueError): m.estimate(a)

    def test_duplicate_hole_rejected(self):
        a = scenario(); a["hero_hole"][1] = "As"
        with self.assertRaises(ValueError): m.estimate(a)

    def test_no_range_rejected(self):
        a = scenario(); a["explicit_villain_hands"] = []
        with self.assertRaises(ValueError): m.estimate(a)

    def test_empty_board_allowed(self):
        a = scenario(); a["known_board"] = []
        r = m.estimate(a)
        self.assertEqual(r["samples"], 100)

    def test_river_board_allowed(self):
        a = scenario(); a["known_board"] += ["Ts", "Js"]
        r = m.estimate(a)
        self.assertEqual(r["samples"], 100)

    def test_result_cannot_authorize_clips(self):
        r = m.estimate(scenario())
        self.assertIs(r["automatic_clip_selection_authorized"], False)


class TestFiles(unittest.TestCase):
    def test_cli_file_and_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "scenario.json"
            output = Path(folder) / "report.json"
            source.write_text(json.dumps(scenario()), encoding="utf-8")
            r = m.process(str(source), str(output))
            self.assertEqual(json.loads(output.read_text()), r)
            self.assertEqual(r["source_scenario_sha256"], m.file_hash(source))
            with self.assertRaises(ValueError): m.process(str(source), str(output))

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source, out = Path(folder)/"input.json", Path(folder)/"out.json"
            source.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(ValueError): m.process(str(source), str(out))
            self.assertFalse(out.exists())

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source, alias, out = Path(folder)/"input.json", Path(folder)/"alias.json", Path(folder)/"out.json"
            source.write_text(json.dumps(scenario()), encoding="utf-8")
            alias.symlink_to(source)
            with self.assertRaises(ValueError): m.process(str(alias), str(out))

    def test_input_output_same_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/"input.json"
            source.write_text(json.dumps(scenario()), encoding="utf-8")
            with self.assertRaises(ValueError): m.process(str(source), str(source))

    def test_nan_json_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source, out = Path(folder)/"input.json", Path(folder)/"out.json"
            source.write_text(json.dumps(scenario()).replace('"samples": 100', '"samples": NaN'), encoding="utf-8")
            with self.assertRaises(ValueError): m.process(str(source), str(out))


if __name__ == "__main__": unittest.main()
