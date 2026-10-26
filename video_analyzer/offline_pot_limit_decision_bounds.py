"""Offline PLO5/PLO6 pot-limit arithmetic for explicitly supplied chip ledgers.

This is NOT a hand reconstruction, legality certificate, or strategic advice.
Inputs are hypothetical/human-transcribed and must not be silently treated as
OCR-verified. Amounts are nonnegative integer chip units, not floating money.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

MAX_JSON = 65536
MAX_CHIPS = 10**12
REQUIRED = {"schema_version", "variant", "source", "pot_before_action",
            "actor_contribution_street", "highest_contribution_street",
            "actor_stack_remaining", "min_full_raise_increment",
            "observed_action", "notes"}
ACTIONS = {"fold", "check", "call", "bet", "raise"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def chips(value, field):
    require(type(value) is int and 0 <= value <= MAX_CHIPS, f"Invalid {field}")
    return value


def strict_json(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
            "Unsafe input")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def assess(data):
    require(type(data) is dict and set(data) == REQUIRED and
            type(data["schema_version"]) is int and data["schema_version"] == 1 and
            data["variant"] in ("PLO5", "PLO6") and
            data["source"] in ("synthetic", "human_transcribed") and
            type(data["notes"]) is str and len(data["notes"]) <= 1000,
            "Invalid decision schema")
    pot = chips(data["pot_before_action"], "pot")
    own = chips(data["actor_contribution_street"], "actor contribution")
    highest = chips(data["highest_contribution_street"], "highest contribution")
    stack = chips(data["actor_stack_remaining"], "stack")
    require(highest >= own and pot >= highest + (own if own < highest else 0) and
            pot + stack + own <= MAX_CHIPS, "Inconsistent pot/contributions/stack")
    inc = data["min_full_raise_increment"]
    require(inc is None or (type(inc) is int and 1 <= inc <= MAX_CHIPS),
            "Invalid full raise increment")
    action = data["observed_action"]
    require(type(action) is dict and set(action) == {"kind", "target_contribution_street"} and
            action["kind"] in ACTIONS, "Invalid action")
    target = action["target_contribution_street"]
    require(target is None or (type(target) is int and 0 <= target <= MAX_CHIPS),
            "Invalid action target")
    require((action["kind"] in ("fold", "check") and target is None) or
            (action["kind"] in ("call", "bet", "raise") and target is not None),
            "Unexpected target semantics")
    to_call = highest - own
    after_call = pot + to_call
    cap = own + to_call + after_call if stack >= to_call else own + stack
    max_target = min(own + stack, cap)
    min_full_raise_to = highest + inc if highest and inc is not None else None
    issues = []
    kind = action["kind"]
    if kind == "check" and to_call:
        issues.append("check_faces_call")
    if kind == "call":
        expected = own + min(stack, to_call)
        if to_call == 0:
            issues.append("call_without_amount_to_call")
        if target != expected:
            issues.append("call_target_mismatch_including_short_all_in")
    if kind in ("bet", "raise"):
        if kind == "bet" and highest:
            issues.append("bet_label_when_wager_exists")
        if kind == "raise" and not highest:
            issues.append("raise_label_without_prior_wager")
        if stack <= to_call:
            issues.append("no_stack_available_to_raise")
        if target <= highest:
            issues.append("aggressive_target_not_above_highest")
        if target > own + stack:
            issues.append("target_exceeds_remaining_stack")
        if target > max_target:
            issues.append("target_exceeds_pot_limit_cap")
        if kind == "raise":
            if inc is None:
                issues.append("min_raise_increment_unknown")
            elif target < min_full_raise_to:
                if target == own + stack and target > highest:
                    issues.append("short_all_in_raise_may_not_reopen_action")
                else:
                    issues.append("raise_below_declared_full_raise_minimum")
        if kind == "bet" and inc is None:
            issues.append("opening_minimum_bet_unknown")
        if kind == "bet" and inc is not None and target < inc:
            if target == own + stack and target > 0:
                issues.append("short_all_in_opening_bet")
            else:
                issues.append("opening_bet_below_declared_minimum")
    # A human ledger can be incomplete even when the arithmetic is internally consistent.
    return {
        "schema_version": 1, "status": "conditional_pot_limit_arithmetic_not_video_verified",
        "variant": data["variant"], "input_source": data["source"],
        "amount_unit": "integer_chips", "to_call": to_call,
        "pot_after_hypothetical_call": after_call,
        "pot_limit_max_total_contribution_street": max_target,
        "min_full_raise_total_contribution_street": min_full_raise_to,
        "observed_action": action, "review_flags": sorted(set(issues)),
        "arithmetic_consistent_under_supplied_ledger": not issues,
        "betting_rules_verified": False, "video_evidence_verified": False,
        "hand_reconstruction_verified": False, "ready_for_equity_or_ev": False,
        "automatic_clip_selection_authorized": False,
        "limitations": [
            "Pot includes all chips already committed, including current-street wagers.",
            "Actor and highest contributions refer to the same betting street.",
            "Minimum full raise increment is supplied, not inferred from the video.",
            "Short all-in raises may not reopen betting; no betting order is reconstructed.",
            "No side-pot, action-order, multiway eligibility or OCR verification is performed.",
            "No legality or strategy conclusion follows from a human/synthetic ledger.",
        ],
    }


def export(input_path, output_path):
    source, dest = Path(input_path), Path(output_path)
    require(source.resolve() != dest.resolve() and dest.suffix.lower() == ".json" and
            dest.parent.is_dir() and not dest.parent.is_symlink() and not dest.exists(),
            "Unsafe output")
    raw = source.read_bytes() if source.is_file() and not source.is_symlink() else b""
    report = assess(strict_json(source))
    payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    require(len(payload) <= MAX_JSON and source.read_bytes() == raw, "Source changed or output oversized")
    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output")
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger_json")
    parser.add_argument("new_report_json")
    args = parser.parse_args(argv)
    print(json.dumps(export(args.ledger_json, args.new_report_json)["review_flags"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
