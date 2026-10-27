"""Offline pot-accounting gap audit for human-reviewed PLO5/PLO6 actions.

Never certifies a complete hand, correct pot, equity or EV. Optional manual
entries are explicitly hypotheses; arithmetic equality is not evidence.

Usage:
  python offline_four_table_pot_gap_audit.py template REVIEWED.json NEW_MANIFEST.json
  python offline_four_table_pot_gap_audit.py audit REVIEWED.json MANIFEST.json NEW_REPORT.json
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_BYTES = 4 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
ACTOR = re.compile(r"(?:hero|seat_[1-9])\Z")
CHIPS = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?\Z")
STREETS = ("preflop", "flop", "turn", "river")
ACTIONS = ("fold", "check", "call", "bet", "raise", "all-in")
FORCED = ("small_blind", "big_blind", "ante", "straddle")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Invalid or symlinked input")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def unique(pairs):
    d = {}
    for k, v in pairs:
        require(k not in d, "Duplicate JSON key")
        d[k] = v
    return d


def read_json(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_BYTES,
            "Invalid input size or path")
    return json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def amount(v, *, positive=False):
    require(type(v) is str and CHIPS.fullmatch(v), "Invalid chip amount")
    n = Decimal(v)
    require(n > 0 if positive else n >= 0, "Invalid chip amount sign")
    return n


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected), "Invalid object fields")


def valid_actor(v, seat_count=None):
    require(type(v) is str and ACTOR.fullmatch(v), "Invalid actor")
    if seat_count is not None and v.startswith("seat_"):
        require(int(v.split("_")[1]) <= seat_count, "Actor exceeds seat count")
    return v


def validate_review(data):
    keys(data, ("schema_version", "analysis_status", "source_action_audit_sha256",
                "source_human_review_sha256", "recording_sha256",
                "recording_hash_checked_in_this_run", "hands",
                "complete_hand_reconstructed", "ready_for_equity_or_ev",
                "automatic_clip_selection_authorized", "warning"))
    require(type(data["schema_version"]) is int and data["schema_version"] == 1 and
            data["analysis_status"] == "human_assigned_observed_actions_not_full_history" and
            data["complete_hand_reconstructed"] is False and
            data["ready_for_equity_or_ev"] is False and
            data["automatic_clip_selection_authorized"] is False and
            type(data["recording_hash_checked_in_this_run"]) is bool and
            type(data["warning"]) is str, "Upstream math promotion or invalid review")
    for k in ("source_action_audit_sha256", "source_human_review_sha256", "recording_sha256"):
        require(type(data[k]) is str and HASH.fullmatch(data[k]), "Invalid provenance hash")
    hands = data["hands"]
    require(type(hands) is list and 1 <= len(hands) <= 64, "Invalid hand count")
    seen = set()
    for hand in hands:
        keys(hand, ("hand_id", "table_id", "declared_game_type", "actions",
                    "observed_action_count", "human_assigned_contributions_by_street",
                    "review_flags", "action_history_complete", "pot_accounting_reconciled",
                    "opponent_ranges_known", "ready_for_equity_or_ev"))
        ident = hand["hand_id"]
        require(type(ident) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", ident)
                and ident not in seen, "Invalid hand identity")
        seen.add(ident)
        require(type(hand["table_id"]) is int and 1 <= hand["table_id"] <= 4 and
                hand["declared_game_type"] in ("PLO5", "PLO6") and
                hand["action_history_complete"] is False and
                hand["pot_accounting_reconciled"] is False and
                hand["opponent_ranges_known"] is False and
                hand["ready_for_equity_or_ev"] is False, "Invalid upstream hand status")
        actions = hand["actions"]
        require(type(actions) is list and type(hand["observed_action_count"]) is int and
                hand["observed_action_count"] == len(actions) and len(actions) <= 32 and
                type(hand["review_flags"]) is list, "Invalid actions/flags")
        totals = {s: Decimal(0) for s in STREETS}
        last = (-1.0, -1)
        last_street = -1
        for a in actions:
            keys(a, ("source_observation_index", "pts_seconds", "action_label_as_observed",
                     "actor_human_assigned", "street_human_assigned",
                     "amount_contributed_human_assigned", "reviewer_note",
                     "visually_supported_street_candidate", "human_confirmed_in_manifest"))
            idx, pts, street = a["source_observation_index"], a["pts_seconds"], a["street_human_assigned"]
            require(type(idx) is int and 0 <= idx < 32 and type(pts) in (int, float) and
                    math.isfinite(pts) and pts >= 0 and (pts, idx) > last and
                    street in STREETS and STREETS.index(street) >= last_street and
                    a["action_label_as_observed"] in ACTIONS and
                    a["human_confirmed_in_manifest"] is True and
                    type(a["reviewer_note"]) is str and a["reviewer_note"].strip(),
                    "Invalid observed action chronology")
            last, last_street = (pts, idx), STREETS.index(street)
            valid_actor(a["actor_human_assigned"])
            candidate = a["visually_supported_street_candidate"]
            require(candidate is None or candidate == street + "_candidate",
                    "Visual street contradicts review")
            chips = a["amount_contributed_human_assigned"]
            if a["action_label_as_observed"] in ("fold", "check"):
                require(chips is None, "Fold/check cannot contribute")
            else:
                totals[street] += amount(chips, positive=True)
        reported = hand["human_assigned_contributions_by_street"]
        keys(reported, STREETS)
        for s in STREETS:
            require(amount(reported[s]) == totals[s], "Upstream totals mismatch")
    return data


def safe_output(output, inputs):
    p = Path(output)
    require(p.parent.is_dir() and not p.parent.is_symlink() and not p.exists() and
            not p.is_symlink() and all(p.resolve() != Path(x).resolve() for x in inputs),
            "Output must be new and separate")
    return p


def write_new(path, data):
    with tempfile.TemporaryDirectory(prefix="plo_pot_gap_", dir=path.parent) as folder:
        staged = Path(folder) / "report.json"
        staged.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        os.link(staged, path)


def template(review_path, output_path):
    output = safe_output(output_path, (review_path,))
    before = digest(review_path)
    data = validate_review(read_json(review_path))
    result = {"schema_version": 1, "source_betting_review_sha256": before,
              "reviewer_confirmed_offline": False,
              "hands": [{"hand_id": h["hand_id"], "table_id": h["table_id"],
                         "seat_count": None, "starting_pot": None,
                         "forced_contributions": [], "unobserved_contributions": [],
                         "returned_uncalled_bets": [], "rake": None,
                         "observed_final_pot": None, "side_pots_declared": None,
                         "complete_action_coverage_confirmed": False,
                         "reviewer_notes": ""} for h in data["hands"]]}
    require(digest(review_path) == before, "Source changed during template generation")
    write_new(output, result)
    return result


def entries(items, expected, seat_count, *, kind=None):
    require(type(items) is list and len(items) <= 40, "Invalid manual entry count")
    result = []
    for item in items:
        keys(item, expected)
        actor = valid_actor(item["actor"], seat_count)
        chips = amount(item["amount"], positive=True)
        note = item["reviewer_note"]
        require(type(note) is str and 1 <= len(note.strip()) <= 500, "Missing manual entry note")
        street = "preflop" if kind == "forced" else item["street"]
        require(street in STREETS, "Invalid manual street")
        if kind == "forced":
            require(item["kind"] in FORCED, "Invalid forced bet kind")
        result.append({"actor": actor, "street": street, "amount": chips,
                       "kind": item.get("kind")})
    return result


def audit(review_path, manifest_path, output_path, *, recording_path=None):
    output = safe_output(output_path, (review_path, manifest_path))
    before, manual_hash = digest(review_path), digest(manifest_path)
    upstream = validate_review(read_json(review_path))
    manual = read_json(manifest_path)
    keys(manual, ("schema_version", "source_betting_review_sha256",
                  "reviewer_confirmed_offline", "hands"))
    require(type(manual["schema_version"]) is int and manual["schema_version"] == 1 and
            manual["source_betting_review_sha256"] == before and
            manual["reviewer_confirmed_offline"] is True and
            type(manual["hands"]) is list and len(manual["hands"]) == len(upstream["hands"]),
            "Manual manifest not bound to source")
    if recording_path is not None:
        require(digest(recording_path) == upstream["recording_sha256"], "Recording hash mismatch")
    results = []
    for h, m in zip(upstream["hands"], manual["hands"]):
        keys(m, ("hand_id", "table_id", "seat_count", "starting_pot",
                 "forced_contributions", "unobserved_contributions",
                 "returned_uncalled_bets", "rake", "observed_final_pot",
                 "side_pots_declared", "complete_action_coverage_confirmed", "reviewer_notes"))
        require(m["hand_id"] == h["hand_id"] and type(m["table_id"]) is int and
                m["table_id"] == h["table_id"] and
                (m["seat_count"] is None or
                 (type(m["seat_count"]) is int and 2 <= m["seat_count"] <= 9)) and
                (m["side_pots_declared"] is None or type(m["side_pots_declared"]) is bool) and
                m["complete_action_coverage_confirmed"] is False and
                type(m["reviewer_notes"]) is str and
                1 <= len(m["reviewer_notes"].strip()) <= 1000,
                "Invalid manual hand metadata")
        seats = m["seat_count"]
        for a in h["actions"]:
            valid_actor(a["actor_human_assigned"], seats)
        forced = entries(m["forced_contributions"], ("actor", "kind", "amount", "reviewer_note"), seats, kind="forced")
        missing = entries(m["unobserved_contributions"], ("actor", "street", "amount", "reviewer_note"), seats)
        refunds = entries(m["returned_uncalled_bets"], ("actor", "street", "amount", "reviewer_note"), seats)
        require(len({(x["actor"], x["kind"]) for x in forced}) == len(forced),
                "Duplicate forced contribution")
        observed = sum((amount(v) for v in h["human_assigned_contributions_by_street"].values()), Decimal(0))
        gross = observed + sum((x["amount"] for x in forced + missing), Decimal(0))
        paid = {}
        for a in h["actions"]:
            if a["amount_contributed_human_assigned"] is not None:
                key = (a["actor_human_assigned"], a["street_human_assigned"])
                paid[key] = paid.get(key, Decimal(0)) + amount(a["amount_contributed_human_assigned"])
        for x in forced + missing:
            key = (x["actor"], x["street"])
            paid[key] = paid.get(key, Decimal(0)) + x["amount"]
        refunded = {}
        for x in refunds:
            key = (x["actor"], x["street"])
            refunded[key] = refunded.get(key, Decimal(0)) + x["amount"]
        for key, value in refunded.items():
            require(value <= paid.get(key, Decimal(0)), "Refund exceeds declared contribution")
        returned = sum((x["amount"] for x in refunds), Decimal(0))
        start = None if m["starting_pot"] is None else amount(m["starting_pot"])
        rake = None if m["rake"] is None else amount(m["rake"])
        final = None if m["observed_final_pot"] is None else amount(m["observed_final_pot"])
        require(rake is None or rake <= (start or Decimal(0)) + gross - returned,
                "Rake exceeds declared pot")
        estimate = None if start is None or rake is None else start + gross - returned - rake
        delta = None if estimate is None or final is None else estimate - final
        flags = ["action_coverage_incomplete", "manual_entries_not_independently_verified"]
        if seats is None: flags.append("seat_count_unknown")
        if start is None: flags.append("starting_pot_unknown")
        if rake is None: flags.append("rake_unknown")
        if final is None: flags.append("final_pot_unknown")
        if m["side_pots_declared"] is None: flags.append("side_pot_status_unknown")
        if m["side_pots_declared"] is True: flags.append("side_pot_distribution_unverified")
        if missing: flags.append("unobserved_contributions_human_hypotheses")
        if h["review_flags"]: flags.append("upstream_visual_flags_unresolved")
        if delta is not None and delta != 0: flags.append("conditional_pot_discrepancy")
        results.append({"hand_id": h["hand_id"], "table_id": h["table_id"],
                        "declared_game_type": h["declared_game_type"],
                        "observed_action_count": len(h["actions"]),
                        "reviewed_action_contributions": str(observed),
                        "manual_forced_contributions": str(sum((x["amount"] for x in forced), Decimal(0))),
                        "manual_unobserved_contributions": str(sum((x["amount"] for x in missing), Decimal(0))),
                        "manual_returned_uncalled_bets": str(returned),
                        "conditional_pot_estimate": str(estimate) if estimate is not None else None,
                        "human_supplied_final_pot": str(final) if final is not None else None,
                        "conditional_difference": str(delta) if delta is not None else None,
                        "blockers": flags, "action_history_complete": False,
                        "pot_accounting_reconciled": False, "ready_for_equity_or_ev": False})
    require(digest(review_path) == before and digest(manifest_path) == manual_hash,
            "Input changed during audit")
    if recording_path is not None:
        require(digest(recording_path) == upstream["recording_sha256"], "Recording changed")
    result = {"schema_version": 1, "analysis_status": "conditional_pot_arithmetic_unverified",
              "source_betting_review_sha256": before, "source_manual_manifest_sha256": manual_hash,
              "recording_sha256": upstream["recording_sha256"],
              "recording_hash_checked_in_this_run": recording_path is not None,
              "hands": results, "complete_hand_reconstructed": False,
              "ready_for_equity_or_ev": False, "automatic_clip_selection_authorized": False,
              "warning": "Arithmetic consistency is not visual proof or complete action coverage. No equity/EV authorization."}
    write_new(output, result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="command", required=True)
    t = subs.add_parser("template")
    t.add_argument("reviewed"); t.add_argument("output")
    a = subs.add_parser("audit")
    a.add_argument("reviewed"); a.add_argument("manifest"); a.add_argument("output")
    a.add_argument("--recording")
    args = p.parse_args(argv)
    result = (template(args.reviewed, args.output) if args.command == "template" else
              audit(args.reviewed, args.manifest, args.output, recording_path=args.recording))
    print(json.dumps({"hands": len(result["hands"]),
                      "status": result.get("analysis_status", "unconfirmed_template")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
