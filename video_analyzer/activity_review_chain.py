"""Hash-bound, human-gated bridge from offline activity OCR to hand observations.

No action, card, pot, hand or mathematical input is inferred from OCR. All
human approvals must be explicit; frame hashes and decoded PTS are audited.
"""
import hashlib
import json
from pathlib import Path

from activity_ocr_bridge import prepare_activity_ocr_jobs
from review_packet import build_review_packet
from reviewed_ocr_bridge import bridge_reviewed_ocr


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _validate_candidates(report, plan):
    if (not isinstance(report, dict) or report.get('schema_version') != 1
            or report.get('analysis_status') != 'unverified_ocr_candidates_only'
            or report.get('requires_manual_review') is not True
            or report.get('ready_for_equity_or_ev') is not False
            or report.get('evidence_manifest_sha256') != plan['evidence_manifest_sha256']
            or report.get('recording_sha256') != plan['recording_sha256']):
        raise ValueError('OCR report does not match audited activity evidence')
    rows = report.get('candidates')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Invalid OCR candidates')
    if len(rows) != len(plan['jobs']):
        raise ValueError('OCR candidate count differs from audited OCR plan')
    expected = {}
    for job in plan['jobs']:
        key = (job['table_id'], job['field'], job['source_image'])
        if key in expected:
            raise ValueError('Duplicate OCR job')
        expected[key] = job
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid OCR candidate')
        key = (row.get('table_id'), row.get('field'), row.get('source_image'))
        if key not in expected or key in seen:
            raise ValueError('Unrecognized or repeated OCR source')
        seen.add(key)
        job = expected[key]
        for field in ('source_sha256', 'source_pts_ticks', 'timestamp',
                      'requested_seeks', 'seek_reasons'):
            if type(row.get(field)) is not type(job[field]) or row[field] != job[field]:
                raise ValueError(f'OCR source mismatch: {field}')
        if (row.get('evidence_manifest_sha256') != plan['evidence_manifest_sha256']
                or row.get('timestamp_semantics') != plan['timestamp_semantics']
                or row.get('status') not in ('candidate_unverified', 'needs_manual_review')):
            raise ValueError('OCR provenance/status mismatch')
    return True


def _read_and_validate(evidence_dir, roi_manifest, ocr_report):
    # prepare_activity_ocr_jobs re-audits all image bytes and the manifest.
    plan = prepare_activity_ocr_jobs(evidence_dir, roi_manifest)
    _validate_candidates(ocr_report, plan)
    return plan


def create_activity_review_template(evidence_dir, roi_manifest, ocr_report):
    """Generate unapproved forms bound to the exact OCR report and source bytes."""
    plan = _read_and_validate(evidence_dir, roi_manifest, ocr_report)
    template = build_review_packet(ocr_report)
    template.update({
        'analysis_status': 'unapproved_activity_review_template',
        'ocr_report_sha256': _digest(ocr_report),
        'evidence_manifest_sha256': plan['evidence_manifest_sha256'],
        'recording_sha256': plan['recording_sha256'],
        'timestamp_semantics': plan['timestamp_semantics'],
        'ready_for_equity_or_ev': False,
        'warning': ('No OCR field, hand ID or action is approved. Explicit human review '
                    'and source integrity verification are required.'),
    })
    return template


def bridge_activity_review(evidence_dir, roi_manifest, ocr_report, human_review):
    """Verify source hashes + review binding before producing reviewed observations.

    Still does NOT certify accuracy of manual labels or authorize equity/EV.
    """
    expected = create_activity_review_template(evidence_dir, roi_manifest, ocr_report)
    if not isinstance(human_review, dict):
        raise ValueError('Invalid human review')
    for field in ('ocr_report_sha256', 'evidence_manifest_sha256',
                  'recording_sha256', 'timestamp_semantics'):
        if human_review.get(field) != expected[field]:
            raise ValueError(f'Review binding mismatch: {field}')
    submitted = human_review.get('events')
    reference = expected['events']
    if not isinstance(submitted, list) or len(submitted) != len(reference):
        raise ValueError('Review must account for every OCR frame/field')
    for actual, baseline in zip(submitted, reference):
        if not isinstance(actual, dict):
            raise ValueError('Invalid review event')
        for field in ('table_id', 'timestamp'):
            if type(actual.get(field)) is not type(baseline[field]) or actual[field] != baseline[field]:
                raise ValueError('Review event table or decoded PTS changed')
        fields = actual.get('field_reviews')
        if not isinstance(fields, dict) or set(fields) != set(baseline['field_reviews']):
            raise ValueError('Review fields do not match OCR source')
        for name, original in baseline['field_reviews'].items():
            if not isinstance(fields[name], dict) or type(fields[name].get('candidate_index')) is not int or fields[name]['candidate_index'] != original['candidate_index']:
                raise ValueError('Review candidate index changed')
        if actual.get('human_confirmed') is not True:
            raise ValueError('Human approval required for every reviewed event')
    # Exact decoded PTS matching (no cross-frame or nearby-time joins).
    reviewed = bridge_reviewed_ocr(ocr_report, human_review, max_time_delta=0.0)
    reviewed.update({
        'analysis_status': 'human_reviewed_activity_observations',
        'ocr_report_sha256': expected['ocr_report_sha256'],
        'evidence_manifest_sha256': expected['evidence_manifest_sha256'],
        'recording_sha256': expected['recording_sha256'],
        'timestamp_semantics': expected['timestamp_semantics'],
        'ready_for_equity_or_ev': False,
        'warning': ('Manual approval is not ground-truth accuracy. Do not infer hidden cards, '
                    'opponent ranges or EV from this report.'),
    })
    return reviewed


def run_activity_review(evidence_dir, roi_manifest, ocr_path, output_path,
                        *, human_review_path=None):
    """Write a new JSON review template or a validated human-reviewed report."""
    ocr = json.loads(Path(ocr_path).read_text(encoding='utf-8'))
    if human_review_path is None:
        result = create_activity_review_template(evidence_dir, roi_manifest, ocr)
    else:
        review = json.loads(Path(human_review_path).read_text(encoding='utf-8'))
        result = bridge_activity_review(evidence_dir, roi_manifest, ocr, review)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence_dir')
    parser.add_argument('manual_rois_json')
    parser.add_argument('ocr_report_json')
    parser.add_argument('output_json')
    parser.add_argument('--human-review', help='Optional explicitly approved review JSON')
    args = parser.parse_args()
    result = run_activity_review(args.evidence_dir, args.manual_rois_json,
                                 args.ocr_report_json, args.output_json,
                                 human_review_path=args.human_review)
    print(json.dumps({'status': result['analysis_status'],
                      'events': len(result['events']) if 'events' in result else len(result['observations'])}))
