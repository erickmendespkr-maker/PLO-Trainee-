"""Offline, non-authoritative hand-boundary evaluation against human annotations.

Usage: python offline_hand_boundary_benchmark.py proposals.json labels.json new_report.json

This is a *measurement tool*, not a detector: it never infers hands from video,
never authorizes poker equity/EV, and does not verify annotation correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 512
MAX_DURATION = 14_400
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
Z95 = 1.959963984540054


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def load(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_BYTES, "invalid input JSON")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _number(value, minimum, maximum, label):
    require(type(value) in (int, float) and math.isfinite(value) and
            minimum <= value <= maximum, f"invalid {label}")
    return float(value)


def _intervals(rows, *, human):
    require(type(rows) is list and len(rows) <= MAX_ROWS, "invalid boundary list")
    seen = set()
    result = {t: [] for t in range(1, 5)}
    for index, item in enumerate(rows):
        require(type(item) is dict and type(item.get("table_id")) is int and
                1 <= item["table_id"] <= 4, "invalid table_id")
        start = _number(item.get("start_seconds"), 0, MAX_DURATION, "start")
        end = _number(item.get("end_seconds"), 0, MAX_DURATION, "end")
        require(end - start >= 0.05, "hand boundary interval too short")
        key = (item["table_id"], start, end)
        require(key not in seen, "duplicate boundary")
        seen.add(key)
        if human:
            require(set(item) == {"table_id", "start_seconds", "end_seconds"},
                    "invalid human annotation fields")
        else:
            require(set(item).issubset({"table_id", "start_seconds", "end_seconds",
                                        "status", "confidence_uncalibrated",
                                        "source_sample_indices"}) and
                    {"table_id", "start_seconds", "end_seconds", "status"}.issubset(item),
                    "invalid candidate fields")
            require(item["status"] == "needs_manual_review", "unreviewed proposal required")
            if "confidence_uncalibrated" in item:
                _number(item["confidence_uncalibrated"], 0, 1, "uncalibrated confidence")
            if "source_sample_indices" in item:
                indices = item["source_sample_indices"]
                require(type(indices) is list and 1 <= len(indices) <= 128 and
                        all(type(i) is int and i >= 0 for i in indices) and
                        len(set(indices)) == len(indices), "invalid source sample indices")
        result[item["table_id"]].append((start, end, index))
    for table in result:
        result[table].sort()
        require(all(result[table][i][0] >= result[table][i-1][1]
                    for i in range(1, len(result[table]))),
                "overlapping hand intervals on one table")
    return result


def _validate(proposals, labels):
    require(type(proposals) is dict and
            set(proposals) == {"schema_version", "status", "ready_for_equity_or_ev",
                               "recording_sha256", "boundaries"} and
            type(proposals["schema_version"]) is int and proposals["schema_version"] == 1 and
            proposals["status"] == "unverified_offline_hand_boundary_proposals" and
            proposals["ready_for_equity_or_ev"] is False,
            "invalid or promoted candidate report")
    require(type(labels) is dict and
            set(labels) == {"schema_version", "status", "recording_sha256", "hands"} and
            type(labels["schema_version"]) is int and labels["schema_version"] == 1 and
            labels["status"] == "human_annotated_hand_boundaries", "invalid label report")
    for source in (proposals, labels):
        require(type(source["recording_sha256"]) is str and
                SHA256.fullmatch(source["recording_sha256"]), "invalid recording SHA")
    require(proposals["recording_sha256"] == labels["recording_sha256"],
            "candidate/label recordings differ")
    return (_intervals(proposals["boundaries"], human=False),
            _intervals(labels["hands"], human=True))


def wilson(success, total):
    if total == 0:
        return None
    p = success / total
    denom = 1 + Z95**2 / total
    center = (p + Z95**2 / (2 * total)) / denom
    radius = Z95 / denom * math.sqrt(p * (1-p) / total + Z95**2 / (4 * total**2))
    return [max(0.0, center-radius), min(1.0, center+radius)]


def _match(pred, gold, tolerance):
    """Maximum noncrossing matches; among ties minimize total endpoint error.

    Both interval sequences are nonoverlapping and sorted by start.
    Dynamic programming enforces one-to-one temporal correspondence.
    """
    n, m = len(pred), len(gold)
    dp = [[(0, 0.0) for _ in range(m+1)] for _ in range(n+1)]
    moves = [[None for _ in range(m+1)] for _ in range(n+1)]
    for i in range(n-1, -1, -1):
        for j in range(m-1, -1, -1):
            choices = [(dp[i+1][j], "skip_prediction"),
                       (dp[i][j+1], "skip_label")]
            ds = abs(pred[i][0] - gold[j][0])
            de = abs(pred[i][1] - gold[j][1])
            if ds <= tolerance + 1e-9 and de <= tolerance + 1e-9:
                k, neg_error = dp[i+1][j+1]
                choices.append(((k+1, neg_error-ds-de), "match"))
            # Stable preference for match on exact ties, without sacrificing
            # maximum cardinality or smaller total endpoint error.
            score, move = max(choices, key=lambda x: (x[0][0], x[0][1],
                                                     x[1] == "match",
                                                     x[1] == "skip_label"))
            dp[i][j], moves[i][j] = score, move
    pairs = []
    i = j = 0
    while i < n and j < m:
        move = moves[i][j]
        if move == "match":
            pairs.append((pred[i], gold[j]))
            i += 1
            j += 1
        elif move == "skip_prediction":
            i += 1
        else:
            j += 1
    return pairs


def evaluate(proposals, labels, *, tolerance_seconds=0.5):
    tolerance = _number(tolerance_seconds, 0, 30, "tolerance_seconds")
    predictions, truth = _validate(proposals, labels)
    by_table, matched_details = [], []
    total_pred = total_gold = total_match = 0
    for table in range(1, 5):
        pred, gold = predictions[table], truth[table]
        matches = _match(pred, gold, tolerance)
        count = len(matches)
        total_pred += len(pred)
        total_gold += len(gold)
        total_match += count
        by_table.append({"table_id": table, "proposals": len(pred),
                         "human_hands": len(gold), "matched": count,
                         "false_positive_proposals": len(pred)-count,
                         "missed_human_hands": len(gold)-count,
                         "precision": count/len(pred) if pred else None,
                         "recall": count/len(gold) if gold else None})
        for p, g in matches:
            matched_details.append({"table_id": table, "proposal_index": p[2],
                                    "human_index": g[2],
                                    "start_error_seconds": round(p[0]-g[0], 9),
                                    "end_error_seconds": round(p[1]-g[1], 9)})
    return {
        "schema_version": 1,
        "status": "offline_boundary_label_agreement_only_not_real_video_accuracy",
        "recording_sha256_claim": proposals["recording_sha256"],
        "tolerance_seconds": tolerance,
        "matching_strategy": "one_to_one_max_cardinality_min_endpoint_error_noncrossing",
        "summary": {"proposals": total_pred, "human_hands": total_gold,
                    "matched": total_match,
                    "false_positive_proposals": total_pred-total_match,
                    "missed_human_hands": total_gold-total_match,
                    "precision": total_match/total_pred if total_pred else None,
                    "recall": total_match/total_gold if total_gold else None,
                    "precision_wilson95": wilson(total_match, total_pred),
                    "recall_wilson95": wilson(total_match, total_gold),
                    "f1": (2*total_match/(total_pred+total_gold)
                           if total_pred+total_gold else None)},
        "by_table": by_table,
        "matches": sorted(matched_details, key=lambda x: (x["table_id"], x["human_index"])),
        "human_labels_verified_against_video": False,
        "proposal_confidence_calibrated": False,
        "hands_reconstructed": False,
        "ready_for_equity_or_ev": False,
        "limitations": [
            "Synthetic or supplied-label agreement is not real-video accuracy.",
            "Recording SHA-256 is a claim shared by input manifests, not verified against video bytes.",
            "Unmatched proposals are false positives; unmatched labels are misses.",
            "Wilson intervals describe finite sample uncertainty, not label validity.",
            "This evaluator does not detect hands, validate cards, or authorize equity/EV."]}


def run(proposals_path, labels_path, output_path, *, tolerance_seconds=0.5):
    proposals_path, labels_path, output_path = map(Path, (proposals_path, labels_path, output_path))
    require(output_path.parent.is_dir() and not output_path.parent.is_symlink() and
            not output_path.exists() and not output_path.is_symlink() and
            len({str(p.resolve()) for p in (proposals_path, labels_path, output_path)}) == 3,
            "output must be new and distinct")
    before = sha256(proposals_path), sha256(labels_path)
    result = evaluate(load(proposals_path), load(labels_path),
                      tolerance_seconds=tolerance_seconds)
    require((sha256(proposals_path), sha256(labels_path)) == before,
            "inputs changed during evaluation")
    result["source_proposals_sha256"] = before[0]
    result["source_human_labels_sha256"] = before[1]
    with tempfile.TemporaryDirectory(prefix=".plo_boundary_eval_", dir=output_path.parent) as folder:
        stage = Path(folder) / "report.json"
        stage.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n", encoding="utf-8")
        os.link(stage, output_path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposals_json")
    parser.add_argument("human_labels_json")
    parser.add_argument("new_output_json")
    parser.add_argument("--tolerance-seconds", type=float, default=0.5)
    args = parser.parse_args(argv)
    report = run(args.proposals_json, args.human_labels_json, args.new_output_json,
                 tolerance_seconds=args.tolerance_seconds)
    print(json.dumps({"matched": report["summary"]["matched"],
                      "precision": report["summary"]["precision"],
                      "recall": report["summary"]["recall"],
                      "ready_for_equity_or_ev": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
