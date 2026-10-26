"""Offline PLO5/PLO6 street contribution reconstruction from explicit observations.

Amounts are incremental integer chips; no hidden bets, ranges or video facts are
inferred. Every decision remains conditional on human/synthetic observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat

from offline_pot_limit_decision_bounds import assess as assess_bounds

STREETS = ("preflop", "flop", "turn", "river")
KINDS = {"post_blind", "fold", "check", "call", "bet", "raise"}
MAX_BYTES = 262144
MAX_CHIPS = 10**12


def require(ok, message):
    if not ok:
        raise ValueError(message)


def integer(value, name, *, minimum=0):
    require(type(value) is int and minimum <= value <= MAX_CHIPS, f"Invalid {name}")
    return value


def strict_read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_BYTES,
            "Unsafe input")
    raw = p.read_bytes()
    require(0 < len(raw) <= MAX_BYTES, "Oversized input")

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "Duplicate JSON key")
            obj[key] = value
        return obj

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))), raw


def reconstruct(data):
    require(type(data) is dict and set(data) == {
        "schema_version", "variant", "source", "table_id", "hand_label",
        "initial_stacks", "starting_pot", "events"}, "Invalid ledger schema")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1 and
            data["variant"] in ("PLO5", "PLO6") and
            data["source"] in ("synthetic", "human_transcribed") and
            type(data["table_id"]) is int and 1 <= data["table_id"] <= 4 and
            type(data["hand_label"]) is str and 0 < len(data["hand_label"]) <= 64,
            "Invalid hand metadata")
    stacks = data["initial_stacks"]
    require(type(stacks) is dict and 2 <= len(stacks) <= 10, "Invalid player stacks")
    for player, stack in stacks.items():
        require(type(player) is str and 0 < len(player) <= 64, "Invalid player")
        integer(stack, "initial stack", minimum=1)
    pot = integer(data["starting_pot"], "starting pot")
    require(pot + sum(stacks.values()) <= MAX_CHIPS, "Chip limit exceeded")
    events = data["events"]
    require(type(events) is list and len(events) <= 500, "Invalid event list")
    remaining = dict(stacks)
    contributed = {p: 0 for p in stacks}
    folded = set()
    street_index = 0
    last_pts = -1.0
    blind_seen = False
    nonblind_seen = False
    rows = []
    warnings = set()
    for index, event in enumerate(events):
        require(type(event) is dict and set(event) == {
            "street", "actor", "kind", "delta_chips", "source_pts_seconds",
            "confidence", "evidence", "min_full_raise_increment"}, "Invalid event schema")
        street, actor, kind = event["street"], event["actor"], event["kind"]
        require(street in STREETS and actor in stacks and kind in KINDS,
                "Invalid street, actor or action")
        current = STREETS.index(street)
        require(current >= street_index and actor not in folded, "Street regression or action after fold")
        if current > street_index:
            require(kind != "post_blind", "Blinds only preflop")
            contributed = {p: 0 for p in stacks}
            street_index = current
        delta = integer(event["delta_chips"], "delta")
        require(delta <= remaining[actor], "Action exceeds remaining stack")
        pts = event["source_pts_seconds"]
        require(type(pts) in (int, float) and math.isfinite(pts) and
                last_pts <= pts <= 86400 and pts >= 0, "Invalid event timestamp")
        last_pts = pts
        confidence = event["confidence"]
        require(type(confidence) in (int, float) and math.isfinite(confidence) and
                0 <= confidence <= 1 and
                event["evidence"] in ("synthetic", "human_annotation"),
                "Invalid evidence confidence")
        inc = event["min_full_raise_increment"]
        require(inc is None or (type(inc) is int and 1 <= inc <= MAX_CHIPS),
                "Invalid minimum raise increment")
        require(kind not in ("fold", "check") or delta == 0,
                "Fold/check cannot contribute chips")
        if kind == "post_blind":
            require(current == 0 and not nonblind_seen and delta > 0,
                    "Blind posting after action or outside preflop")
            blind_seen = True
        else:
            nonblind_seen = True
        own = contributed[actor]
        highest = max(contributed.values())
        before = pot
        stack_before = remaining[actor]
        flags = []
        bounds = None
        if kind != "post_blind":
            target = own + delta if kind in ("call", "bet", "raise") else None
            bounds = assess_bounds({
                "schema_version": 1, "variant": data["variant"], "source": data["source"],
                "pot_before_action": before, "actor_contribution_street": own,
                "highest_contribution_street": highest,
                "actor_stack_remaining": stack_before,
                "min_full_raise_increment": inc,
                "observed_action": {"kind": kind, "target_contribution_street": target},
                "notes": "Derived from explicitly declared incremental contribution events.",
            })
            flags = list(bounds["review_flags"])
        if kind == "post_blind" and inc is not None:
            flags.append("blind_does_not_establish_full_raise_increment")
        if confidence < 0.8:
            flags.append("low_observation_confidence")
        if kind in ("call", "bet", "raise") and delta == 0:
            flags.append("zero_increment_wager_label")
        require(before + delta <= MAX_CHIPS, "Pot overflow")
        pot += delta
        remaining[actor] -= delta
        contributed[actor] += delta
        if kind == "fold":
            folded.add(actor)
        warnings.update(flags)
        rows.append({
            "event_index": index, "street": street, "actor": actor, "kind": kind,
            "source_pts_seconds": pts, "confidence": confidence,
            "evidence": event["evidence"], "delta_chips": delta,
            "pot_before_action": before, "pot_after_action": pot,
            "actor_contribution_before_street": own,
            "actor_contribution_after_street": contributed[actor],
            "highest_contribution_before_street": highest,
            "actor_stack_before": stack_before, "actor_stack_after": remaining[actor],
            "pot_limit_bounds_conditional": bounds, "review_flags": sorted(set(flags)),
        })
    if not blind_seen:
        warnings.add("preflop_blinds_not_explicit")
    if not events:
        warnings.add("no_visible_actions")
    # No player or pot conservation assertion can certify the source video.
    require(pot + sum(remaining.values()) == data["starting_pot"] + sum(stacks.values()),
            "Chip conservation failed")
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {
        "schema_version": 1,
        "status": "conditional_observation_ledger_not_video_verified",
        "source": data["source"], "variant": data["variant"],
        "table_id": data["table_id"], "hand_label": data["hand_label"],
        "input_canonical_sha256": digest,
        "amount_semantics": "delta_chips_incremental_on_each_event",
        "events": rows, "final_pot": pot, "final_stacks": remaining,
        "final_street_contributions": contributed,
        "review_flags": sorted(warnings),
        "chip_conservation_under_declared_events": True,
        "video_evidence_verified": False, "betting_rules_verified": False,
        "ready_for_equity_or_ev": False, "automatic_clip_selection_authorized": False,
        "limitations": [
            "Only supplied visible/synthetic events are reconstructed; omitted actions remain unknown.",
            "Starting pot is supplied, not inferred; side pots and refunds are not modeled.",
            "Full raise increments are declared, not independently reconstructed.",
            "A zero-warning ledger is not proof of legal betting or video accuracy.",
            "No ranges, equity, EV or automatic clips are authorized by this report.",
        ],
    }


def export(input_path, output_path):
    source, dest = Path(input_path), Path(output_path)
    require(source.resolve() != dest.resolve() and dest.suffix.lower() == ".json" and
            dest.parent.is_dir() and not dest.parent.is_symlink() and not dest.exists(),
            "Unsafe output path")
    data, raw = strict_read(source)
    report = reconstruct(data)
    payload = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    require(len(payload) <= 2 * 1024 * 1024 and source.read_bytes() == raw,
            "Input changed or report oversized")
    fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
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
    parser.add_argument("observed_events_json")
    parser.add_argument("new_report_json")
    args = parser.parse_args(argv)
    print(json.dumps(export(args.observed_events_json, args.new_report_json)["review_flags"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
