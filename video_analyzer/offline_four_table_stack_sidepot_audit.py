"""Offline conditional stack/side-pot audit for reviewed PLO5/PLO6 recordings.

This is NOT a poker hand reconstructor or equity/EV engine. All seat ledgers are
human hypotheses. Side-pot tiers are arithmetic partitions, not proven payouts.

Usage:
  python offline_four_table_stack_sidepot_audit.py template POT_REPORT.json NEW_TEMPLATE.json
  python offline_four_table_stack_sidepot_audit.py audit POT_REPORT.json MANIFEST.json NEW_REPORT.json
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

MAX_BYTES = 4 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
ACTOR = re.compile(r"(?:hero|seat_[1-9])\Z")
CHIPS = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?\Z")
STATES = ("active", "folded", "all_in", "unknown")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def keys(obj, names):
    require(type(obj) is dict and set(obj) == set(names), "Unexpected or missing JSON fields")


def sha256(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), "Invalid or symlinked input")
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, "Duplicate JSON key")
        out[k] = v
    return out


def read_json(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_BYTES,
            "Invalid input size or symlink")
    return json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def chips(value):
    require(type(value) is str and CHIPS.fullmatch(value), "Invalid decimal chip amount")
    return Decimal(value)


def validate_source(data):
    keys(data, ("schema_version", "analysis_status", "source_betting_review_sha256",
                "source_manual_manifest_sha256", "recording_sha256",
                "recording_hash_checked_in_this_run", "hands", "complete_hand_reconstructed",
                "ready_for_equity_or_ev", "automatic_clip_selection_authorized", "warning"))
    require(type(data["schema_version"]) is int and data["schema_version"] == 1 and
            data["analysis_status"] == "conditional_pot_arithmetic_unverified" and
            data["complete_hand_reconstructed"] is False and
            data["ready_for_equity_or_ev"] is False and
            data["automatic_clip_selection_authorized"] is False and
            type(data["recording_hash_checked_in_this_run"]) is bool and
            type(data["warning"]) is str, "Invalid upstream status")
    for field in ("source_betting_review_sha256", "source_manual_manifest_sha256", "recording_sha256"):
        require(type(data[field]) is str and HASH.fullmatch(data[field]), "Invalid source hash")
    require(type(data["hands"]) is list and 1 <= len(data["hands"]) <= 64, "Invalid hand count")
    seen = set()
    for h in data["hands"]:
        keys(h, ("hand_id", "table_id", "declared_game_type", "observed_action_count",
                 "reviewed_action_contributions", "manual_forced_contributions",
                 "manual_unobserved_contributions", "manual_returned_uncalled_bets",
                 "conditional_pot_estimate", "human_supplied_final_pot",
                 "conditional_difference", "blockers", "action_history_complete",
                 "pot_accounting_reconciled", "ready_for_equity_or_ev"))
        require(type(h["hand_id"]) is str and ID.fullmatch(h["hand_id"]) and
                h["hand_id"] not in seen and type(h["table_id"]) is int and
                1 <= h["table_id"] <= 4 and h["declared_game_type"] in ("PLO5", "PLO6") and
                type(h["observed_action_count"]) is int and 0 <= h["observed_action_count"] <= 32 and
                h["action_history_complete"] is False and
                h["pot_accounting_reconciled"] is False and
                h["ready_for_equity_or_ev"] is False and
                type(h["blockers"]) is list and all(type(b) is str for b in h["blockers"]),
                "Invalid upstream hand")
        seen.add(h["hand_id"])
        for field in ("reviewed_action_contributions", "manual_forced_contributions",
                      "manual_unobserved_contributions", "manual_returned_uncalled_bets"):
            chips(h[field])
        gross = sum((chips(h[f]) for f in ("reviewed_action_contributions",
                    "manual_forced_contributions", "manual_unobserved_contributions")), Decimal(0))
        require(chips(h["manual_returned_uncalled_bets"]) <= gross, "Refund exceeds gross")
        for field in ("conditional_pot_estimate", "human_supplied_final_pot", "conditional_difference"):
            if h[field] is not None:
                if field == "conditional_difference":
                    require(type(h[field]) is str and re.fullmatch(r"-?\d+(?:\.\d{1,2})?", h[field]),
                            "Invalid signed conditional difference")
                else:
                    chips(h[field])
        if h["conditional_pot_estimate"] is not None and h["human_supplied_final_pot"] is not None:
            require(h["conditional_difference"] is not None and
                    Decimal(h["conditional_difference"]) ==
                    chips(h["conditional_pot_estimate"]) - chips(h["human_supplied_final_pot"]),
                    "Upstream conditional difference mismatch")
        else:
            require(h["conditional_difference"] is None, "Unfounded upstream difference")
    return data


def safe_output(path, sources):
    p = Path(path)
    require(p.parent.is_dir() and not p.parent.is_symlink() and not p.exists() and
            not p.is_symlink() and all(p.resolve() != Path(s).resolve() for s in sources),
            "Output must be a new separate file")
    return p


def write_new(path, value):
    with tempfile.TemporaryDirectory(prefix="plo_stack_audit_", dir=path.parent) as tmp:
        staged = Path(tmp) / "output.json"
        staged.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8")
        os.link(staged, path)


def make_template(source_path, output_path):
    output = safe_output(output_path, (source_path,))
    before = sha256(source_path)
    source = validate_source(read_json(source_path))
    result = {"schema_version": 1, "source_pot_audit_sha256": before,
              "reviewer_confirmed_offline": False,
              "hands": [{"hand_id": h["hand_id"], "table_id": h["table_id"],
                         "seat_count": None, "seats": [], "reviewer_notes": ""}
                        for h in source["hands"]]}
    require(sha256(source_path) == before, "Source changed")
    write_new(output, result)
    return result


def side_pot_tiers(seats):
    """Pure arithmetic partition; does not allocate awards or prove eligibility."""
    levels = sorted({s["committed"] for s in seats if s["committed"] > 0})
    tiers = []
    prev = Decimal(0)
    for level in levels:
        contributors = [s for s in seats if s["committed"] >= level]
        eligible = [s["actor"] for s in contributors if s["state"] not in ("folded", "unknown")]
        unknown = [s["actor"] for s in contributors if s["state"] == "unknown"]
        tiers.append({"cap": str(level), "amount": str((level - prev) * len(contributors)),
                      "contributors": [s["actor"] for s in contributors],
                      "eligible_if_states_correct": eligible,
                      "unknown_eligibility": unknown})
        prev = level
    return tiers


def audit(source_path, manifest_path, output_path, *, recording_path=None):
    inputs = (source_path, manifest_path) + ((recording_path,) if recording_path is not None else ())
    output = safe_output(output_path, inputs)
    source_hash, manifest_hash = sha256(source_path), sha256(manifest_path)
    source = validate_source(read_json(source_path))
    manifest = read_json(manifest_path)
    keys(manifest, ("schema_version", "source_pot_audit_sha256", "reviewer_confirmed_offline", "hands"))
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
            manifest["source_pot_audit_sha256"] == source_hash and
            manifest["reviewer_confirmed_offline"] is True and
            type(manifest["hands"]) is list and len(manifest["hands"]) == len(source["hands"]),
            "Unconfirmed or unbound manual manifest")
    if recording_path is not None:
        require(sha256(recording_path) == source["recording_sha256"], "Recording hash mismatch")
    results = []
    for original, manual in zip(source["hands"], manifest["hands"]):
        keys(manual, ("hand_id", "table_id", "seat_count", "seats", "reviewer_notes"))
        count = manual["seat_count"]
        require(manual["hand_id"] == original["hand_id"] and
                type(manual["table_id"]) is int and manual["table_id"] == original["table_id"] and
                type(count) is int and 2 <= count <= 9 and
                type(manual["seats"]) is list and len(manual["seats"]) == count and
                type(manual["reviewer_notes"]) is str and
                1 <= len(manual["reviewer_notes"].strip()) <= 1000,
                "Invalid manual hand or seat count")
        seats, actors, flags = [], set(), list(original["blockers"])
        for item in manual["seats"]:
            keys(item, ("actor", "starting_stack", "net_contribution", "stack_after_contribution",
                        "state", "reviewer_note"))
            actor = item["actor"]
            require(type(actor) is str and ACTOR.fullmatch(actor) and actor not in actors and
                    (actor == "hero" or int(actor.split("_")[1]) <= count) and
                    item["state"] in STATES and type(item["reviewer_note"]) is str and
                    1 <= len(item["reviewer_note"].strip()) <= 500,
                    "Invalid seat identity/state/note")
            actors.add(actor)
            start, committed = chips(item["starting_stack"]), chips(item["net_contribution"])
            require(committed <= start, "Contribution exceeds starting stack")
            after = None if item["stack_after_contribution"] is None else chips(item["stack_after_contribution"])
            if after is not None:
                require(after == start - committed, "Pre-award stack does not reconcile")
            if item["state"] == "all_in":
                require(committed == start and start > 0, "All-in must exhaust declared starting stack")
            if item["state"] == "unknown":
                flags.append("seat_state_unknown")
            if after is None:
                flags.append("pre_award_stack_unverified")
            seats.append({"actor": actor, "starting_stack": start, "committed": committed,
                          "stack_after_contribution": after, "state": item["state"]})
        require("hero" in actors or actors == {f"seat_{i}" for i in range(1, count + 1)},
                "Ambiguous seat inventory")
        total = sum((s["committed"] for s in seats), Decimal(0))
        expected = sum((chips(original[f]) for f in ("reviewed_action_contributions",
                        "manual_forced_contributions", "manual_unobserved_contributions")), Decimal(0)) - \
                   chips(original["manual_returned_uncalled_bets"])
        if total != expected:
            flags.append("seat_total_vs_pot_audit_mismatch")
        tiers = side_pot_tiers(seats)
        require(sum((Decimal(t["amount"]) for t in tiers), Decimal(0)) == total,
                "Internal tier arithmetic mismatch")
        for t in tiers:
            if len(t["contributors"]) == 1:
                flags.append("single_contributor_top_layer_requires_refund_review")
            if not t["eligible_if_states_correct"] and not t["unknown_eligibility"]:
                flags.append("no_eligible_contender_in_layer")
            if t["unknown_eligibility"]:
                flags.append("layer_eligibility_uncertain")
        flags.append("human_seat_ledgers_not_independently_verified")
        results.append({"hand_id": original["hand_id"], "table_id": original["table_id"],
                        "declared_game_type": original["declared_game_type"],
                        "seat_count_human_supplied": count, "net_seat_contributions": str(total),
                        "net_pot_audit_contributions": str(expected),
                        "conditional_contribution_difference": str(total - expected),
                        "side_pot_tiers_conditional": tiers,
                        "blockers": sorted(set(flags)), "action_history_complete": False,
                        "side_pot_eligibility_verified": False, "ready_for_equity_or_ev": False})
    require(sha256(source_path) == source_hash and sha256(manifest_path) == manifest_hash,
            "Inputs changed during audit")
    if recording_path is not None:
        require(sha256(recording_path) == source["recording_sha256"], "Recording changed during audit")
    result = {"schema_version": 1, "analysis_status": "conditional_stack_sidepot_arithmetic_unverified",
              "source_pot_audit_sha256": source_hash, "source_seat_manifest_sha256": manifest_hash,
              "recording_sha256": source["recording_sha256"],
              "recording_hash_checked_in_this_run": recording_path is not None,
              "hands": results, "complete_hand_reconstructed": False,
              "ready_for_equity_or_ev": False, "automatic_clip_selection_authorized": False,
              "warning": "Manual seat hypotheses and side-pot arithmetic are not independent evidence; no equity/EV or automatic clips."}
    write_new(output, result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    t = sub.add_parser("template")
    t.add_argument("source")
    t.add_argument("output")
    a = sub.add_parser("audit")
    a.add_argument("source")
    a.add_argument("manifest")
    a.add_argument("output")
    a.add_argument("--recording")
    args = p.parse_args(argv)
    result = make_template(args.source, args.output) if args.command == "template" else \
             audit(args.source, args.manifest, args.output, recording_path=args.recording)
    print(json.dumps({"hands": len(result["hands"]),
                      "status": result.get("analysis_status", "unconfirmed_template")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
