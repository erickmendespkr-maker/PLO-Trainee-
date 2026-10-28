"""Offline, fail-closed EV interpretation gate for human-reviewed video observations.

Usage:
 python video_analyzer/offline_review_ev_gate.py recording.mp4 exported_batch/ \
     session_review.json manual_annotations.json reviewed_observations.json \
     new_ev_gate.json new_ev_gate.html

No EV recomputation, real-time integration, poker advice or source modification.
"""
from __future__ import annotations
import argparse
from html import escape
import json
import os
from pathlib import Path
import tempfile

from offline_human_observation_review import (
    load, require, sha256, validate_annotations, verify_source, SAFE_NAME,
)

STATUS = {
    None: 'blocked_pending_review',
    'confirmed': 'conditional_model_only',
    'corrected': 'blocked_stale_observation_requires_recalculation',
    'inconclusive': 'blocked_inconclusive_observation',
}


def validate(recording, clips, packet_path, annotations_path, reviewed_path):
    recording, clips, packet_path, annotations_path, reviewed_path = map(
        Path, (recording, clips, packet_path, annotations_path, reviewed_path))
    require(clips.is_dir() and not clips.is_symlink() and SAFE_NAME.fullmatch(clips.name),
            'Invalid clips directory')
    inputs = (recording, packet_path, annotations_path, reviewed_path)
    require(len({str(p.resolve()) for p in inputs}) == 4, 'Inputs must be distinct')
    hashes = {str(p): sha256(p) for p in inputs}
    packet, annotations, reviewed = map(load, (packet_path, annotations_path, reviewed_path))
    source, media = verify_source(packet, hashes[str(recording)], clips)
    entries = validate_annotations(annotations, source, hashes[str(packet_path)])
    require(type(reviewed) is dict and reviewed.get('schema_version') == 1 and
            reviewed.get('analysis_status') == 'offline_human_supplied_observation_review_unverified' and
            reviewed.get('source_recording_sha256') == hashes[str(recording)] and
            reviewed.get('source_session_review_sha256') == hashes[str(packet_path)] and
            reviewed.get('source_manual_annotations_sha256') == hashes[str(annotations_path)] and
            reviewed.get('reviewer_alias_unverified') == annotations['reviewer_alias'] and
            reviewed.get('human_supplied_annotations_recorded') is True and
            reviewed.get('reviewer_identity_authenticated') is False and
            reviewed.get('video_evidence_independently_verified') is False and
            reviewed.get('range_assumptions_verified') is False and
            reviewed.get('equity_ev_recomputed') is False and
            reviewed.get('decision_quality_verified') is False and
            reviewed.get('automatic_clip_selection_authorized') is False and
            reviewed.get('action_recommendation_authorized') is False and
            reviewed.get('source_files_modified') is False and
            type(reviewed.get('decisions')) is list and
            len(reviewed['decisions']) == len(source) and
            type(reviewed.get('decision_count')) is int and
            reviewed['decision_count'] == len(source) and
            type(reviewed.get('reviewed_decision_count')) is int and
            reviewed['reviewed_decision_count'] == len(entries) and
            type(reviewed.get('pending_decision_count')) is int and
            reviewed['pending_decision_count'] == len(source) - len(entries) and
            type(reviewed.get('clip_count')) is int and
            reviewed['clip_count'] == len(media), 'Invalid reviewed report provenance')
    rows = []
    for key, row in zip(source, reviewed['decisions']):
        original = source[key]
        annotation = entries.get(key)
        require(type(row) is dict and row.get('table_id') == key[0] and
                row.get('hand_id') == key[1] and row.get('decision_id') == key[2] and
                row.get('game_type') == original['game_type'] and
                row.get('clip_file') == original['clip_file'] and
                row.get('clip_sha256') == original['clip_sha256'] and
                row.get('original_observed_action') == original['observed_action'] and
                row.get('original_action_pts_seconds') == original['action_pts_seconds'] and
                row.get('original_review_label') == original.get('review_label') and
                row.get('model_conditional_only') is True and
                row.get('decision_quality_verified') is False and
                row.get('review') == annotation, 'Reviewed decision differs from source/annotations')
        outcome = annotation['outcome'] if annotation is not None else None
        status = STATUS[outcome]
        rows.append({
            'table_id': key[0], 'hand_id': key[1], 'decision_id': key[2],
            'game_type': original['game_type'],
            'clip_file': original['clip_file'], 'clip_sha256': original['clip_sha256'],
            'original_observed_action': original['observed_action'],
            'original_action_pts_seconds': original['action_pts_seconds'],
            'review_outcome': outcome if outcome is not None else 'pending',
            'ev_interpretation_status': status,
            'may_display_hypothetical_ev': outcome == 'confirmed',
            'observed_ev_interval_units': (
                original['observed_ev_interval_units'] if outcome == 'confirmed' else None),
            'range_hypotheses_verified': False,
            'decision_quality_verified': False,
            'recalculation_performed': False,
            'action_recommendation_authorized': False,
        })
    require(all(sha256(p) == hashes[str(p)] for p in inputs) and
            all(sha256(clips / name) == value for name, value in media.items()),
            'Input changed while validating')
    report = {
        'schema_version': 1,
        'analysis_status': 'offline_review_ev_interpretation_gate_only',
        'source_recording_sha256': hashes[str(recording)],
        'source_session_review_sha256': hashes[str(packet_path)],
        'source_manual_annotations_sha256': hashes[str(annotations_path)],
        'source_reviewed_observations_sha256': hashes[str(reviewed_path)],
        'reviewer_identity_authenticated': False,
        'ranges_verified': False,
        'equity_ev_recomputed': False,
        'decision_quality_verified': False,
        'automatic_clip_selection_authorized': False,
        'action_recommendation_authorized': False,
        'warning': 'EV somente hipotetico para observacoes confirmadas; correcoes, inconclusivos e pendentes bloqueados. Nenhuma recomendacao.',
        'decision_count': len(rows),
        'status_counts': {status: sum(r['ev_interpretation_status'] == status for r in rows)
                          for status in STATUS.values()},
        'decisions': rows,
    }
    return report, hashes, media


