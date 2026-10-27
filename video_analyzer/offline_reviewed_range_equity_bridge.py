"""Offline reviewed PLO5/PLO6 heads-up range Monte Carlo -> conditional call EV.

All observations and opponent combos are user-supplied, not read from video.
A manual-review declaration is not proof of visual accuracy. No live play.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat

from offline_reviewed_call_ev import evaluate, check, exact, text, unique_pairs, reject_constant
from range_ev import WeightedHand, estimate_weighted_range_equity

MAX_BYTES = 1024 * 1024
MAX_RANGE = 1000


def analyze(data):
    exact(data, {"schema_version", "reviewed_hand", "review_gate", "weighted_range", "monte_carlo"}, "bridge")
    check(type(data["schema_version"]) is int and data["schema_version"] == 1, "Unsupported schema")
    gate = data["review_gate"]
    exact(gate, {"status", "reviewer_label"}, "review gate")
    check(gate["status"] in ("synthetic_fixture", "human_confirmed_claim"), "Review confirmation required")
    text(gate["reviewer_label"], "reviewer label", 80)
    hand = data["reviewed_hand"]
    check(type(hand) is dict and hand.get("equity_estimate") is None,
          "Existing external equity is not accepted; supply a new range for recomputation")
    prior = evaluate(hand)  # Validate the existing, exact reviewed-hand schema.
    blocked = [x for x in prior["blocked_reasons"] if x != "equity_estimate_missing"]
    if gate["status"] == "synthetic_fixture" and hand["annotation_source"] != "synthetic":
        blocked.append("synthetic_gate_annotation_mismatch")
    if gate["status"] == "human_confirmed_claim" and hand["annotation_source"] != "human_annotation":
        blocked.append("human_gate_annotation_mismatch")
    mc = data["monte_carlo"]
    exact(mc, {"trials", "seed"}, "monte carlo")
    check(type(mc["trials"]) is int and 100 <= mc["trials"] <= 50000, "Trials out of bounds")
    check(type(mc["seed"]) is int and 0 <= mc["seed"] < 2**64, "Invalid seed")
    entries = data["weighted_range"]
    check(type(entries) is list and 1 <= len(entries) <= MAX_RANGE, "Invalid range length")
    weights = []
    seen = set()
    for entry in entries:
        exact(entry, {"cards", "weight"}, "range combo")
        cards = entry["cards"]
        check(type(cards) is list and len(cards) == len(hand["hero_cards"]), "Invalid opponent card count")
        check(all(type(c) is str for c in cards), "Invalid opponent card type")
        check(type(entry["weight"]) in (int, float) and math.isfinite(entry["weight"]) and
              0 <= entry["weight"] <= 1e12, "Invalid combo weight")
        key = tuple(sorted(cards))
        check(key not in seen, "Duplicate opponent combo")
        seen.add(key)
        weights.append(WeightedHand(tuple(cards), float(entry["weight"])))
    check(any(x.weight > 0 for x in weights), "Range needs a positive-weight combo")
    range_bytes = json.dumps(entries, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")
    report = {
        "schema_version": 1,
        "status": "offline_conditional_math_from_declared_review_and_range",
        "variant": hand["variant"], "table_id": hand["table_id"],
        "hand_label": hand["hand_label"],
        "review_gate_claim": gate,
        "recording_sha256_claim_unverified": hand["source_recording_sha256_claim"],
        "range_label_claim": hand["opponent_range"]["label"],
        "range_assumptions_claim": hand["opponent_range"]["assumptions"],
        "range_sha256": hashlib.sha256(range_bytes).hexdigest(),
        "range_combos_supplied": len(entries),
        "trials_requested": mc["trials"], "seed": mc["seed"],
        "blocked_reasons": sorted(blocked),
        "monte_carlo_recomputed": False,
        "equity": None, "equity_ci95_hoeffding": None,
        "wins": None, "ties": None, "losses": None,
        "ev_call_chips": None, "ev_fold_chips": None,
        "ev_call_interval_chips": None, "break_even_equity": None,
        "interval_interpretation": None,
        "model": "Heads-up single-pot call versus fold; no future betting; fixed unconditional rake; no ICM",
        "uncertainty": "Hoeffding 95% CI bounds MC sampling only, not opponent range, OCR or annotation error",
        "video_evidence_verified": False,
        "opponent_range_verified": False,
        "strategic_error_proven": False,
        "automatic_clip_selection_authorized": False,
    }
    if blocked:
        return report
    # range_ev validates card uniqueness, board collisions, positive-weight
    # opponent combos, and the exactly-two-private/three-board Omaha rule.
    result = estimate_weighted_range_equity(hand["hero_cards"], hand["board_cards"],
                                            weights, trials=mc["trials"], seed=mc["seed"])
    d = hand["decision"]
    pool = float(d["pot_before_call"]) + float(d["call_cost"])
    cost = float(d["call_cost"])
    rake = float(d["expected_rake"])
    ev = lambda e: round(e * pool - cost - rake, 8)
    lo, hi = result.ci95_low, result.ci95_high
    report.update({
        "monte_carlo_recomputed": True,
        "equity": result.equity,
        "equity_ci95_hoeffding": [lo, hi],
        "wins": result.wins, "ties": result.ties, "losses": result.losses,
        "ev_call_chips": ev(result.equity), "ev_fold_chips": 0.0,
        "ev_call_interval_chips": [ev(lo), ev(hi)],
        "break_even_equity": round((cost + rake) / pool, 10),
        "interval_interpretation": ("positive_across_sampling_interval" if ev(lo) > 0 else
                                    "negative_across_sampling_interval" if ev(hi) < 0 else
                                    "crosses_or_touches_zero"),
    })
    return report


def export(source, destination):
    src, dst = Path(source), Path(destination)
    check(src.is_file() and not src.is_symlink() and 0 < src.stat().st_size <= MAX_BYTES,
          "Unsafe input")
    check(dst.suffix.lower() == ".json" and dst.parent.is_dir() and
          not dst.parent.is_symlink() and not dst.exists() and
          src.resolve() != dst.resolve(), "Unsafe output")
    raw = src.read_bytes()
    check(0 < len(raw) <= MAX_BYTES, "Input too large")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=reject_constant)
    report = analyze(data)
    report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    payload = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    check(len(payload) <= MAX_BYTES and src.read_bytes() == raw, "Input changed")
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_json")
    p.add_argument("new_output_json")
    args = p.parse_args(argv)
    report = export(args.input_json, args.new_output_json)
    print(json.dumps({"monte_carlo_recomputed": report["monte_carlo_recomputed"],
                      "blocked_reasons": report["blocked_reasons"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
