# OCR adjudication — offline protocol (cycle 36)

Scope: review of recorded PLO5/PLO6 frames only. This workflow never captures live play, infers hidden cards as facts, or makes automated betting decisions.

## Procedure

1. Extract hash-bound evidence and create a blank OCR benchmark template.
2. Obtain two separate human annotation exports without showing OCR suggestions.
3. Run `ocr_label_consensus.py` to retain matching labels and identify conflicts or missing labels.
4. Run `ocr_adjudication.py prepare EVIDENCE_DIR A.json B.json review.json` to create a third-reviewer template containing only pending rows.
5. The adjudicator opens each referenced frame and explicitly sets `review_status=human_adjudicated` and a valid `expected` value, or leaves it pending. No values are filled automatically.
6. Run `ocr_adjudication.py apply EVIDENCE_DIR A.json B.json review_filled.json merged.json audit.json` to create a benchmark-ready template and a separate provenance audit.
7. Run `ocr_ground_truth_benchmark.py score EVIDENCE_DIR merged.json ocr_candidates.json metrics.json` to calculate OCR metrics **only for labeled samples**.

All source images are checked against SHA-256 and decoded presentation timestamps; all annotation pairs are bound by a canonical digest. Any changed source, sample identity, row order, or unexpected OCR field is rejected. SHA-256 does not prove original capture or the independence of reviewers.

## Limitations

This component was tested with synthetic video frames. Human annotations in demonstrations are synthetic, not verified poker ground truth. Missing/conflicting rows stay unscored until reviewed. Wilson intervals quantify sampling uncertainty only; they do not measure visual model calibration or strategic accuracy. A real, authorized 3–5-minute sample remains required for quantitative validation.

The local `ocr_adjudication.py` module and tests must be synchronized to the feature branch before the commands above can run from a fresh GitHub checkout. Do not interpret documentation-only commits as code deployment.