def render_html(report):
    cards = []
    for row in report['decisions']:
        name = escape(row['hand_id'], quote=True)
        decision = escape(row['decision_id'], quote=True)
        status = escape(row['ev_interpretation_status'], quote=True)
        cards.append(f'<article><h2>Mesa {row["table_id"]} · {name} · {decision}</h2>'
                     f'<p>Estado: <strong>{status}</strong></p>'
                     '<p>Sem recomendação; ranges e qualidade da decisão não verificados.</p></article>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'">'
            '<title>PLO Trainee — status EV após revisão</title>'
            '<style>body{font:16px system-ui;background:#111827;color:#f3f4f6;max-width:850px;margin:2rem auto;padding:1rem}'
            'article{border:1px solid #6b7280;border-radius:8px;padding:1rem;margin:1rem 0}</style></head><body>'
            '<h1>Interpretação condicional após revisão humana</h1>'
            '<p>Confirmado não significa EV correto. Correções exigem novo cálculo condicionado a dados revisados.</p>'
            + ''.join(cards) + '</body></html>\n')


def build(recording, clips, packet, annotations, reviewed, output_json, output_html):
    output, html, clips = Path(output_json), Path(output_html), Path(clips)
    inputs = tuple(map(Path, (recording, packet, annotations, reviewed)))
    require(output.parent == html.parent == clips.parent and
            output.suffix == '.json' and html.suffix == '.html' and output != html and
            all(not p.exists() and not p.is_symlink() for p in (output, html)) and
            not {str(p.resolve()) for p in (output, html)}.intersection(
                str(p.resolve()) for p in inputs), 'Outputs must be new siblings')
    report, hashes, media = validate(recording, clips, packet, annotations, reviewed)
    with tempfile.TemporaryDirectory(prefix='plo_ev_gate_', dir=clips.parent) as tmp:
        stage_json, stage_html = Path(tmp) / 'gate.json', Path(tmp) / 'gate.html'
        stage_json.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
        stage_html.write_text(render_html(report), encoding='utf-8')
        require(all(sha256(Path(p)) == h for p, h in hashes.items()) and
                all(sha256(clips / n) == h for n, h in media.items()), 'Input changed before publication')
        os.link(stage_json, output)
        try:
            os.link(stage_html, html)
        except BaseException:
            output.unlink()
            raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('recording', 'clip_directory', 'session_review_json', 'manual_annotations_json',
                'reviewed_observations_json', 'new_ev_gate_json', 'new_ev_gate_html'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    result = build(args.recording, args.clip_directory, args.session_review_json,
                   args.manual_annotations_json, args.reviewed_observations_json,
                   args.new_ev_gate_json, args.new_ev_gate_html)
    print(json.dumps({'status': result['analysis_status'], 'decisions': result['decision_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
