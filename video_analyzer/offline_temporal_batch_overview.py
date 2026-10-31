"""Read-only offline HTML index for audited temporal table crops and blocked decisions.

Usage: python offline_temporal_batch_overview.py VIDEO BATCH_DIR REVIEW.json CROPS_DIR
No live interaction, no OCR promotion and no strategy verdict.
"""
from __future__ import annotations

import argparse
from html import escape
import os
from pathlib import Path
import tempfile
from urllib.parse import quote

import offline_ev_table_crop as crop
import offline_temporal_batch_crops as temporal


def href(from_dir, target):
    rel = os.path.relpath(target, from_dir)
    return '/'.join('..' if s == '..' else quote(s, safe='') for s in Path(rel).parts)


def build(video, batch_dir, review_json, crops_dir):
    video, batch_dir, review_json, crops_dir = map(Path, (video, batch_dir, review_json, crops_dir))
    temporal.safe_output(crops_dir)
    target = crops_dir / 'temporal_crop_overview.html'
    temporal.no_collision(target)
    # Re-run the same preflight against an empty, separate temporary directory;
    # this checks every original source hash and interval before publishing HTML.
    with tempfile.TemporaryDirectory(prefix='plo_temporal_index_check_', dir=crops_dir) as scratch:
        _, _, batch_path, _, plans, blocked, inputs = temporal.preflight(
            video, batch_dir, review_json, scratch)
    ledger_path = crops_dir / 'temporal_crop_batch_report.json'
    ledger = crop.read_json(ledger_path)
    crop.check(type(ledger) is dict and ledger.get('schema_version') == 1 and
               ledger.get('status') == temporal.STATUS and
               ledger.get('automatic_ocr_math_authorization') is False and
               ledger.get('table_identity_verified') is False and
               ledger.get('source_video_sha256') == inputs[0][1] and
               ledger.get('source_temporal_review_sha256') == inputs[1][1] and
               ledger.get('source_batch_report_sha256') == inputs[2][1] and
               ledger.get('boundary_guard_seconds') == temporal.GUARD_SECONDS and
               type(ledger.get('clips')) is list and type(ledger.get('blocked')) is list and
               ledger.get('rendered_count') == len(plans) == len(ledger['clips']) and
               ledger.get('blocked_count') == len(blocked) == len(ledger['blocked']) and
               ledger['blocked'] == blocked, 'invalid temporal crop ledger')
    checked = inputs + [(ledger_path, crop.digest(ledger_path))]
    cards = []
    for item, plan in zip(ledger['clips'], plans):
        cid, table, hand, report, region, index = plan
        crop.check(type(item) is dict and item.get('clip_id') == cid and
                   item.get('table_id') == table and item.get('hand_id') == hand and
                   item.get('segment_index') == index and
                   item.get('filename') == f'temporal_{cid}.mp4' and
                   item.get('metadata') == f'temporal_{cid}.json',
                   'temporal clip identity mismatch')
        mp4, meta_path = crops_dir / item['filename'], crops_dir / item['metadata']
        sha = crop.digest(mp4)
        meta = crop.read_json(meta_path)
        crop.check(item.get('sha256') == sha and
                   meta.get('status') == temporal.CROP_STATUS and
                   meta.get('clip_id') == cid and meta.get('table_id_claim') == table and
                   meta.get('hand_id') == hand and meta.get('crop_sha256') == sha and
                   meta.get('crop_filename') == item['filename'] and
                   meta.get('region_claim') == region and
                   meta.get('temporal_segment_index') == index and
                   meta.get('source_video_sha256') == inputs[0][1] and
                   meta.get('source_temporal_review_sha256') == inputs[1][1] and
                   meta.get('source_batch_report_sha256') == inputs[2][1] and
                   meta.get('source_clip_report_sha256') == crop.digest(batch_dir / (cid + '.json')) and
                   meta.get('automatic_ocr_math_authorization') is False and
                   meta.get('table_identity_verified') is False and
                   meta.get('clip_start_seconds') == report['clip_start_seconds'] and
                   meta.get('clip_duration_seconds_claim') == report['clip_duration_seconds'] and
                   meta.get('decision_pts_seconds_claim') == report['decision_pts_seconds_claim'],
                   'temporal crop metadata mismatch')
        checked.extend([(mp4, sha), (meta_path, crop.digest(meta_path))])
        original = batch_dir / (cid + '.mp4')
        cards.append('<section><h2>Mesa ' + escape(table) + ' · Mão ' + escape(hand) +
                     '</h2><p>Segmento ' + str(index) + ' · PTS ' +
                     escape(str(report['decision_pts_seconds_claim'])) + 's</p>' +
                     '<div class="pair"><div><h3>Original</h3><video controls preload="none" src="' +
                     escape(href(crops_dir, original), quote=True) + '"></video></div>' +
                     '<div><h3>Recorte temporal</h3><video controls preload="none" src="' +
                     escape(href(crops_dir, mp4), quote=True) + '"></video></div></div>' +
                     '<p><a href="' + escape(href(crops_dir, meta_path), quote=True) +
                     '">Proveniência JSON</a> · <a href="' +
                     escape(href(crops_dir, batch_dir / (cid + '.json')), quote=True) +
                     '">EV condicional / hipóteses</a></p></section>')
    blocked_html = ''.join('<li>' + escape(x['clip_id']) + ': ' + escape(x['reason']) +
                           '</li>' for x in blocked)
    page = ('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PLO Trainee — recortes temporais</title>'
            '<style>body{font:16px system-ui;max-width:980px;margin:2rem auto;padding:0 1rem}'
            'section{border-top:1px solid #999;padding:1rem 0}'
            '.pair{display:flex;gap:1rem;flex-wrap:wrap}.pair>div{flex:1 1 320px}'
            'video{width:100%;max-width:450px}</style>'
            '<h1>Recortes temporais — sessão gravada</h1>'
            '<p>Geometria e identidade das mesas são declarações humanas não verificadas. '
            'Equity/EV condicionais não são vereditos estratégicos. Sem OCR automático.</p>'
            '<p>Exportados: ' + str(len(cards)) + ' · Bloqueados: ' + str(len(blocked)) +
            ' · <a href="temporal_crop_batch_report.json">Relatório JSON</a></p>' +
            ''.join(cards) + '<h2>Decisões bloqueadas para revisão</h2><ul>' +
            blocked_html + '</ul></html>')
    crop.check(all(crop.digest(p) == sha for p, sha in checked),
               'input changed during overview construction')
    with tempfile.TemporaryDirectory(prefix='plo_temporal_index_', dir=crops_dir) as folder:
        temp = Path(folder) / target.name
        temp.write_text(page, encoding='utf-8')
        crop.check(all(crop.digest(p) == sha for p, sha in checked),
                   'input changed before index publication')
        temporal.no_collision(target)
        os.link(temp, target)
    return target


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('video', 'batch_dir', 'temporal_review_json', 'crops_dir'):
        p.add_argument(n)
    a = p.parse_args(argv)
    print(build(a.video, a.batch_dir, a.temporal_review_json, a.crops_dir))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
