"""Fail-closed, offline review checklist for nominal PLO5/PLO6 evidence dossiers.

Only generates human review tasks. Never infers cards, reconstructs a hand,
verifies source PTS, authorizes mathematical calculations, or selects clips.
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

FIELDS = ('hero_cards', 'board', 'pot', 'bet')
STATUSES = ('confirmed', 'corrected', 'uncertain', 'rejected', 'pending')
FALSE_FLAGS = ('hand_start_or_end_pts_verified', 'hand_reconstruction_verified',
               'ready_for_equity_or_ev', 'automatic_clip_selection_authorized')
SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_DOSSIERS = 2000
MAX_OBSERVATIONS = 20_000


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(value):
    _require(type(value) is str and SHA.fullmatch(value) is not None, 'Invalid SHA-256')
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _false_gates(value):
    _require(all(value.get(flag) is False for flag in FALSE_FLAGS),
             'Unverified dossier cannot claim mathematical authority')


def validate_dossiers(report):
    """Validate report consistency, NOT authenticity of its underlying evidence.

    Authentic provenance must be established upstream with dossiers_job(),
    which re-audits the original recording and its derived artifacts.
    """
    _require(type(report) is dict and report.get('schema_version') == 1 and
             type(report.get('schema_version')) is int and
             report.get('analysis_status') == 'reviewed_nominal_interval_evidence_dossiers_no_math',
             'Unexpected dossier schema/status')
    _false_gates(report)
    _require(report.get('timestamp_semantics') == 'nominal_sampling_grid_not_exact_source_pts'
             and report.get('requires_manual_hand_reconstruction') is True,
             'Unexpected timestamp semantics')
    for key in ('source_sha256', 'source_timeline_sha256', 'source_intervals_sha256',
                'source_windows_sha256'):
        _sha(report.get(key))
    _require(type(report.get('job_id')) is str and
             re.fullmatch(r'[0-9a-f]{32}', report['job_id']) is not None, 'Invalid job ID')
    dossiers = report.get('dossiers')
    _require(type(dossiers) is list and len(dossiers) <= MAX_DOSSIERS, 'Invalid dossier count')
    counts = report.get('counts')
    _require(type(counts) is dict and counts.get('dossiers') == len(dossiers)
             and type(counts.get('dossiers')) is int and counts.get('math_ready') == 0
             and type(counts.get('math_ready')) is int, 'Invalid dossier counts')
    seen_hands, seen_evidence = set(), set()
    total = 0
    for hand in dossiers:
        _require(type(hand) is dict, 'Malformed dossier')
        _false_gates(hand)
        table, label = hand.get('table_id'), hand.get('hand_label_human_assigned')
        _require(type(table) is int and 1 <= table <= 4 and
                 type(label) is str and 0 < len(label) <= 64, 'Invalid hand identity')
        ident = (table, label)
        _require(ident not in seen_hands, 'Duplicate hand identity')
        seen_hands.add(ident)
        start, end = (hand.get('start_nominal_seconds_human_marked'),
                      hand.get('end_nominal_seconds_human_marked'))
        _require(_finite(start) and _finite(end) and 0 <= start < end <= 86400,
                 'Invalid nominal interval')
        _require(_finite(hand.get('reviewer_confidence_subjective')) and
                 0 <= hand['reviewer_confidence_subjective'] <= 1,
                 'Invalid subjective confidence')
        worksheet = hand.get('manual_reconstruction_worksheet')
        _require(type(worksheet) is dict and worksheet and
                 all(value is None for value in worksheet.values()),
                 'Manual reconstruction already populated; unexpected authority')
        rows = hand.get('observations')
        summaries = hand.get('field_summaries')
        _require(type(rows) is list and type(summaries) is dict and
                 set(summaries) == set(FIELDS), 'Malformed observations/summaries')
        total += len(rows)
        _require(total <= MAX_OBSERVATIONS, 'Too many observations')
        by_field = {f: [] for f in FIELDS}
        for row in rows:
            _require(type(row) is dict and row.get('table_id') == table and
                     type(row.get('table_id')) is int and row.get('field') in FIELDS and
                     type(row.get('field')) is str, 'Cross-table or unknown evidence')
            stamp = row.get('nominal_timestamp_seconds')
            _require(_finite(stamp) and start <= stamp <= end, 'Evidence outside hand interval')
            _sha(row.get('source_image_sha256'))
            _require(type(row.get('candidate_index')) is int and row['candidate_index'] >= 0,
                     'Invalid candidate index')
            status = row.get('review_status')
            _require(type(status) is str and status in STATUSES, 'Invalid review status')
            value = row.get('human_annotation_value_unparsed')
            _require(value is None or (type(value) is str and len(value) <= 1000),
                     'Invalid human annotation')
            if status in ('confirmed', 'corrected'):
                _require(type(value) is str and bool(value.strip()),
                         'Approved evidence missing human value')
            else:
                _require(value is None, 'Unapproved evidence has promoted value')
            key = (table, float(stamp), row['field'], row['candidate_index'],
                   row['source_image_sha256'])
            _require(key not in seen_evidence, 'Duplicate evidence reference')
            seen_evidence.add(key)
            by_field[row['field']].append(row)
        for field in FIELDS:
            summary = summaries[field]
            _require(type(summary) is dict and
                     summary.get('usable_as_mathematical_fact') is False and
                     summary.get('observation_count') == len(by_field[field]) and
                     type(summary.get('observation_count')) is int, 'Invalid field summary')
            statuses = summary.get('review_status_counts')
            _require(type(statuses) is dict and set(statuses) == set(STATUSES) and
                     all(type(statuses[s]) is int and statuses[s] ==
                         sum(row['review_status'] == s for row in by_field[field])
                         for s in STATUSES), 'Inconsistent review counts')
            approved = [r for r in by_field[field] if r['review_status'] in ('confirmed', 'corrected')]
            _require(summary.get('human_approved_observation_count') == len(approved) and
                     type(summary.get('human_approved_observation_count')) is int and
                     summary.get('missing_from_interval') is (not by_field[field]),
                     'Inconsistent approved/missing counts')
            distinct = sorted({r['human_annotation_value_unparsed'] for r in approved})
            _require(summary.get('distinct_human_values_unparsed') == distinct and
                     summary.get('multiple_values_across_time_requires_interpretation') is (len(distinct) > 1),
                     'Inconsistent human values')
            stamps = {}
            for row in approved:
                stamps.setdefault(float(row['nominal_timestamp_seconds']), set()).add(
                    row['human_annotation_value_unparsed'])
            conflicts = sorted(t for t, values in stamps.items() if len(values) > 1)
            _require(summary.get('same_nominal_timestamp_conflicts') == conflicts,
                     'Inconsistent conflict flags')
    _require(type(counts.get('linked_ocr_observations')) is int and
             counts['linked_ocr_observations'] == total and
             type(counts.get('unassigned_ocr_observations')) is int and
             counts['unassigned_ocr_observations'] >= 0, 'Invalid evidence totals')
    return total


def build_checklist(report):
    """Create a non-authoritative, deterministic task queue from validated JSON."""
    validate_dossiers(report)
    tasks = []
    for hand in report['dossiers']:
        missing, unresolved, conflicts, changes = [], [], [], []
        for field in FIELDS:
            s = hand['field_summaries'][field]
            if not s['human_approved_observation_count']:
                missing.append(field)
            if any(s['review_status_counts'][status] for status in ('pending', 'uncertain', 'rejected')):
                unresolved.append(field)
            if s['same_nominal_timestamp_conflicts']:
                conflicts.append(field)
            if s['multiple_values_across_time_requires_interpretation']:
                changes.append(field)
        blockers = ['source_pts_and_hand_boundaries_not_verified',
                    'complete_action_sequence_stacks_and_ranges_not_attested',
                    'independent_manual_hand_reconstruction_required']
        if missing:
            blockers.append('no_approved_observation_for_required_fields')
        if unresolved:
            blockers.append('unresolved_or_rejected_ocr_observations')
        if conflicts:
            blockers.append('conflicting_values_at_same_nominal_timestamp')
        if changes:
            blockers.append('temporal_value_changes_need_action_sequence_review')
        tasks.append({
            'table_id': hand['table_id'], 'hand_label_human_assigned': hand['hand_label_human_assigned'],
            'nominal_interval_seconds': [hand['start_nominal_seconds_human_marked'],
                                         hand['end_nominal_seconds_human_marked']],
            'source_image_sha256s': sorted({r['source_image_sha256'] for r in hand['observations']}),
            'human_subjective_interval_confidence': hand['reviewer_confidence_subjective'],
            'missing_approved_fields': missing, 'unresolved_fields': unresolved,
            'same_timestamp_conflict_fields': conflicts, 'temporally_changing_fields': changes,
            'blocking_reasons': blockers,
            'manual_reconstruction_template': {
                'variant': None, 'hero_cards': None, 'board_by_street': None,
                'pot_and_bet_sequence': None, 'effective_stacks': None,
                'actions_with_actors_and_streets': None,
                'decision_point': None, 'opponent_ranges_assumptions': None,
                'source_pts_verified_against_video': None,
                'independent_reviewer_attestation': None,
            },
            'hand_reconstruction_verified': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
        })
    return {
        'schema_version': 1,
        'analysis_status': 'manual_reconstruction_checklist_no_math',
        'job_id': report['job_id'], 'source_sha256': report['source_sha256'],
        'source_dossiers_sha256': hashlib.sha256(_canonical(report)).hexdigest(),
        'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
        'tasks': tasks,
        'counts': {'hands_to_review': len(tasks), 'math_ready': 0,
                   'with_missing_approved_fields': sum(bool(t['missing_approved_fields']) for t in tasks),
                   'with_same_timestamp_conflicts': sum(bool(t['same_timestamp_conflict_fields']) for t in tasks)},
        'requires_source_video_reaudit': True,
        'hand_start_or_end_pts_verified': False,
        'hand_reconstruction_verified': False, 'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'limitations': ['A checklist is not a reconstructed hand or an equity/EV input.',
                        'Nominal timestamps are not exact video PTS.',
                        'OCR values remain unparsed and cannot be promoted to mathematical facts.',
                        'No inferred hidden cards, strategic verdict, or automatic clip selection.'],
    }


def export_checklist(input_path, output_path):
    source, target = Path(input_path), Path(output_path)
    _require(source.is_file() and not source.is_symlink() and
             source.stat().st_size <= MAX_INPUT_BYTES, 'Unsafe or oversized input')
    raw = source.read_bytes()
    _require(len(raw) <= MAX_INPUT_BYTES, 'Oversized input')
    try:
        report = json.loads(raw.decode('utf-8'),
                            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid UTF-8 JSON') from exc
    result = build_checklist(report)
    _require(source.read_bytes() == raw, 'Input changed during validation')
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'
    _require(len(payload) <= MAX_OUTPUT_BYTES, 'Oversized output')
    _require(target.parent.is_dir() and not target.parent.is_symlink(),
             'Unsafe output directory')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Unsafe output file')
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dossiers_json')
    parser.add_argument('output_json')
    args = parser.parse_args(argv)
    report = export_checklist(args.dossiers_json, args.output_json)
    print(json.dumps({'counts': report['counts'], 'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
