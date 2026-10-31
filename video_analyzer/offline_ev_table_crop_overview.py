"""Read-only local HTML index for audited manually cropped table MP4 clips.

Usage: python offline_ev_table_crop_overview.py CROPS_OUTPUT_DIR
No network access, OCR authorization, live poker or strategy verdict.
"""
from __future__ import annotations
import argparse
from html import escape
import os
from pathlib import Path
import tempfile

import offline_ev_table_crop as crop


def overview(folder):
    folder = Path(folder)
    crop.check(folder.is_dir() and not folder.is_symlink(), 'unsafe crop folder')
    target = folder / 'crop_overview.html'
    crop.check(not target.exists() and not target.is_symlink(), 'crop overview exists')
    ledger_path = folder / 'crop_batch_report.json'
    ledger = crop.read_json(ledger_path)
    crop.check(type(ledger) is dict and ledger.get('schema_version') == 1
               and ledger.get('status') == 'offline_table_crop_batch_unverified'
               and ledger.get('automatic_ocr_math_authorization') is False
               and type(ledger.get('rendered_count')) is int
               and type(ledger.get('clips')) is list
               and len(ledger['clips']) <= crop.MAX_CLIPS
               and len(ledger['clips']) == ledger['rendered_count'], 'invalid crop ledger')
    checked = [(ledger_path, crop.digest(ledger_path))]
    html = ['<!doctype html><html lang="pt-BR"><meta charset="utf-8">',
            '<title>PLO Trainee - recortes offline</title>',
            '<h1>PLO Trainee - recortes por mesa</h1>',
            '<p><strong>Geometria declarada manualmente.</strong> ',
            'Cartas, ações, ranges e EV não verificados; não é veredito estratégico.</p>',
            '<p>Clipes: ', str(ledger['rendered_count']), '</p>']
    ids = set()
    for item in ledger['clips']:
        crop.check(type(item) is dict, 'invalid crop entry')
        cid = item.get('clip_id')
        crop.check(type(cid) is str and crop.ID.fullmatch(cid) and cid not in ids,
                   'unsafe or duplicate clip ID')
        ids.add(cid)
        mp4_name, json_name = 'crop_' + cid + '.mp4', 'crop_' + cid + '.json'
        crop.check(item.get('filename') == mp4_name and item.get('metadata') == json_name,
                   'unsafe crop filenames')
        mp4, detail_path = folder / mp4_name, folder / json_name
        mp4_sha = crop.digest(mp4)
        detail = crop.read_json(detail_path)
        crop.check(item.get('sha256') == mp4_sha and detail.get('crop_sha256') == mp4_sha
                   and detail.get('crop_filename') == mp4_name
                   and detail.get('status') == 'offline_manual_table_crop_unverified'
                   and detail.get('automatic_ocr_math_authorization') is False
                   and detail.get('source_video_sha256') == ledger.get('source_video_sha256')
                   and detail.get('source_layout_sha256') == ledger.get('source_layout_sha256')
                   and detail.get('clip_id') == cid and detail.get('table_id') == item.get('table_id'),
                   'crop provenance mismatch')
        checked.extend([(mp4, mp4_sha), (detail_path, crop.digest(detail_path))])
        html.extend(['<section><h2>Mesa ', escape(str(detail['table_id'])),
                     ' · Mão ', escape(str(detail.get('hand_id'))), '</h2>',
                     '<p>Início no vídeo: ', escape(str(detail.get('clip_start_seconds'))),
                     ' s · ROI declarada: ', escape(str(detail.get('region_claim'))), '</p>',
                     '<p><a href="', escape(mp4_name, quote=True), '">MP4</a> · ',
                     '<a href="', escape(json_name, quote=True), '">JSON de proveniência</a></p>',
                     '<video controls preload="none" width="360" src="',
                     escape(mp4_name, quote=True), '"></video></section>'])
    html.append('</html>')
    crop.check(all(crop.digest(p) == sha for p, sha in checked),
               'crop files changed during HTML generation')
    with tempfile.TemporaryDirectory(prefix='plo_crop_html_', dir=folder) as temp:
        draft = Path(temp) / 'overview.html'
        draft.write_text(''.join(html), encoding='utf-8')
        crop.check(not target.exists() and not target.is_symlink(), 'crop overview appeared')
        os.link(draft, target)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('crop_output_dir')
    args = parser.parse_args(argv)
    print(overview(args.crop_output_dir))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
