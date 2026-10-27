"""Offline human review of OCR proposals; never promotes observations to complete hands.

Usage: python offline_four_table_ocr_human_review.py BUNDLE OCR_JSON REVIEW_JSON NEW_OUTPUT_JSON
Review manifest schema v1: {schema_version, source_ocr_sha256, decisions:[
 {candidate_index, decision: confirm|correct|reject, reviewed_text: str|null,
  visual_evidence_checked: bool, note: str}]}.
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

from offline_four_table_sample_review import verify_bundle
from offline_four_table_ocr_proposals import FIELDS, STATUS as OCR_STATUS

MAX_BYTES = 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
CARD = re.compile(r"[2-9TJQKA][cdhs]\Z")
AMOUNT = re.compile(r"(?:0|[1-9]\d{0,8})(?:\.\d{1,2})?\Z")
ACTIONS = frozenset({"fold", "check", "call", "bet", "raise", "all-in"})


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "Duplicate JSON key")
        out[key] = value
    return out


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_BYTES,
            "Invalid or oversized input")
    return json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def normalize(field, value):
    require(type(value) is str and 0 < len(value) <= 128 and
            all(32 <= ord(ch) <= 126 for ch in value), "Invalid reviewed text")
    value = value.strip()
    if field in ("hero_cards", "board"):
        cards = value.split()
        require((len(cards) in (5, 6) if field == "hero_cards" else 1 <= len(cards) <= 5)
                and all(CARD.fullmatch(c) for c in cards) and
                len(set(cards)) == len(cards), "Invalid visible cards")
        return " ".join(cards)
    if field in ("pot", "bet", "stack"):
        require(bool(AMOUNT.fullmatch(value)), "Invalid amount")
        return value
    require(field == "action" and value.lower() in ACTIONS, "Invalid action")
    return value.lower()


def review(bundle_path, ocr_path, decisions_path, output_path, *, recording_path=None):
    bundle, ocr_file, decision_file, output = map(
        Path, (bundle_path, ocr_path, decisions_path, output_path))
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink(), "Output must be new")
    require(not output.resolve().is_relative_to(bundle.resolve()),
            "Output must be outside source bundle")
    source = verify_bundle(bundle, recording_path)
    ocr, edits = read(ocr_file), read(decision_file)
    ocr_sha, edits_sha = sha(ocr_file), sha(decision_file)
    require(type(ocr) is dict and ocr.get("schema_version") == 1 and
            ocr.get("analysis_status") == OCR_STATUS and
            ocr.get("ready_for_equity_or_ev") is False and
            ocr.get("requires_manual_review") is True and
            ocr.get("recording_sha256") == source["recording_sha256"] and
            ocr.get("source_region_samples_sha256") == sha(bundle / "region_samples.json"),
            "OCR report does not bind to verified source")
    candidates = ocr.get("candidates")
    require(type(candidates) is list and 1 <= len(candidates) <= 32,
            "Invalid OCR candidate count")
    require(type(edits) is dict and set(edits) ==
            {"schema_version", "source_ocr_sha256", "decisions"} and
            type(edits["schema_version"]) is int and edits["schema_version"] == 1 and
            edits["source_ocr_sha256"] == ocr_sha and
            type(edits["decisions"]) is list and
            len(edits["decisions"]) == len(candidates), "Invalid review binding or coverage")
    verified = []
    for index, (candidate, edit) in enumerate(zip(candidates, edits["decisions"])):
        require(type(candidate) is dict and candidate.get("status") == "needs_manual_review" and
                candidate.get("parsed_candidate") is None and
                candidate.get("field") in FIELDS, "Invalid OCR candidate")
        table, sample = candidate.get("table_id"), candidate.get("sample_index")
        require(type(table) is int and 1 <= table <= 4 and type(sample) is int and
                0 <= sample < len(source["samples"]), "Invalid OCR identity")
        frame = source["samples"][sample]
        crops = [c for c in frame["table_crops"] if c["table_id"] == table]
        require(len(crops) == 1 and candidate.get("source_crop_path") == crops[0]["path"] and
                candidate.get("source_crop_sha256") == crops[0]["sha256"] and
                candidate.get("decoded_source_pts_seconds") == frame["decoded_source_pts_seconds"],
                "OCR candidate not bound to verified frame")
        require(type(edit) is dict and set(edit) ==
                {"candidate_index", "decision", "reviewed_text", "visual_evidence_checked", "note"} and
                type(edit["candidate_index"]) is int and edit["candidate_index"] == index and
                edit["decision"] in ("confirm", "correct", "reject") and
                type(edit["visual_evidence_checked"]) is bool and
                type(edit["note"]) is str and len(edit["note"]) <= 512,
                "Invalid review entry")
        if edit["decision"] == "reject":
            require(edit["reviewed_text"] is None, "Rejected observation must not carry a value")
            value = None
        else:
            require(edit["visual_evidence_checked"] is True, "Visual evidence must be checked")
            value = normalize(candidate["field"], edit["reviewed_text"])
            if edit["decision"] == "confirm":
                require(value == candidate.get("raw_ocr_text", "").strip(),
                        "Confirmation must match OCR exactly; use correct instead")
        verified.append({"candidate_index": index, "table_id": table,
                         "sample_index": sample, "field": candidate["field"],
                         "decoded_source_pts_seconds": frame["decoded_source_pts_seconds"],
                         "source_crop_path": crops[0]["path"],
                         "source_crop_sha256": crops[0]["sha256"],
                         "review_decision": edit["decision"],
                         "visual_evidence_checked": edit["visual_evidence_checked"],
                         "reviewed_value": value, "note": edit["note"]})
    require(sha(ocr_file) == ocr_sha and sha(decision_file) == edits_sha,
            "Input changed during review")
    verify_bundle(bundle, recording_path)
    result = {"schema_version": 1, "status": "human_reviewed_ocr_fields_only",
              "source_ocr_sha256": ocr_sha, "review_manifest_sha256": edits_sha,
              "source_region_samples_sha256": ocr["source_region_samples_sha256"],
              "recording_sha256": source["recording_sha256"],
              "ready_for_equity_or_ev": False, "complete_hand_reconstructed": False,
              "reviewer_identity_authenticated": False, "reviewed_candidates": verified,
              "warning": "Manual field review only; no inferred hidden cards, ranges or hand actions."}
    with tempfile.TemporaryDirectory(prefix="plo_ocr_review_", dir=output.parent) as temp:
        stage = Path(temp) / "review.json"
        stage.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n", encoding="utf-8")
        os.link(stage, output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    parser.add_argument("ocr_report")
    parser.add_argument("review_manifest")
    parser.add_argument("new_output_json")
    parser.add_argument("--recording")
    args = parser.parse_args(argv)
    result = review(args.bundle, args.ocr_report, args.review_manifest,
                    args.new_output_json, recording_path=args.recording)
    print(json.dumps({"status": result["status"],
                      "count": len(result["reviewed_candidates"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
