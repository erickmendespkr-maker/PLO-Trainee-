"""Audited, read-only HTML cross-index of full-frame and per-table PLO clips.

Usage: python offline_ev_session_crops.py BATCH_DIR CROPS_DIR
Both directories must already contain the cycle-237 and cycle-239 offline ledgers.
No OCR authorization, live poker access or strategic verdict is inferred.
"""
from __future__ import annotations

import argparse
from html import escape
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import quote

import offline_ev_table_crop as crop

BATCH_STATUS = 'offline_conditional_ev_batch_unverified_not_strategy_verdict'
CROP_STATUS = 'offline_table_crop_batch_unverified'
MAX_CLIPS = 20


def checked_sha(path):
    path = Path(path)
    crop.safe_file(path)
    crop.check(0 < path.stat().st_size <= 1_000_000_000, 'empty or oversized input')
    return crop.digest(path)


def safe_id(value):
    return type(value) is str and value not in ('.', '..') and crop.ID.fullmatch(value) is not None


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def relative_href(from_dir, target):
    """Encode each URL segment, retaining only known relative-directory separators."""
    rel = os.path.relpath(target, from_dir)
    return '/'.join('..' if segment == '..' else quote(segment, safe='')
                    for segment in Path(rel).parts)


def build(batch_dir, crops_dir):
    batch_dir, crops_dir = Path(batch_dir), Path(crops_dir)
    crop.check(batch_dir.is_dir() and crops_dir.is_dir() and
               not batch_dir.is_symlink() and not crops_dir.is_symlink() and
               batch_dir.resolve() != crops_dir.resolve(), 'invalid source directories')
    target = crops_dir / 'session_with_crops.html'
    crop.check(not target.exists() and not target.is_symlink(), 'combined overview exists')
    batch_path = batch_dir / 'batch_report.json'
    crops_path = crops_dir / 'crop_batch_report.json'
    batch, cropped = crop.read_json(batch_path), crop.read_json(crops_path)
    crop.check(type(batch) is dict and batch.get('schema_version') == 1 and
               batch.get('status') == BATCH_STATUS and
               batch.get('automatic_ocr_math_authorization') is False and
               type(batch.get('clips')) is list and
               type(batch.get('rendered_count')) is int and
               batch['rendered_count'] == len(batch['clips']) <= MAX_CLIPS,
               'invalid source batch ledger')
    crop.check(type(cropped) is dict and cropped.get('schema_version') == 1 and
               cropped.get('status') == CROP_STATUS and
               cropped.get('automatic_ocr_math_authorization') is False and
               type(cropped.get('clips')) is list and
               type(cropped.get('rendered_count')) is int and
               cropped['rendered_count'] == len(cropped['clips']) <= MAX_CLIPS and
               cropped.get('source_video_sha256') == batch.get('source_video_sha256') and
               cropped.get('source_batch_report_sha256') == checked_sha(batch_path) and
               type(cropped.get('source_layout_sha256')) is str and
               crop.HEX.fullmatch(cropped['source_layout_sha256']),
               'crop ledger does not match source batch')
    checked = [(batch_path, checked_sha(batch_path)), (crops_path, checked_sha(crops_path))]
    source = {}
    for entry in batch['clips']:
        crop.check(type(entry) is dict, 'invalid full-frame clip entry')
        cid = entry.get('clip_id')
        crop.check(safe_id(cid) and cid not in source, 'invalid/duplicate full-frame clip ID')
        mp4_name, json_name = cid + '.mp4', cid + '.json'
        crop.check(entry.get('clip_filename') == mp4_name and
                   entry.get('clip_report_filename') == json_name, 'unsafe full-frame filenames')
        mp4, meta_path = batch_dir / mp4_name, batch_dir / json_name
        mp4_sha = checked_sha(mp4)
        meta = crop.read_json(meta_path)
        crop.check(entry.get('clip_sha256') == mp4_sha and
                   meta.get('rendered_clip_sha256') == mp4_sha and
                   meta.get('status') == 'offline_conditional_ev_clip_not_strategy_verdict' and
                   meta.get('automatic_ocr_math_authorization') is False and
                   meta.get('clip_filename') == mp4_name and
                   meta.get('source_video_sha256') == batch['source_video_sha256'] and
                   meta.get('table_id') == entry.get('table_id') and
                   meta.get('hand_id') == entry.get('hand_id'), 'full-frame clip provenance mismatch')
        start, length = meta.get('clip_start_seconds'), meta.get('clip_duration_seconds')
        crop.check(finite_number(start) and finite_number(length) and
                   start >= 0 and length >= .5 and
                   finite_number(entry.get('clip_start_seconds')) and
                   finite_number(entry.get('clip_duration_seconds')) and
                   abs(start - entry['clip_start_seconds']) <= 1e-5 and
                   abs(length - entry['clip_duration_seconds']) <= 1e-5,
                   'full-frame timestamp mismatch')
        crop.check(safe_id(entry.get('table_id')) and safe_id(entry.get('hand_id')),
                   'invalid table/hand ID')
        checked.extend([(mp4, mp4_sha), (meta_path, checked_sha(meta_path))])
        source[cid] = (entry, meta, mp4, meta_path)
    found = set()
    rows = []
    for entry in cropped['clips']:
        crop.check(type(entry) is dict, 'invalid crop clip entry')
        cid = entry.get('clip_id')
        crop.check(safe_id(cid) and cid in source and cid not in found,
                   'missing/duplicate matching source clip')
        found.add(cid)
        original, full_meta, full_mp4, full_json = source[cid]
        mp4_name, json_name = 'crop_' + cid + '.mp4', 'crop_' + cid + '.json'
        crop.check(entry.get('filename') == mp4_name and
                   entry.get('metadata') == json_name and
                   entry.get('table_id') == original['table_id'], 'unsafe crop clip entry')
        mp4, meta_path = crops_dir / mp4_name, crops_dir / json_name
        mp4_sha = checked_sha(mp4)
        meta = crop.read_json(meta_path)
        crop.check(entry.get('sha256') == mp4_sha and meta.get('crop_sha256') == mp4_sha and
                   meta.get('crop_filename') == mp4_name and
                   meta.get('status') == 'offline_manual_table_crop_unverified' and
                   meta.get('automatic_ocr_math_authorization') is False and
                   meta.get('clip_id') == cid and
                   meta.get('table_id') == original['table_id'] and
                   meta.get('hand_id') == original['hand_id'] and
                   meta.get('source_video_sha256') == batch['source_video_sha256'] and
                   meta.get('source_layout_sha256') == cropped['source_layout_sha256'] and
                   meta.get('source_clip_report_sha256') == checked_sha(full_json),
                   'crop clip provenance mismatch')
        crop.check(finite_number(meta.get('clip_start_seconds')) and
                   finite_number(meta.get('clip_duration_seconds_claim')) and
                   abs(meta['clip_start_seconds'] - full_meta['clip_start_seconds']) <= 1e-5 and
                   abs(meta['clip_duration_seconds_claim'] - full_meta['clip_duration_seconds']) <= 1e-5,
                   'crop timestamps differ from source')
        region = meta.get('region_claim')
        crop.check(type(region) is dict and set(region) ==
                   {'table_id', 'x', 'y', 'width', 'height'} and
                   region['table_id'] == original['table_id'] and
                   all(type(region[k]) is int for k in ('x','y','width','height')) and
                   region['x'] >= 0 and region['y'] >= 0 and
                   region['width'] >= 2 and region['height'] >= 2 and
                   region['width'] % 2 == 0 and region['height'] % 2 == 0 and
                   type(meta.get('source_width')) is int and
                   type(meta.get('source_height')) is int and
                   region['x'] + region['width'] <= meta['source_width'] and
                   region['y'] + region['height'] <= meta['source_height'],
                   'invalid crop geometry claim')
        checked.extend([(mp4, mp4_sha), (meta_path, checked_sha(meta_path))])
        rows.append((cid, original, full_meta, full_mp4, full_json, mp4, meta_path))
    crop.check(found == set(source), 'incomplete crop coverage')
    html = ['<!doctype html><html lang="pt-BR"><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            '<title>PLO Trainee - sessão e recortes</title>',
            '<style>body{font:16px system-ui;max-width:1050px;margin:2rem auto;padding:0 1rem}',
            'section{border-top:1px solid #aaa;padding:1rem 0}video{max-width:100%;width:440px}',
            '.warning{border-left:4px solid #777;padding:.7rem 1rem;background:#eee;color:#222}',
            '.pair{display:flex;flex-wrap:wrap;gap:1rem}.pair>div{flex:1 1 320px}</style>',
            '<h1>PLO Trainee — sessão e recortes por mesa</h1>',
            '<p class="warning">Geometria manual não verificada. Cartas, ações, ranges e EV ',
            'são hipóteses; diferença de EV não é veredito de erro. ',
            'Confiança humana não é probabilidade calibrada. Sem autorização OCR automática.</p>',
            '<p>Clipes auditados: ', str(len(rows)), ' · <a href="',
            escape(relative_href(crops_dir, batch_path), quote=True), '">Lote original JSON</a>',
            ' · <a href="crop_batch_report.json">Lote de recortes JSON</a></p>']
    for cid, entry, full_meta, full_mp4, full_json, mp4, meta_path in rows:
        html.extend(['<section><h2>Mesa ', escape(entry['table_id']), ' · Mão ',
                     escape(entry['hand_id']), '</h2><p>',
                     escape(str(full_meta.get('variant', 'variante incerta'))), ' · ',
                     escape(str(full_meta.get('street', 'street incerta'))),
                     ' · Ação declarada: ',
                     escape(str(full_meta.get('action_taken_claim_unverified', 'incerta'))),
                     ' · Início: ', escape(str(full_meta['clip_start_seconds'])), ' s</p>',
                     '<div class="pair"><div><h3>Gravação completa</h3><video controls preload="none" src="',
                     escape(relative_href(crops_dir, full_mp4), quote=True), '"></video><p><a href="',
                     escape(relative_href(crops_dir, full_json), quote=True),
                     '">Hipóteses / JSON original</a></p></div>',
                     '<div><h3>Recorte manual da mesa</h3><video controls preload="none" src="',
                     escape(relative_href(crops_dir, mp4), quote=True), '</video><p><a href="',
                     escape(relative_href(crops_dir, meta_path), quote=True),
                     '">Região e proveniência / JSON</a></p></div></div></section>'])
    html.append('<p>Índice estático, offline, gerado após verificação SHA-256. Não altera MP4.</p></html>')
    crop.check(all(checked_sha(p) == sha for p, sha in checked),
               'input changed during index construction')
    with tempfile.TemporaryDirectory(prefix='plo_cross_index_', dir=crops_dir) as folder:
        draft = Path(folder) / 'index.html'
        draft.write_text(''.join(html), encoding='utf-8')
        crop.check(all(checked_sha(p) == sha for p, sha in checked),
                   'input changed before publishing index')
        crop.check(not target.exists() and not target.is_symlink(), 'index appeared during build')
        os.link(draft, target)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch_dir')
    parser.add_argument('crops_dir')
    args = parser.parse_args(argv)
    print(build(args.batch_dir, args.crops_dir))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
