"""Conservative offline PLO5/PLO6 action-review triage for a reviewed snapshot.

This is a *warning-only* evidence checklist, NOT a pot-limit betting rules
validator. The upstream action ``amount`` has no unambiguous contribution/
raise-to semantics, and observed actions may omit blinds, opponents or streets.
No action, video frame, range, equity or EV is inferred or authorized here.
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

MAX_JSON = 4 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")
STREETS = ("preflop", "flop", "turn", "river")
ACTIONS = {"fold", "check", "call", "bet", "raise"}
GATES = ("hand_reconstruction_verified", "source_pts_verified",
         "ready_for_equity_or_ev", "automatic_clip_selection_authorized")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def read_strict_json(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
            "Unsafe snapshot input")
    raw = p.read_bytes()
    require(0 < len(raw) <= MAX_JSON, "Oversized snapshot")

    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "Duplicate JSON key")
            out[key] = value
        return out

    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON encoding") from exc
    require(type(obj) is dict, "Expected snapshot object")
    return obj, raw


def audit_snapshot(snapshot):
    """Return deterministic, non-authoritative triage from a reviewed candidate.

    Hash checks detect accidental mismatch inside this JSON, not authenticity:
    a malicious author can rewrite both a value and its self-declared hash.
    """
    require(type(snapshot) is dict and snapshot.get("schema_version") == 1 and
            snapshot.get("status") == "derived_human_reviewed_snapshot_not_video_verified" and
            type(snapshot.get("job_id")) is str and
            type(snapshot.get("source_recording_sha256")) is str and
            SHA.fullmatch(snapshot["source_recording_sha256"]),
            "Unexpected reviewed snapshot")
    for gate in GATES:
        require(snapshot.get(gate) is False, "Upstream snapshot asserts verification")
    rows = snapshot.get("hands")
    require(type(rows) is list and len(rows) <= 2000, "Invalid hand list")
    seen = set()
    output = []
    intervals = {}
    for row in rows:
        require(type(row) is dict, "Invalid hand row")
        entry = row.get("human_entry_candidate")
        require(type(entry) is dict, "Missing candidate")
        table, label = row.get("table_id"), row.get("hand_label_human_assigned")
        require(type(table) is int and 1 <= table <= 4 and
                type(label) is str and 0 < len(label) <= 64 and
                (table, label) not in seen and
                entry.get("table_id") == table and
                entry.get("hand_label_human_assigned") == label,
                "Duplicate or inconsistent hand identity")
        seen.add((table, label))
        require(entry.get("variant") in ("PLO5", "PLO6"), "Invalid PLO variant")
        require(type(row.get("candidate_human_entry_sha256")) is str and
                digest(entry) == row["candidate_human_entry_sha256"],
                "Candidate digest mismatch")
        for gate in GATES:
            require(row.get(gate) is False, "Upstream hand asserts verification")
        start, end = entry.get("source_pts_start_seconds"), entry.get("source_pts_end_seconds")
        require((start is None and end is None) or
                (finite(start) and finite(end) and 0 <= start < end <= 86400),
                "Invalid source interval")
        board = entry.get("board_by_street")
        require(type(board) is dict and set(board) == {"flop", "turn", "river"},
                "Invalid board structure")
        hero = entry.get("hero_cards")
        require(hero is None or (type(hero) is list and len(hero) == int(entry["variant"][-1])),
                "Wrong hero card count")
        actions = entry.get("actions")
        require(type(actions) is list and len(actions) <= 200, "Invalid actions")
        flags = set()
        if start is None:
            flags.add("hand_interval_missing")
        else:
            intervals.setdefault(table, []).append((start, end, label))
        if hero is None:
            flags.add("hero_cards_missing")
        if board["flop"] is None:
            flags.add("flop_not_visible")
        if not entry.get("opponent_range_notes"):
            flags.add("opponent_range_unspecified")
        for key in ("pot_before_decision", "call_amount", "effective_stack"):
            if entry.get(key) is None:
                flags.add(key + "_missing")
        if not actions:
            flags.add("actions_missing")
        folded = set()
        last_by_street = {}
        last_pts = -1.0
        last_street = -1
        for action in actions:
            require(type(action) is dict and set(action) ==
                    {"street", "actor", "action", "amount", "source_pts_seconds"},
                    "Unexpected action schema")
            street, actor, kind = action["street"], action["actor"], action["action"]
            pts, amount = action["source_pts_seconds"], action["amount"]
            require(street in STREETS and kind in ACTIONS and
                    type(actor) is str and 0 < len(actor) <= 64 and
                    finite(pts) and 0 <= pts <= 86400 and
                    finite(amount) and 0 <= amount <= 1e9 and
                    STREETS.index(street) >= last_street and pts >= last_pts and
                    (start is None or start <= pts <= end),
                    "Invalid or nonchronological action")
            if actor == "unknown":
                flags.add("actor_unknown")
            if actor in folded and actor != "unknown":
                flags.add("action_after_visible_fold")
            if kind == "fold" and actor != "unknown":
                folded.add(actor)
            previous = last_by_street.get(street)
            if previous is not None:
                if pts == previous["source_pts_seconds"]:
                    flags.add("same_pts_multiple_actions")
                if actor == previous["actor"] and actor != "unknown":
                    flags.add("consecutive_actions_same_actor")
                if kind == "bet" and previous["action"] in ("bet", "raise"):
                    flags.add("bet_after_aggressive_action_check_labels")
            elif kind in ("call", "raise"):
                flags.add("call_or_raise_without_visible_prior_action")
            last_by_street[street] = action
            last_pts, last_street = pts, STREETS.index(street)
        output.append({
            "table_id": table, "hand_label_human_assigned": label,
            "candidate_human_entry_sha256": row["candidate_human_entry_sha256"],
            "observed_action_count": len(actions),
            "review_flags": sorted(flags),
            "betting_rules_verified": False,
            "ready_for_equity_or_ev": False,
            "automatic_clip_selection_authorized": False,
        })
    by_key = {(r["table_id"], r["hand_label_human_assigned"]): r for r in output}
    for table, group in intervals.items():
        group.sort(key=lambda item: (item[0], item[1], item[2]))
        max_end = -1
        for start, end, label in group:
            if start < max_end:
                by_key[(table, label)]["review_flags"].append("overlap_with_prior_hand_same_table")
            max_end = max(max_end, end)
    for row in output:
        row["review_flags"] = sorted(set(row["review_flags"]))
    counts = {}
    for row in output:
        for flag in row["review_flags"]:
            counts[flag] = counts.get(flag, 0) + 1
    return {
        "schema_version": 1,
        "status": "human_review_triage_only_not_betting_rule_verification",
        "job_id": snapshot["job_id"],
        "source_recording_sha256": snapshot["source_recording_sha256"],
        "reviewed_snapshot_sha256": digest(snapshot),
        "hands": output,
        "counts": {"hands": len(output), "hands_with_flags": sum(bool(r["review_flags"]) for r in output),
                   "flags_by_type": dict(sorted(counts.items()))},
        "betting_rules_verified": False,
        "hand_reconstruction_verified": False,
        "source_pts_verified": False,
        "ready_for_equity_or_ev": False,
        "automatic_clip_selection_authorized": False,
        "limitations": [
            "Warnings are triage hints, not proof of illegal bets or strategic mistakes.",
            "Action amount has no declared incremental-vs-total-raise semantics.",
            "Blinds, per-player contributions, prior raises and missing actions are unknown.",
            "Pot-limit raise ceilings, legal min-raises and stack conservation cannot be certified.",
            "Input snapshot is not independently re-derived from the draft/review chain.",
            "Human candidate data are not verified against source frames or OCR.",
        ],
    }


def export_audit(snapshot_path, output_path):
    source, output = Path(snapshot_path), Path(output_path)
    require(source.resolve() != output.resolve() and output.suffix.lower() == ".json" and
            output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists(), "Unsafe output path")
    snapshot, raw = read_strict_json(source)
    report = audit_snapshot(snapshot)
    payload = (json.dumps(report, indent=2, ensure_ascii=False,
                          allow_nan=False) + "\n").encode("utf-8")
    require(len(payload) <= MAX_JSON, "Oversized report")
    require(source.read_bytes() == raw, "Source changed during audit")
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output")
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reviewed_snapshot_json")
    parser.add_argument("new_audit_json")
    args = parser.parse_args(argv)
    print(json.dumps(export_audit(args.reviewed_snapshot_json, args.new_audit_json)["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())