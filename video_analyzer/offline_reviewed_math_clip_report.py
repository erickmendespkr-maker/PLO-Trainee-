"""Offline evidence-bound Monte Carlo/EV viewer for a single reviewed decision.

Usage: python offline_reviewed_math_clip_report.py MANIFEST.json CANDIDATE.json
       MC_REPORT.json SPLIT_DIR EMPTY_OUTPUT_DIR
This is a navigation/reporting adapter, not an OCR or strategic-verdict engine.
The MC result is recomputed from the candidate before being displayed.
"""
from __future__ import annotations
import argparse
from html import escape
import json
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import quote

import offline_math_mc_bridge as bridge
import offline_reviewed_clip_manifest as clips

STATUS = 'offline_reviewed_math_clip_conditional_navigation_only'
JSON_NAME = 'reviewed_math_clip.json'
HTML_NAME = 'reviewed_math_clip.html'


def check(ok, message):
    if not ok:
        raise ValueError(message)


def build(manifest, candidate, report, candidate_sha):
    check(type(manifest) is dict and manifest.get('schema_version') == 1 and
          manifest.get('status') == clips.STATUS and
          manifest.get('automatic_math_authorization') is False and
          manifest.get('confidence_calibrated') is False and
          manifest.get('table_identity_verified') is False and
          type(manifest.get('source_reviewed_report_sha256')) is str and
          clips.HEX.fullmatch(manifest['source_reviewed_report_sha256']) and
          type(manifest.get('hands')) is list and 1 <= len(manifest['hands']) <= 500,
          'invalid reviewed clip manifest')
    check(type(candidate) is dict and type(report) is dict and
          candidate.get('variant') == manifest.get('variant') and
          candidate.get('source_review_sha256') == manifest['source_reviewed_report_sha256'] and
          candidate.get('source_full_review_sha256') == manifest['source_reviewed_report_sha256'] and
          report.get('source_review_sha256_claim') == manifest['source_reviewed_report_sha256'] and
          report.get('source_candidate_sha256') == candidate_sha,
          'math/review provenance mismatch')
    # Re-run the installed engine, not merely trust a supplied EV JSON.
    check(bridge.build(candidate, candidate_sha) == report,
          'math report does not match recomputed conditional simulation')
    key = (candidate['table_id'], candidate['hand_id'])
    matches = [h for h in manifest['hands'] if type(h) is dict and
               (h.get('table_id'), h.get('hand_id')) == key]
    check(len(matches) == 1, 'missing or ambiguous reviewed hand')
    hand = matches[0]
    t = candidate['decision_timestamp_seconds']
    check(clips.number(t) and clips.number(hand.get('start_seconds')) and
          clips.number(hand.get('end_seconds')) and
          hand['start_seconds'] <= t <= hand['end_seconds'] and
          hand.get('automatic_math_authorization') is False and
          hand.get('card_evidence_consistent_claim') is True and
          hand.get('review_flags') == [], 'decision outside reviewed clean hand')
    available = hand.get('clips')
    check(type(available) is list and len(available) <= 1000, 'invalid clip list')
    selected = []
    for c in available:
        check(type(c) is dict and type(c.get('filename')) is str and
              clips.SAFE_MP4.fullmatch(c['filename']) and
              type(c.get('sha256')) is str and clips.HEX.fullmatch(c['sha256']) and
              clips.number(c.get('start_seconds')) and clips.number(c.get('end_seconds')) and
              c['start_seconds'] < c['end_seconds'] and
              type(c.get('decision_in_part')) is bool,
              'invalid clip metadata')
        if c['start_seconds'] <= t <= c['end_seconds'] and c['decision_in_part']:
            selected.append(c)
    check(len(selected) == 1, 'decision clip missing or ambiguous; manual review required')
    chosen = selected[0]
    return {'schema_version': 1, 'status': STATUS, 'variant': candidate['variant'],
            'table_id': key[0], 'hand_id': key[1], 'decision_timestamp_seconds': t,
            'decision_street': candidate['decision_street'],
            'clip': {k: chosen[k] for k in ('filename', 'sha256', 'start_seconds',
                    'end_seconds', 'clip_id', 'segment_index')},
            'math': {k: report[k] for k in ('model', 'seed', 'trials', 'wins', 'ties',
                    'losses', 'equity_estimate', 'equity_95pct_hoeffding_interval',
                    'ev_call_estimate', 'ev_call_95pct_hoeffding_interval',
                    'break_even_equity', 'range_assumption', 'confidence_assumption')},
            'source_reviewed_report_sha256': manifest['source_reviewed_report_sha256'],
            'source_candidate_sha256': candidate_sha,
            'automatic_clip_selection_authorized': False,
            'strategic_correctness_verified': False,
            'warning': ('Human-reviewed assertions and hypothetical uniform range only. '
                        'Sampling interval does not cover OCR, range or model uncertainty; '
                        'no automatic decision quality verdict.')}


