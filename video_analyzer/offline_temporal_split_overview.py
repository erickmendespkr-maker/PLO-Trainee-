"""Build an offline HTML index for reviewed temporal split MP4s, with integrity checks.

Usage: python offline_temporal_split_overview.py VIDEO BATCH_DIR REVIEW_JSON SPLIT_DIR
No inferred poker facts, no networking, no browser-side scripts.
"""
from __future__ import annotations
import argparse
import html
import json
import os
from pathlib import Path
import tempfile

import offline_ev_table_crop as crop
import offline_temporal_split_clips as split

PAGE = 'temporal_split_overview.html'


def require(ok, reason):
    crop.check(ok, reason)


def render(video, batch_dir, review_json, split_dir):
    out = Path(split_dir)
    require(out.is_dir() and not out.is_symlink(), 'unsafe split directory')
    split.existing.no_collision(out / PAGE)
    # Rebuild the expected split plan against the original authenticated inputs.
    with tempfile.TemporaryDirectory(prefix='plo_split_verify_', dir=out) as tmp:
        _, _, plans, blocked, inputs = split.preflight(video, batch_dir, review_json, tmp)
    ledger = crop.read_json(out / 'temporal_split_report.json')
    require(type(ledger) is dict and ledger.get('schema_version') == 1 and
            ledger.get('status') == split.STATUS and
            ledger.get('source_video_sha256') == inputs[0][1] and
            ledger.get('source_temporal_review_sha256') == inputs[1][1] and
            ledger.get('source_batch_report_sha256') == inputs[2][1] and
            ledger.get('transition_guard_seconds') == split.GUARD_SECONDS and
            ledger.get('min_part_seconds') == split.MIN_PART_SECONDS and
            ledger.get('table_identity_verified') is False and
            ledger.get('automatic_ocr_math_authorization') is False and
            ledger.get('blocked') == blocked and
            type(ledger.get('blocked_count')) is int and
            ledger['blocked_count'] == len(blocked) and
            type(ledger.get('rendered_count')) is int and
            ledger['rendered_count'] == len(plans) and
            type(ledger.get('parts')) is list and
            len(ledger['parts']) == len(plans), 'split ledger/provenance mismatch')
    sections = []
    for item, plan in zip(ledger['parts'], plans):
        require(type(item) is dict and
                item.get('clip_id') == plan['clip_id'] and
                item.get('table_id') == plan['table_id'] and
                item.get('hand_id') == plan['hand_id'] and
                item.get('segment_index') == plan['segment_index'] and
                item.get('filename') == plan['filename'] and
                item.get('metadata') == plan['metadata'] and
                item.get('start_seconds') == plan['start'] and
                item.get('end_seconds') == plan['end'] and
                item.get('decision_in_part') is plan['decision_in_part'] and
                item.get('omitted_intervals_seconds') == plan['omitted_intervals'],
                'unexpected split entry')
        mp4, meta_path = out / plan['filename'], out / plan['metadata']
        sha = crop.digest(mp4)
        meta = crop.read_json(meta_path)
        require(item.get('sha256') == sha and meta.get('sha256') == sha and
                meta.get('filename') == plan['filename'] and
                meta.get('status') == split.PART_STATUS and
                meta.get('source_video_sha256') == inputs[0][1] and
                meta.get('source_temporal_review_sha256') == inputs[1][1] and
                meta.get('source_batch_report_sha256') == inputs[2][1] and
                meta.get('source_clip_report_sha256') == plan['source_clip_report_sha256'] and
                meta.get('table_identity_verified') is False and
                meta.get('automatic_ocr_math_authorization') is False and
                meta.get('region_claim') == plan['region'] and
                meta.get('start_seconds') == plan['start'] and
                meta.get('end_seconds') == plan['end'] and
                meta.get('decision_in_part') is plan['decision_in_part'] and
                meta.get('omitted_intervals_seconds') == plan['omitted_intervals'],
                'split MP4/metadata integrity mismatch')
        gap = ', '.join(f"{x['start_seconds']:.2f}–{x['end_seconds']:.2f}s"
                        for x in plan['omitted_intervals']) or 'nenhum'
        sections.append('<article><h2>Mesa ' + html.escape(plan['table_id']) +
                        ' · Mão ' + html.escape(plan['hand_id']) +
                        ' · Segmento ' + str(plan['segment_index']) + '</h2>' +
                        '<video controls preload="metadata" src="' +
                        html.escape(plan['filename'], quote=True) + '"></video>' +
                        '<p>Intervalo do vídeo original: ' + f"{plan['start']:.2f}–{plan['end']:.2f}s" +
                        ' · Decisão neste trecho: ' + ('sim' if plan['decision_in_part'] else 'não') +
                        '</p><p>Tempo omitido (não reconstruído): ' + html.escape(gap) + '</p>' +
                        '<a href="' + html.escape(plan['metadata'], quote=True) +
                        '">Metadados e SHA-256</a></article>')
    blocked_html = ''.join('<li>' + html.escape(b['clip_id']) + ': ' +
                           html.escape(b['reason']) + '</li>' for b in blocked)
    page = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<title>PLO Trainee — Cortes temporais offline</title><style>'
            'body{font:16px sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem}'
            'article{border:1px solid #888;border-radius:8px;padding:1rem;margin:1rem 0}'
            'video{display:block;max-width:100%;margin:1rem 0}p{line-height:1.5}'
            '</style></head><body><h1>Cortes temporais — evidências não verificadas</h1>'
            '<p>Gravação offline. Geometria e identidade das mesas declaradas; '
            'ações e EV condicionais não comprovados. Transições omitidas, '
            'sem reconstrução ou continuidade artificial.</p>' +
            ''.join(sections) + '<h2>Decisões bloqueadas</h2><ul>' + blocked_html +
            '</ul></body></html>')
    require(all(crop.digest(f) == sha for f, sha in inputs), 'source changed')
    with tempfile.TemporaryDirectory(prefix='plo_split_html_', dir=out) as folder:
        tmp = Path(folder) / PAGE
        tmp.write_text(page, encoding='utf-8')
        split.existing.no_collision(out / PAGE)
        os.link(tmp, out / PAGE)
    return {'html_filename': PAGE, 'parts': len(plans), 'blocked': len(blocked)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'batch_dir', 'temporal_review_json', 'split_dir'):
        parser.add_argument(name)
    a = parser.parse_args(argv)
    print(json.dumps(render(a.video, a.batch_dir, a.temporal_review_json, a.split_dir)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
