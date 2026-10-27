"""Offline, heads-up PLO5/PLO6 conditional showdown-equity Monte Carlo.

NOT an action recommendation, EV estimator, video recognizer, or real-time tool.
Input hands/ranges are explicitly user-supplied *hypotheses*. No hidden cards
are inferred. Omaha uses exactly TWO private and THREE board cards.

Usage: python offline_omaha_equity_mc.py scenario.json new_report.json

The result is a reproducible estimate conditional on the specified opponent
range, uniformly weighted among unblocked enumerated combinations, and on a
uniform random runout. The reported 95% interval is a conservative Hoeffding
bound on mean payoff in [0,1], not a claim of range/model validity.
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import tempfile

RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK = tuple(r + s for r in RANKS for s in SUITS)
CARD = re.compile(r"[2-9TJQKA][cdhs]\Z")
MAX_INPUT_BYTES = 512 * 1024
MAX_SAMPLES = 10000
MAX_RANGE = 512


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def strict_keys(value: object, expected: tuple[str, ...]) -> None:
    require(type(value) is dict and set(value) == set(expected), "Unexpected or missing JSON fields")


def cards(value: object, count: int, label: str) -> tuple[str, ...]:
    require(type(value) is list and len(value) == count, f"{label}: wrong card count")
    require(all(type(c) is str and CARD.fullmatch(c) for c in value), f"{label}: invalid card")
    require(len(set(value)) == len(value), f"{label}: repeated card")
    return tuple(value)


def validate_scenario(raw: object) -> dict:
    strict_keys(raw, ("schema_version", "game_type", "hero_hole", "known_board",
                      "explicit_villain_hands", "samples", "seed", "range_assumption"))
    require(type(raw["schema_version"]) is int and raw["schema_version"] == 1,
            "Unsupported schema")
    game = raw["game_type"]
    require(type(game) is str and game in ("PLO5", "PLO6"), "Only PLO5/PLO6")
    hole_count = 5 if game == "PLO5" else 6
    hero = cards(raw["hero_hole"], hole_count, "hero")
    board_raw = raw["known_board"]
    require(type(board_raw) is list and len(board_raw) in (0, 3, 4, 5),
            "Board must be preflop/flop/turn/river")
    board = cards(board_raw, len(board_raw), "board")
    require(not (set(hero) & set(board)), "Hero/board overlap")
    range_raw = raw["explicit_villain_hands"]
    require(type(range_raw) is list and 1 <= len(range_raw) <= MAX_RANGE,
            "Range size outside allowed limits")
    seen, range_hands = set(), []
    for item in range_raw:
        hand = cards(item, hole_count, "villain")
        canonical = tuple(sorted(hand))
        require(canonical not in seen, "Duplicate opponent combination")
        seen.add(canonical)
        range_hands.append(hand)
    require(type(raw["samples"]) is int and 100 <= raw["samples"] <= MAX_SAMPLES,
            "Samples must be 100..10000")
    require(type(raw["seed"]) is int and 0 <= raw["seed"] <= 2**32 - 1,
            "Seed outside uint32")
    assumption = raw["range_assumption"]
    require(type(assumption) is str and 1 <= len(assumption.strip()) <= 1000,
            "Explicit range assumption required")
    blocked = set(hero) | set(board)
    eligible = [hand for hand in range_hands if not (set(hand) & blocked)]
    require(eligible, "All opponent combinations blocked by known cards")
    return {"game_type": game, "hero_hole": hero, "known_board": board,
            "eligible_hands": eligible, "range_count": len(range_hands),
            "samples": raw["samples"], "seed": raw["seed"],
            "range_assumption": assumption}


def rank_five(hand: tuple[str, ...]) -> tuple[int, ...]:
    """Standard high-hand rank. Ordered tuples compare lexicographically."""
    require(len(hand) == 5 and len(set(hand)) == 5, "Exactly five distinct cards")
    vals = [RANKS.index(c[0]) + 2 for c in hand]
    counts = Counter(vals)
    desc = sorted(vals, reverse=True)
    flush = len({c[1] for c in hand}) == 1
    unique = set(vals)
    straight = 0
    if len(unique) == 5:
        for high in range(14, 4, -1):
            needed = {high - i for i in range(5)}
            if high == 5:
                needed = {14, 2, 3, 4, 5}
            if unique == needed:
                straight = high
                break
    if flush and straight:
        return (8, straight)
    by_freq = sorted(((freq, val) for val, freq in counts.items()), reverse=True)
    if by_freq[0][0] == 4:
        return (7, by_freq[0][1], by_freq[1][1])
    if [freq for freq, _ in by_freq] == [3, 2]:
        return (6, by_freq[0][1], by_freq[1][1])
    if flush:
        return (5, *desc)
    if straight:
        return (4, straight)
    if by_freq[0][0] == 3:
        return (3, by_freq[0][1], *sorted((v for v in vals if v != by_freq[0][1]), reverse=True))
    if [freq for freq, _ in by_freq] == [2, 2, 1]:
        pairs = sorted((v for freq, v in by_freq if freq == 2), reverse=True)
        return (2, *pairs, next(v for freq, v in by_freq if freq == 1))
    if by_freq[0][0] == 2:
        return (1, by_freq[0][1], *sorted((v for v in vals if v != by_freq[0][1]), reverse=True))
    return (0, *desc)


def best_omaha(hole: tuple[str, ...], board: tuple[str, ...]) -> tuple[int, ...]:
    require(len(hole) in (5, 6) and len(board) == 5 and
            len(set(hole + board)) == len(hole) + 5, "Invalid Omaha showdown cards")
    return max(rank_five(two + three)
               for two in combinations(hole, 2)
               for three in combinations(board, 3))


def estimate(raw: object) -> dict:
    s = validate_scenario(raw)
    rng = random.Random(s["seed"])
    hero, board = s["hero_hole"], s["known_board"]
    known = set(hero) | set(board)
    wins = ties = losses = 0
    for _ in range(s["samples"]):
        villain = rng.choice(s["eligible_hands"])
        used = known | set(villain)
        remaining = [card for card in DECK if card not in used]
        runout = rng.sample(remaining, 5 - len(board))
        full_board = board + tuple(runout)
        a = best_omaha(hero, full_board)
        b = best_omaha(villain, full_board)
        if a > b:
            wins += 1
        elif a == b:
            ties += 1
        else:
            losses += 1
    n = s["samples"]
    equity = (wins + ties / 2) / n
    # Distribution-free, independent bounded [0,1] payoff bound.
    halfwidth = math.sqrt(math.log(2 / 0.05) / (2 * n))
    return {"schema_version": 1, "analysis_status": "conditional_heads_up_equity_only",
            "game_type": s["game_type"], "hero_hole": list(hero),
            "known_board": list(board), "range_assumption": s["range_assumption"],
            "opponent_range_weighting": "uniform_over_unblocked_explicit_combinations",
            "submitted_opponent_combinations": s["range_count"],
            "eligible_opponent_combinations": len(s["eligible_hands"]),
            "blocked_opponent_combinations": s["range_count"] - len(s["eligible_hands"]),
            "seed": s["seed"], "samples": n,
            "wins": wins, "ties": ties, "losses": losses,
            "equity_estimate": equity,
            "equity_95pct_hoeffding_interval": [max(0.0, equity-halfwidth),
                                                  min(1.0, equity+halfwidth)],
            "confidence_method": "two_sided_Hoeffding_95pct_conditional_on_range_model",
            "exactly_two_private_three_board": True,
            "opponent_range_is_hypothesis_not_observation": True,
            "video_evidence_verified": False,
            "ready_for_ev": False, "automatic_clip_selection_authorized": False,
            "warning": "Heads-up high-only conditional equity, not EV or decision quality. Range, actions, fold equity, rake and future betting are not verified."}


def no_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def file_hash(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), "Input must be a regular non-symlink file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process(input_path: str, output_path: str) -> dict:
    source, dest = Path(input_path), Path(output_path)
    require(source.is_file() and not source.is_symlink() and
            0 < source.stat().st_size <= MAX_INPUT_BYTES, "Invalid input file")
    require(dest.parent.is_dir() and not dest.parent.is_symlink() and
            not dest.exists() and not dest.is_symlink() and
            dest.resolve() != source.resolve(), "Output must be a new separate file")
    initial_hash = file_hash(source)
    raw = json.loads(source.read_text(encoding="utf-8"),
                     object_pairs_hook=no_duplicate_json_keys,
                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    report = estimate(raw)
    require(file_hash(source) == initial_hash, "Input changed during calculation")
    report["source_scenario_sha256"] = initial_hash
    with tempfile.TemporaryDirectory(prefix="plo_equity_", dir=dest.parent) as folder:
        staged = Path(folder) / "report.json"
        staged.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.link(staged, dest)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario")
    parser.add_argument("new_report")
    args = parser.parse_args(argv)
    report = process(args.scenario, args.new_report)
    print(json.dumps({"status": report["analysis_status"],
                      "equity": report["equity_estimate"], "samples": report["samples"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
