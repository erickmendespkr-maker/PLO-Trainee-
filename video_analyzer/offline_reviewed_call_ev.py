"""Offline conditional call-vs-fold chip EV from *supplied* reviewed annotations.

This module does not recognize cards, run Monte Carlo, certify ranges, or
recommend real-time actions. Equity is an externally supplied estimate; its
claimed confidence interval is NOT recalibrated or independently verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

MAX_JSON = 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CARD = re.compile(r"(?:[2-9TJQKA])(?:[cdhs])\Z")
FIELDS = {"schema_version", "variant", "table_id", "hand_label",
          "source_recording_sha256_claim", "annotation_source", "hero_cards",
          "board_cards", "opponent_range", "equity_estimate", "decision",
          "unresolved_fields"}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def exact(obj, fields, name):
    check(type(obj) is dict and set(obj) == fields, f"Invalid {name} schema")


def finite(value, name, low=0, high=1e12):
    check(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
          f"Invalid {name}")
    return float(value)


def text(value, name, limit=120):
    check(type(value) is str and 0 < len(value) <= limit and not any(ord(c) < 32 for c in value),
          f"Invalid {name}")
    return value


def cards(value, count, name):
    check(type(value) is list and len(value) in count and
          all(type(c) is str and CARD.fullmatch(c) for c in value),
          f"Invalid {name}")
    check(len(set(value)) == len(value), f"Duplicate {name}")
    return value


def evaluate(data):
    exact(data, FIELDS, "input")
    check(type(data["schema_version"]) is int and data["schema_version"] == 1,
          "Unsupported schema version")
    check(data["variant"] in ("PLO5", "PLO6") and type(data["table_id"]) is int and
          1 <= data["table_id"] <= 4, "Invalid game/table")
    text(data["hand_label"], "hand label", 64)
    check(type(data["source_recording_sha256_claim"]) is str and
          SHA256.fullmatch(data["source_recording_sha256_claim"]) is not None,
          "Invalid source SHA claim")
    check(data["annotation_source"] in ("synthetic", "human_annotation"),
          "Invalid annotation source")
    hero = cards(data["hero_cards"], {5} if data["variant"] == "PLO5" else {6}, "hero cards")
    board = cards(data["board_cards"], {0, 3, 4, 5}, "board cards")
    check(len(set(hero + board)) == len(hero) + len(board), "Overlapping cards")
    exact(data["opponent_range"], {"label", "opponents", "assumptions"}, "range")
    text(data["opponent_range"]["label"], "range label")
    check(type(data["opponent_range"]["opponents"]) is int and
          1 <= data["opponent_range"]["opponents"] <= 9, "Invalid opponent count")
    check(type(data["opponent_range"]["assumptions"]) is list and
          1 <= len(data["opponent_range"]["assumptions"]) <= 20,
          "Range assumptions required")
    for assumption in data["opponent_range"]["assumptions"]:
        text(assumption, "range assumption", 240)
    check(type(data["unresolved_fields"]) is list and
          len(data["unresolved_fields"]) <= 30 and
          len(set(data["unresolved_fields"])) == len(data["unresolved_fields"]),
          "Invalid unresolved fields")
    for field in data["unresolved_fields"]:
        text(field, "unresolved field")
    exact(data["decision"], {"action", "pot_before_call", "call_cost",
                             "remaining_stack", "expected_rake", "no_future_betting",
                             "no_side_pots"}, "decision")
    d = data["decision"]
    check(d["action"] in ("call", "fold", "raise"), "Unsupported decision label")
    pot = finite(d["pot_before_call"], "pot")
    cost = finite(d["call_cost"], "call cost")
    stack = finite(d["remaining_stack"], "remaining stack")
    rake = finite(d["expected_rake"], "expected rake")
    check(type(d["no_future_betting"]) is bool and type(d["no_side_pots"]) is bool,
          "Invalid model assumptions")
    check(rake <= pot + cost, "Expected rake exceeds contested pot")
    e = data["equity_estimate"]
    if e is not None:
        exact(e, {"method", "equity", "ci_low", "ci_high", "trials", "seed",
                  "ties_included", "ci_label"}, "equity")
        check(e["method"] == "external_monte_carlo" and
              e["ci_label"] == "claimed_95_percent" and
              e["ties_included"] is True and
              type(e["trials"]) is int and 100 <= e["trials"] <= 1000000000 and
              type(e["seed"]) is int and 0 <= e["seed"] < 2**64,
              "Unsupported or incomplete equity provenance")
        eq = finite(e["equity"], "equity", 0, 1)
        low = finite(e["ci_low"], "equity CI low", 0, 1)
        high = finite(e["ci_high"], "equity CI high", 0, 1)
        check(low <= eq <= high, "Inconsistent equity interval")
    reasons = []
    if data["unresolved_fields"]:
        reasons.append("unresolved_annotations")
    if e is None:
        reasons.append("equity_estimate_missing")
    if d["action"] != "call":
        reasons.append("only_call_vs_fold_supported")
    if data["opponent_range"]["opponents"] != 1:
        reasons.append("multiway_or_side_pot_model_not_supported")
    if not d["no_future_betting"]:
        reasons.append("future_betting_not_modeled")
    if not d["no_side_pots"]:
        reasons.append("side_pots_not_modeled")
    if cost <= 0 or cost > stack:
        reasons.append("invalid_or_unaffordable_call")
    result = {
        "schema_version": 1,
        "status": "conditional_offline_ev_from_declared_annotations_not_video_verified",
        "variant": data["variant"], "table_id": data["table_id"],
        "hand_label": data["hand_label"],
        "source_recording_sha256_claim_unverified": data["source_recording_sha256_claim"],
        "annotation_source_claim": data["annotation_source"],
        "hero_cards_declared": hero, "board_cards_declared": board,
        "opponent_range_label_declared": data["opponent_range"]["label"],
        "range_assumptions_declared": data["opponent_range"]["assumptions"],
        "equity_provenance_claim_unverified": e,
        "conditional_ev_available": not reasons,
        "blocked_reasons": sorted(reasons),
        "ev_call_chips": None, "ev_fold_chips": None,
        "ev_call_interval_chips": None, "break_even_equity": None,
        "interval_interpretation": None,
        "formula": "EV(call) = equity_share * (pot_before_call + call_cost) - call_cost - expected_rake",
        "model_assumptions": [
            "Heads-up single-pot showdown, no future betting or side pots.",
            "Pot is measured before hero calls and includes all opponent wagers already committed.",
            "Equity is a supplied showdown pot-share estimate, including ties; not recomputed here.",
            "Expected rake is a fixed unconditional chip cost supplied by the analyst.",
            "Fold EV is zero relative to this decision; prior chips are sunk.",
            "Claimed equity confidence bounds are propagated, not independently validated.",
            "Omaha exactly-two-private/three-board evaluation is not performed by this module.",
            "Card visibility, source hash, OCR, range accuracy and annotations are not verified.",
        ],
        "video_evidence_verified": False,
        "monte_carlo_recomputed": False,
        "automatic_clip_selection_authorized": False,
        "strategic_error_proven": False,
    }
    if not reasons:
        pool = pot + cost
        # Requiring a positive pot and a positive call ensures the denominator exists.
        threshold = (cost + rake) / pool
        ev = lambda equity: round(equity * pool - cost - rake, 8)
        result.update({
            "ev_call_chips": ev(eq), "ev_fold_chips": 0.0,
            "ev_call_interval_chips": [ev(low), ev(high)],
            "break_even_equity": round(threshold, 10),
            "interval_interpretation": ("positive_across_claimed_interval" if ev(low) > 0 else
                "negative_across_claimed_interval" if ev(high) < 0 else
                "crosses_or_touches_zero"),
        })
    return result


def unique_pairs(pairs):
    result = {}
    for k, v in pairs:
        check(k not in result, "Duplicate JSON key")
        result[k] = v
    return result


def reject_constant(value):
    raise ValueError(f"Nonfinite JSON constant: {value}")


def export(source, destination):
    src, dst = Path(source), Path(destination)
    check(src.is_file() and not src.is_symlink() and 0 < src.stat().st_size <= MAX_JSON,
          "Unsafe input")
    check(dst.suffix.lower() == ".json" and dst.parent.is_dir() and
          not dst.parent.is_symlink() and not dst.exists() and
          src.resolve() != dst.resolve(), "Unsafe output")
    raw = src.read_bytes()
    check(0 < len(raw) <= MAX_JSON, "Input too large")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)
    report = evaluate(data)
    report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    payload = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    check(len(payload) <= MAX_JSON and src.read_bytes() == raw, "Input changed")
    fd = os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            check(stat.S_ISREG(os.fstat(out.fileno()).st_mode), "Unsafe output type")
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewed_hand_json")
    parser.add_argument("new_conditional_ev_report_json")
    args = parser.parse_args(argv)
    report = export(args.reviewed_hand_json, args.new_conditional_ev_report_json)
    print(json.dumps({"available": report["conditional_ev_available"],
                      "blocked_reasons": report["blocked_reasons"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