def html_page(result, relative_media):
    c, m = result['clip'], result['math']
    source = quote(relative_media + '/' + c['filename'], safe='/._-')
    parts = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
             '<title>PLO Trainee — equity e clipe revisado</title>',
             '<style>body{font:16px system-ui;max-width:800px;margin:2rem auto;padding:1rem}',
             'video{width:100%;max-width:720px}dt{font-weight:bold;margin-top:.8rem}',
             'dd{margin-left:0}</style></head><body>',
             '<h1>Decisão revisada — análise condicional</h1><p>',
             escape(result['table_id'] + ' / ' + result['hand_id']),
             '</p><video controls preload="metadata" src="', escape(source, quote=True),
             '"></video><dl>']
    for label, value in [('Street', result['decision_street']),
                         ('Timestamp (s)', result['decision_timestamp_seconds']),
                         ('Equity estimada', m['equity_estimate']),
                         ('IC Monte Carlo 95%', m['equity_95pct_hoeffding_interval']),
                         ('EV call (unidades)', m['ev_call_estimate']),
                         ('IC EV call 95%', m['ev_call_95pct_hoeffding_interval']),
                         ('Hipótese de range', m['range_assumption']),
                         ('Limites de confiança', m['confidence_assumption'])]:
        parts += ['<dt>', escape(str(label)), '</dt><dd>', escape(str(value)), '</dd>']
    parts += ['</dl><p><strong>Aviso:</strong> ', escape(result['warning']),
              '</p><p><a href="', JSON_NAME, '">Relatório JSON</a></p></body></html>']
    return ''.join(parts)


def export(manifest_path, candidate_path, report_path, media_dir, output_dir):
    inputs = [Path(p) for p in (manifest_path, candidate_path, report_path)]
    media, output = Path(media_dir), Path(output_dir)
    check(all(p.is_file() and not p.is_symlink() for p in inputs) and
          media.is_dir() and not media.is_symlink() and
          output.is_dir() and not output.is_symlink() and
          len({p.resolve() for p in inputs + [media, output]}) == 5,
          'unsafe input/output locations')
    check(all(not (output / name).exists() and not (output / name).is_symlink()
              for name in (JSON_NAME, HTML_NAME)), 'output collision')
    hashes = [clips.digest(p) for p in inputs]
    manifest, candidate, report = [clips.read_json(p) for p in inputs]
    result = build(manifest, candidate, report, hashes[1])
    clip_file = media / result['clip']['filename']
    check(clip_file.is_file() and not clip_file.is_symlink() and
          clips.digest(clip_file) == result['clip']['sha256'],
          'clip missing or modified')
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix='.plo_math_clip_', dir=output) as folder:
            temp = Path(folder)
            (temp / JSON_NAME).write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                    allow_nan=False) + '\n', encoding='utf-8')
            (temp / HTML_NAME).write_text(html_page(result, Path(os.path.relpath(media, output)).as_posix()), encoding='utf-8')
            check(all(clips.digest(p) == h for p, h in zip(inputs, hashes)) and
                  clips.digest(clip_file) == result['clip']['sha256'], 'source changed')
            for name in (JSON_NAME, HTML_NAME):
                check(not (output / name).exists() and not (output / name).is_symlink(),
                      'output collision')
                os.link(temp / name, output / name)
                created.append(output / name)
        return result
    except BaseException:
        for p in reversed(created):
            p.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'candidate', 'mc_report', 'split_dir', 'new_output_dir'):
        p.add_argument(name)
    a = p.parse_args()
    print(export(a.manifest, a.candidate, a.mc_report, a.split_dir,
                 a.new_output_dir)['status'])
