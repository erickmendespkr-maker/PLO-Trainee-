"""Consolidate an offline, human-reviewed PLO5/PLO6 session without new EV claims.

Usage:
 python video_analyzer/offline_session_consolidated_report.py \
  recording.mp4 exported_batch/ session_review.json manual_annotations.json \
  reviewed_observations.json ev_gate.json new_summary.json new_summary.html

The report is read-only: no OCR, equity recalculation, clip selection or advice.
Only already-exported, manually selected clips are included. Requires the
existing review EV gate; fails closed if any source or gate has become stale.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import os
from pathlib import Path
import tempfile

from offline_human_observation_review import load, require, sha256
from offline_review_ev_gate import validate as recompute_gate


def summarize(recording, clips, packet, annotations, reviewed, gate_path):
    """Return a deterministic summary only when the EV gate matches current inputs."""
    paths = tuple(map(Path, (recording, packet, annotations, reviewed, gate_path)))
    require(len({str(p.resolve()) for p in paths}) == len(paths), 'Input paths must differ')
    expected, _, media = recompute_gate(recording, clips, packet, annotations, reviewed)
    gate = load(gate_path)
    require(gate == expected, 'EV gate stale, altered or not bound to inputs')
    source = load(packet)
    rows = source['decisions']
    require(len(rows) == len(gate['decisions']), 'Decision count mismatch')
    grouped = {}
    for original, status in zip(rows, gate['decisions']):
        key = (original['table_id'], original['hand_id'])
        require((status['table_id'], status['hand_id'], status['decision_id']) ==
                (original['table_id'], original['hand_id'], original['decision_id']),
                'Decision order mismatch')
        if key not in grouped:
            grouped[key] = {
                'table_id': key[0], 'hand_id': key[1],
                'game_type': original['game_type'],
                'clip_file': original['clip_file'],
                'clip_sha256': original['clip_sha256'],
                'clip_window_seconds': original.get('clip_window_seconds'),
                'candidate_window_seconds': original.get('candidate_window_seconds'),
                'decisions': [],
            }
        hand = grouped[key]
        require((hand['game_type'], hand['clip_file'], hand['clip_sha256'],
                 hand['clip_window_seconds'], hand['candidate_window_seconds']) ==
                (original['game_type'], original['clip_file'], original['clip_sha256'],
                 original.get('clip_window_seconds'), original.get('candidate_window_seconds')),
                'Inconsistent hand identity or media')
        display_ev = status['may_display_hypothetical_ev'] is True
        hand['decisions'].append({
            'decision_id': original['decision_id'],
            'action_pts_seconds': original['action_pts_seconds'],
            'original_observed_action': original['observed_action'],
            'review_outcome': status['review_outcome'],
            'ev_interpretation_status': status['ev_interpretation_status'],
            'may_display_hypothetical_ev': display_ev,
            'hypothetical_ev_interval_units': (
                status['observed_ev_interval_units'] if display_ev else None),
            'priority_label_from_unverified_model': original.get('review_label'),
            'call_range_assumption_unverified': original.get('call_range_assumption'),
            'raise_called_range_assumption_unverified': original.get('raise_called_range_assumption'),
            'fold_probability_hypothesis': original.get('fold_probability_hypothesis'),
            'decision_quality_verified': False,
            'action_recommendation_authorized': False,
        })
    hands = sorted(grouped.values(), key=lambda h: (h['table_id'], h['candidate_window_seconds'][0] if h['candidate_window_seconds'] else -1, h['hand_id']))
    summary = {
        'schema_version': 1,
        'analysis_status': 'offline_consolidated_human_review_read_only',
        'source_recording_sha256': sha256(recording),
        'source_session_review_sha256': sha256(packet),
        'source_manual_annotations_sha256': sha256(annotations),
        'source_reviewed_observations_sha256': sha256(reviewed),
        'source_ev_gate_sha256': sha256(gate_path),
        'reviewer_identity_authenticated': False,
        'video_evidence_independently_verified': False,
        'range_assumptions_verified': False,
        'equity_ev_recomputed': False,
        'decision_quality_verified': False,
        'automatic_clip_selection_authorized': False,
        'action_recommendation_authorized': False,
        'warning': ('Relatorio de evidencias e hipoteses; EV apenas condicional para '
                    'observacoes confirmadas. Outras observacoes bloqueadas. '
                    'Nao ha inferencia visual independente nem recomendacao.'),
        'table_count': len({h['table_id'] for h in hands}),
        'hand_count': len(hands),
        'decision_count': len(rows),
        'clip_count': len(media),
        'ev_status_counts': expected['status_counts'],
        'hands': hands,
    }
    return summary, {str(p): sha256(p) for p in paths}, media


def render_html(report, batch_name):
    h = lambda value: escape(str(value), quote=True)
    cards = []
    for hand in report['hands']:
        decisions = []
        for d in hand['decisions']:
            ev = ('EV hipotetico: ' + h(d['hypothetical_ev_interval_units'])
                  if d['may_display_hypothetical_ev'] else 'EV bloqueado ate revisao/recalculo')
            decisions.append('<li><strong>' + h(d['decision_id']) + '</strong> · '
                             + h(d['action_pts_seconds']) + 's · acao observada '
                             + h(d['original_observed_action']) + ' · '
                             + h(d['review_outcome']) + ' · ' + h(d['ev_interpretation_status'])
                             + '<p>' + ev + '</p><details><summary>Hipoteses nao verificadas</summary>'
                             + '<p>Range call: ' + h(d['call_range_assumption_unverified'])
                             + '</p><p>Range raise pago: ' + h(d['raise_called_range_assumption_unverified'])
                             + '</p><p>Probabilidade hipotetica de fold: '
                             + h(d['fold_probability_hypothesis']) + '</p></details></li>')
        cards.append('<article><h2>Mesa ' + str(hand['table_id']) + ' · ' + h(hand['game_type'])
                     + ' · ' + h(hand['hand_id']) + '</h2><p>Janela: '
                     + h(hand['candidate_window_seconds']) + 's</p>'
                     + '<video controls preload="none" playsinline src="'
                     + h(batch_name + '/' + hand['clip_file']) + '"></video>'
                     + '<ul>' + ''.join(decisions) + '</ul></article>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'media-src \'self\' file:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<title>PLO Trainee — sessao revisada offline</title>'
            '<style>body{font:16px system-ui;background:#111827;color:#f3f4f6;max-width:950px;margin:2rem auto;padding:1rem}'
            'article{background:#1f2937;border:1px solid #64748b;border-radius:12px;padding:1rem;margin:1rem 0}'
            'video{max-width:100%;width:480px;background:#000}li{margin:.9rem 0}code{overflow-wrap:anywhere}</style>'
            '</head><body><h1>PLO Trainee — relatorio consolidado offline</h1>'
            '<p>Somente videos previamente selecionados. OCR, ranges, EV e decisoes nao foram '
            'autenticados. Confirmacao humana nao comprova qualidade matematica. Sem recomendacoes.</p>'
            '<p>Mesas: ' + str(report['table_count']) + ' · Maos: ' + str(report['hand_count'])
            + ' · Decisoes: ' + str(report['decision_count']) + '</p>'
            + ''.join(cards) + '</body></html>\n')


def build(recording, clips, packet, annotations, reviewed, gate, output_json, output_html):
    clips, output_json, output_html = map(Path, (clips, output_json, output_html))
    inputs = tuple(map(Path, (recording, packet, annotations, reviewed, gate)))
    require(clips.is_dir() and not clips.is_symlink() and
            output_json.parent == output_html.parent == clips.parent and
            output_json.suffix == '.json' and output_html.suffix == '.html' and
            output_json != output_html and
            all(not p.exists() and not p.is_symlink() for p in (output_json, output_html)) and
            not {str(p.resolve()) for p in (output_json, output_html)}.intersection(
                str(p.resolve()) for p in inputs), 'Outputs must be new siblings of clips')
    report, hashes, media = summarize(recording, clips, packet, annotations, reviewed, gate)
    with tempfile.TemporaryDirectory(prefix='plo_session_summary_', dir=clips.parent) as tmp:
        js, html = Path(tmp) / 'report.json', Path(tmp) / 'report.html'
        js.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        html.write_text(render_html(report, clips.name), encoding='utf-8')
        require(all(sha256(p) == digest for p, digest in hashes.items()) and
                all(sha256(clips / name) == digest for name, digest in media.items()),
                'Source changed during publication')
        os.link(js, output_json)
        try:
            os.link(html, output_html)
        except BaseException:
            output_json.unlink()
            raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('recording', 'clip_directory', 'session_review_json',
                 'manual_annotations_json', 'reviewed_observations_json',
                 'ev_gate_json', 'new_summary_json', 'new_summary_html'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    report = build(args.recording, args.clip_directory, args.session_review_json,
                   args.manual_annotations_json, args.reviewed_observations_json,
                   args.ev_gate_json, args.new_summary_json, args.new_summary_html)
    print(json.dumps({'status': report['analysis_status'], 'hands': report['hand_count'],
                      'decisions': report['decision_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
