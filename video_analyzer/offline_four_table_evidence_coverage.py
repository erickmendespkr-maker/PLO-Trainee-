"""Fail-closed offline cross-stage provenance and coverage audit for PLO5/PLO6.

Inputs: human-reviewed betting report, conditional pot report, human seat
manifest, conditional stack/side-pot report. This module does not prove any
hand complete, infer hidden cards, run equity/EV, or authorize clip selection.

Usage:
  python offline_four_table_evidence_coverage.py REVIEW.json POT.json SEATS.json STACK.json NEW.json [--recording MP4] [--gap-seconds 10]
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import math
from pathlib import Path

import offline_four_table_pot_gap_audit as pot_module
import offline_four_table_stack_sidepot_audit as stack_module

MAX_HANDS = 64


def check(condition, message):
    if not condition:
        raise ValueError(message)


def identity(h):
    return h["hand_id"], h["table_id"], h["declared_game_type"]


def validate_stack_report(stack):
    stack_module.keys(stack, ("schema_version", "analysis_status", "source_pot_audit_sha256",
        "source_seat_manifest_sha256", "recording_sha256", "recording_hash_checked_in_this_run",
        "hands", "complete_hand_reconstructed", "ready_for_equity_or_ev",
        "automatic_clip_selection_authorized", "warning"))
    check(type(stack["schema_version"]) is int and stack["schema_version"] == 1 and
          stack["analysis_status"] == "conditional_stack_sidepot_arithmetic_unverified" and
          stack["complete_hand_reconstructed"] is False and
          stack["ready_for_equity_or_ev"] is False and
          stack["automatic_clip_selection_authorized"] is False and
          type(stack["recording_hash_checked_in_this_run"]) is bool and
          type(stack["warning"]) is str, "Invalid stack report status")
    for k in ("source_pot_audit_sha256", "source_seat_manifest_sha256", "recording_sha256"):
        check(type(stack[k]) is str and stack_module.HASH.fullmatch(stack[k]), "Invalid stack hash")
    check(type(stack["hands"]) is list and 1 <= len(stack["hands"]) <= MAX_HANDS,
          "Invalid stack hand count")
    seen = set()
    for h in stack["hands"]:
        stack_module.keys(h, ("hand_id", "table_id", "declared_game_type", "seat_count_human_supplied",
            "net_seat_contributions", "net_pot_audit_contributions", "conditional_contribution_difference",
            "side_pot_tiers_conditional", "blockers", "action_history_complete",
            "side_pot_eligibility_verified", "ready_for_equity_or_ev"))
        ident = identity(h)
        check(ident not in seen and type(ident[0]) is str and stack_module.ID.fullmatch(ident[0]) and
              type(ident[1]) is int and 1 <= ident[1] <= 4 and ident[2] in ("PLO5", "PLO6") and
              type(h["seat_count_human_supplied"]) is int and 2 <= h["seat_count_human_supplied"] <= 9 and
              type(h["blockers"]) is list and all(type(x) is str for x in h["blockers"]) and
              h["action_history_complete"] is False and h["side_pot_eligibility_verified"] is False and
              h["ready_for_equity_or_ev"] is False, "Invalid stack hand")
        seen.add(ident)
        for k in ("net_seat_contributions", "net_pot_audit_contributions"):
            stack_module.chips(h[k])
        check(type(h["conditional_contribution_difference"]) is str and
              stack_module.re.fullmatch(r"-?\d+(?:\.\d{1,2})?", h["conditional_contribution_difference"]) and
              Decimal(h["conditional_contribution_difference"]) ==
              Decimal(h["net_seat_contributions"]) - Decimal(h["net_pot_audit_contributions"]),
              "Stack contribution difference mismatch")
        check(type(h["side_pot_tiers_conditional"]) is list, "Invalid tier list")
    return stack


def checked_manifest(manifest, pot_hash, pot_hands, stack_hands):
    stack_module.keys(manifest, ("schema_version", "source_pot_audit_sha256",
                                   "reviewer_confirmed_offline", "hands"))
    check(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
          manifest["source_pot_audit_sha256"] == pot_hash and
          manifest["reviewer_confirmed_offline"] is True and
          type(manifest["hands"]) is list and len(manifest["hands"]) == len(pot_hands),
          "Invalid seat manifest binding")
    for p, s, m in zip(pot_hands, stack_hands, manifest["hands"]):
        stack_module.keys(m, ("hand_id", "table_id", "seat_count", "seats", "reviewer_notes"))
        check((m["hand_id"], m["table_id"]) == (p["hand_id"], p["table_id"]) and
              type(m["table_id"]) is int and type(m["seat_count"]) is int and
              m["seat_count"] == s["seat_count_human_supplied"] and
              type(m["seats"]) is list and len(m["seats"]) == m["seat_count"] and
              type(m["reviewer_notes"]) is str and 1 <= len(m["reviewer_notes"].strip()) <= 1000,
              "Seat manifest hand mismatch")
        actors, tiers_input = set(), []
        for seat in m["seats"]:
            stack_module.keys(seat, ("actor", "starting_stack", "net_contribution",
                "stack_after_contribution", "state", "reviewer_note"))
            actor = seat["actor"]
            check(type(actor) is str and stack_module.ACTOR.fullmatch(actor) and actor not in actors and
                  (actor == "hero" or int(actor.split("_")[1]) <= m["seat_count"]) and
                  seat["state"] in stack_module.STATES and
                  type(seat["reviewer_note"]) is str and 1 <= len(seat["reviewer_note"].strip()) <= 500,
                  "Invalid seat identity")
            actors.add(actor)
            start, net = stack_module.chips(seat["starting_stack"]), stack_module.chips(seat["net_contribution"])
            check(net <= start, "Contribution exceeds stack")
            if seat["stack_after_contribution"] is not None:
                check(stack_module.chips(seat["stack_after_contribution"]) == start - net,
                      "Seat balance mismatch")
            if seat["state"] == "all_in":
                check(start > 0 and net == start, "Invalid all-in balance")
            tiers_input.append({"actor": actor, "committed": net, "state": seat["state"]})
        check("hero" in actors or actors == {f"seat_{i}" for i in range(1, m["seat_count"] + 1)},
              "Ambiguous seat inventory")
        total = sum((x["committed"] for x in tiers_input), Decimal(0))
        expected = sum((stack_module.chips(p[k]) for k in ("reviewed_action_contributions",
            "manual_forced_contributions", "manual_unobserved_contributions")), Decimal(0)) - \
            stack_module.chips(p["manual_returned_uncalled_bets"])
        check(total == Decimal(s["net_seat_contributions"]) and
              expected == Decimal(s["net_pot_audit_contributions"]), "Seat or pot totals changed")
        tiers = stack_module.side_pot_tiers(tiers_input)
        check(tiers == s["side_pot_tiers_conditional"], "Conditional tiers changed")
    return manifest


def audit(review_path, pot_path, seats_path, stack_path, output_path, *, recording_path=None,
          gap_seconds=10.0):
    check(type(gap_seconds) in (float, int) and math.isfinite(gap_seconds) and 0 < gap_seconds <= 3600,
          "Invalid gap threshold")
    sources = [Path(x) for x in (review_path, pot_path, seats_path, stack_path)]
    if recording_path is not None:
        sources.append(Path(recording_path))
    output = stack_module.safe_output(output_path, sources)
    before = [stack_module.sha256(p) for p in sources]
    review = pot_module.validate_review(stack_module.read_json(sources[0]))
    pot = stack_module.validate_source(stack_module.read_json(sources[1]))
    manifest = stack_module.read_json(sources[2])
    stack = validate_stack_report(stack_module.read_json(sources[3]))
    check(pot["source_betting_review_sha256"] == before[0] and
          stack["source_pot_audit_sha256"] == before[1] and
          stack["source_seat_manifest_sha256"] == before[2], "Cross-stage SHA-256 chain mismatch")
    checked_manifest(manifest, before[1], pot["hands"], stack["hands"])
    check(len(review["hands"]) == len(pot["hands"]) == len(stack["hands"]),
          "Cross-stage hand count mismatch")
    recording_hash = review["recording_sha256"]
    check(recording_hash == pot["recording_sha256"] == stack["recording_sha256"],
          "Recording identity mismatch")
    if recording_path is not None:
        check(before[4] == recording_hash, "Recording content mismatch")
    hands = []
    for r, p, m, s in zip(review["hands"], pot["hands"], manifest["hands"], stack["hands"]):
        check(identity(r) == identity(p) == identity(s) and
              (m["hand_id"], m["table_id"]) == (r["hand_id"], r["table_id"]) and
              len(r["actions"]) == p["observed_action_count"], "Hand identity/count mismatch")
        observed = {x["actor"]: Decimal(0) for x in m["seats"]}
        evidence = []
        flags = set(p["blockers"]) | set(s["blockers"])
        timestamps = []
        for a in r["actions"]:
            actor = a["actor_human_assigned"]
            check(actor in observed, "Reviewed actor absent from seat inventory")
            value = Decimal(a["amount_contributed_human_assigned"] or "0")
            observed[actor] += value
            timestamps.append(float(a["pts_seconds"]))
            evidence.append({"source_observation_index": a["source_observation_index"],
                "pts_seconds": a["pts_seconds"], "actor_human_assigned": actor,
                "street_human_assigned": a["street_human_assigned"],
                "action_label_as_observed": a["action_label_as_observed"],
                "amount_contributed_human_assigned": a["amount_contributed_human_assigned"],
                "reviewed_betting_report_sha256": before[0],
                "independent_visual_verification": False})
        check(sum(observed.values(), Decimal(0)) == stack_module.chips(p["reviewed_action_contributions"]),
              "Observed action total inconsistent with pot report")
        gaps = [{"start_pts_seconds": a, "end_pts_seconds": b, "duration_seconds": round(b-a, 6)}
                for a, b in zip(timestamps, timestamps[1:]) if b-a > gap_seconds]
        if gaps:
            flags.add("long_interval_without_reviewed_action_not_proof_of_missing_action")
        if stack_module.chips(p["manual_forced_contributions"]) > 0 or \
           stack_module.chips(p["manual_unobserved_contributions"]) > 0 or \
           stack_module.chips(p["manual_returned_uncalled_bets"]) > 0:
            flags.add("manual_pot_adjustments_not_tied_to_visual_timestamps")
        seats = []
        for seat in m["seats"]:
            actor = seat["actor"]
            net = stack_module.chips(seat["net_contribution"])
            delta = net - observed[actor]
            labels = [a["action_label_as_observed"] for a in evidence if a["actor_human_assigned"] == actor]
            if delta != 0:
                flags.add("seat_net_contribution_not_reconciled_with_reviewed_actions")
            if seat["state"] == "all_in" and "all-in" not in labels:
                flags.add("all_in_state_without_observed_all_in_label")
            if "all-in" in labels and seat["state"] != "all_in":
                flags.add("observed_all_in_label_disagrees_with_seat_state")
            if seat["state"] == "unknown":
                flags.add("seat_state_unknown")
            seats.append({"actor": actor, "state_human_supplied": seat["state"],
                "observed_action_contribution": str(observed[actor]),
                "net_seat_contribution_human_supplied": str(net),
                "unexplained_seat_minus_observed": str(delta),
                "observed_action_indices": [a["source_observation_index"] for a in evidence
                                            if a["actor_human_assigned"] == actor],
                "state_visually_verified": False})
        flags.update(("action_coverage_unverified", "visual_evidence_not_independently_verified",
                      "opponent_ranges_not_verified"))
        hands.append({"hand_id": r["hand_id"], "table_id": r["table_id"],
            "declared_game_type": r["declared_game_type"],
            "reviewed_action_evidence": evidence,
            "time_range_of_reviewed_actions": [timestamps[0], timestamps[-1]] if timestamps else None,
            "long_intervals_between_reviewed_actions": gaps,
            "seat_coverage": seats, "blockers": sorted(flags),
            "complete_hand_reconstructed": False, "action_history_complete": False,
            "ready_for_equity_or_ev": False, "automatic_clip_selection_authorized": False})
    check([stack_module.sha256(p) for p in sources] == before, "Inputs changed during audit")
    result = {"schema_version": 1, "analysis_status": "cross_stage_evidence_coverage_unverified",
        "source_betting_review_sha256": before[0], "source_pot_audit_sha256": before[1],
        "source_seat_manifest_sha256": before[2], "source_stack_audit_sha256": before[3],
        "recording_sha256": recording_hash,
        "recording_hash_checked_in_this_run": recording_path is not None,
        "gap_threshold_seconds": float(gap_seconds), "hands": hands,
        "complete_hand_reconstructed": False, "ready_for_equity_or_ev": False,
        "automatic_clip_selection_authorized": False,
        "warning": "Only reviewed-action provenance and conditional arithmetic are compared. Missing observations and manual seat hypotheses remain unverified."}
    stack_module.write_new(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("review", "pot", "seats", "stack", "output"):
        parser.add_argument(name)
    parser.add_argument("--recording")
    parser.add_argument("--gap-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    result = audit(args.review, args.pot, args.seats, args.stack, args.output,
                   recording_path=args.recording, gap_seconds=args.gap_seconds)
    print(json.dumps({"hands": len(result["hands"]), "status": result["analysis_status"],
                      "equity_or_ev_authorized": result["ready_for_equity_or_ev"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())