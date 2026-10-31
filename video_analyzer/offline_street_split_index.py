"""Offline, read-only evidence-to-temporal-MP4 navigation index.

Usage: python offline_street_split_index.py VIDEO OBSERVATIONS STREET_DIR BATCH_DIR TEMPORAL_REVIEW SPLIT_DIR

All inputs must be previously produced offline artifacts from the same video.
Revalidates the street report from its observations, and the split plan from
its original batch and temporal review. Does not infer poker facts or authorize
OCR proposals for equity/EV. Never changes the source artifacts.
"""
from __future__ import annotations
import argparse
from html import escape
import json
import os
from pathlib import Path
import re
import tempfile

import offline_ev_table_crop as crop
import offline_street_evidence as street
import offline_temporal_split_clips as split

PAGE = 'street_split_index.html'
REPORT = 'street_split_index.json'
SHA = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, message):
    crop.check(ok, message)


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_size <= 8_000_000,
            'unsafe or oversized JSON input')
    return crop.read_json(p)


def preflight(video, observations, street_dir, batch_dir, review_json, split_dir):
    video, observations, street_dir, batch_dir, review_json, split_dir = map(
        Path, (video, observations, street_dir, batch_dir, review_json, split_dir))
    require(split_dir.is_dir() and not split_dir.is_symlink(), 'unsafe output directory')
    require(street_dir.is_dir() and not street_dir.is_symlink(), 'unsafe street directory')
    require(street_dir.resolve() != split_dir.resolve(), 'street and split directories must differ')
    for name in (PAGE, REPORT):
        split.existing.no_collision(split_dir / name)
    street_path = street_dir / street.REPORT
    split_path = split_dir / 'temporal_split_report.json'
    stored_street, stored_split = read(street_path), read(split_path)
    with tempfile.TemporaryDirectory(prefix='plo_join_check_', dir=split_dir) as tmp:
        expected_street, sources = street.validate(video, observations, tmp)
        _, _, plans, blocked, split_sources = split.preflight(video, batch_dir, review_json, tmp)
    require(stored_street == expected_street, 'street report differs from original observations')
    require(type(stored_split) is dict and stored_split.get('schema_version') == 1 and
            stored_split.get('status') == split.STATUS and
            stored_split.get('source_video_sha256') == expected_street['source_video_sha256'] and
            stored_split.get('source_temporal_review_sha256') == split_sources[1][1] and
            stored_split.get('source_batch_report_sha256') == split_sources[2][1] and
            stored_split.get('transition_guard_seconds') == split.GUARD_SECONDS and
            stored_split.get('min_part_seconds') == split.MIN_PART_SECONDS and
            stored_split.get('table_identity_verified') is False and
            stored_split.get('automatic_ocr_math_authorization') is False and
            stored_split.get('blocked') == blocked and
            stored_split.get('blocked_count') == len(blocked) and
            stored_split.get('rendered_count') == len(plans) and
            type(stored_split.get('parts')) is list and
            len(stored_split['parts']) == len(plans), 'split report or provenance mismatch')
    entries = []
    for item, plan in zip(stored_split['parts'], plans):
        expected_item = {'clip_id': plan['clip_id'], 'table_id': plan['table_id'],
                         'hand_id': plan['hand_id'], 'segment_index': plan['segment_index'],
                         'filename': plan['filename'], 'metadata': plan['metadata'],
                         'start_seconds': plan['start'], 'end_seconds': plan['end'],
                         'decision_in_part': plan['decision_in_part'],
                         'omitted_intervals_seconds': plan['omitted_intervals']}
        require(type(item) is dict and all(item.get(k) == v for k, v in expected_item.items())
                and type(item.get('sha256')) is str and SHA.fullmatch(item['sha256']),
                'unexpected split entry')
        mp4, metadata = split_dir / plan['filename'], split_dir / plan['metadata']
        require(mp4.is_file() and not mp4.is_symlink() and
                metadata.is_file() and not metadata.is_symlink(), 'unsafe split files')
        actual_sha = crop.digest(mp4)
        meta = read(metadata)
        require(actual_sha == item['sha256'] and type(meta) is dict and
                meta.get('sha256') == actual_sha and
                meta.get('status') == split.PART_STATUS and
                meta.get('source_video_sha256') == split_sources[0][1] and
                meta.get('source_temporal_review_sha256') == split_sources[1][1] and
                meta.get('source_batch_report_sha256') == split_sources[2][1] and
                meta.get('source_clip_report_sha256') == plan['source_clip_report_sha256'] and
                meta.get('clip_id') == plan['clip_id'] and
                meta.get('table_id_claim') == plan['table_id'] and
                meta.get('hand_id') == plan['hand_id'] and
                meta.get('segment_index') == plan['segment_index'] and
                meta.get('filename') == plan['filename'] and
                meta.get('region_claim') == plan['region'] and
                meta.get('start_seconds') == plan['start'] and
                meta.get('end_seconds') == plan['end'] and
                meta.get('decision_pts_seconds_claim') == plan['report']['decision_pts_seconds_claim'] and
                meta.get('decision_in_part') is plan['decision_in_part'] and
                meta.get('omitted_intervals_seconds') == plan['omitted_intervals'] and
                meta.get('table_identity_verified') is False and
                meta.get('automatic_ocr_math_authorization') is False,
                'split metadata or MP4 integrity mismatch')
        entries.append((plan, actual_sha))
    all_sources = list(sources) + list(split_sources) + [
        (street_path, crop.digest(street_path)), (split_path, crop.digest(split_path))]
    require(all(crop.digest(path) == digest for path, digest in all_sources),
            'source changed during verification')
    return expected_street, entries, blocked, all_sources


def build_index(streets, entries, blocked, all_sources):
    hands = {(h['table_id'], h['hand_id']): h for h in streets['hands']}
    by_hand = {key: [] for key in hands}
    unlinked = []
    for plan, digest in entries:
        key = (plan['table_id'], plan['hand_id'])
        hand = hands.get(key)
        pts = plan['report']['decision_pts_seconds_claim']
        link = {'clip_id': plan['clip_id'], 'table_id': key[0], 'hand_id': key[1],
                'segment_index': plan['segment_index'], 'filename': plan['filename'],
                'metadata': plan['metadata'], 'sha256': digest,
                'start_seconds': plan['start'], 'end_seconds': plan['end'],
                'decision_pts_seconds_claim': pts,
                'decision_in_part': plan['decision_in_part'],
                'omitted_intervals_seconds': plan['omitted_intervals']}
        if hand is None:
            link['reason'] = 'no_matching_street_hand'
            unlinked.append(link)
        elif not (hand['start_seconds'] <= pts <= hand['end_seconds']):
            link['reason'] = 'decision_outside_street_hand_interval'
            unlinked.append(link)
        else:
            by_hand[key].append(link)
    rows = []
    for hand in streets['hands']:
        key = (hand['table_id'], hand['hand_id'])
        rows.append({'table_id': key[0], 'hand_id': key[1],
                     'start_seconds': hand['start_seconds'], 'end_seconds': hand['end_seconds'],
                     'review_flags': hand['review_flags'], 'streets': hand['streets'],
                     'clips': by_hand[key], 'review_required': True,
                     'automatic_math_authorization': False})
    return {'schema_version': 1, 'status': 'offline_street_split_index_review_required',
            'source_video_sha256': streets['source_video_sha256'],
            'source_street_report_sha256': all_sources[-2][1],
            'source_split_report_sha256': all_sources[-1][1],
            'variant': streets['variant'], 'hands': rows, 'unlinked_clips': unlinked,
            'blocked_clips': blocked, 'confidence_calibrated': False,
            'table_identity_verified': False, 'automatic_ocr_math_authorization': False,
            'warning': 'Navigation only: evidence is unverified, geometry is a claim, and EV is conditional.'}


def page(index):
    parts = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
             '<title>PLO Trainee — Mãos e cortes</title><style>',
             'body{font:15px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}',
             'section{border:1px solid #aaa;border-radius:8px;padding:1rem;margin:1rem 0}',
             'table{width:100%;border-collapse:collapse}th,td{border:1px solid #aaa;',
             'padding:.4rem;text-align:left;overflow-wrap:anywhere}',
             'video{max-width:100%;width:420px}p{line-height:1.5}</style></head><body>',
             '<h1>Mãos e cortes temporais — revisão obrigatória</h1>',
             '<p>Propostas OCR e alegações manuais não são fatos confirmados. ',
             'A confiança não é calibrada; identidade das mesas não verificada. ',
             'Nenhuma autorização automática para equity, EV ou diagnóstico de erro.</p>']
    for hand in index['hands']:
        parts.append('<section><h2>Mesa ' + escape(hand['table_id']) + ' · Mão ' +
                     escape(hand['hand_id']) + '</h2><p>Intervalo declarado: ' +
                     escape(str(hand['start_seconds'])) + '–' +
                     escape(str(hand['end_seconds'])) + 's; conflitos: ' +
                     escape(', '.join(hand['review_flags']) or 'nenhum sinalizado') + '</p>')
        parts.append('<table><thead><tr><th>Street</th><th>Tempo</th><th>Campo</th>'
                     '<th>Proposta</th><th>Origem</th><th>Confiança não calibrada</th>'
                     '</tr></thead><tbody>')
        for street_name, events in hand['streets'].items():
            for e in events:
                value = ' '.join(e['value']) if type(e['value']) is list else e['value']
                parts.append('<tr>' + ''.join('<td>' + escape(str(v)) + '</td>' for v in
                    (street_name, e['timestamp_seconds'], e['kind'], value,
                     e['origin'], e['confidence'])) + '</tr>')
        parts.append('</tbody></table><h3>Cortes associados (vínculo por ID e timestamp)</h3>')
        if not hand['clips']:
            parts.append('<p>Nenhum corte associado; revisão manual necessária.</p>')
        for c in hand['clips']:
            parts.append('<article><p>Clip ' + escape(c['clip_id']) +
                         ' · segmento ' + str(c['segment_index']) + ' · ' +
                         escape(str(c['start_seconds'])) + '–' +
                         escape(str(c['end_seconds'])) + 's; decisão no trecho: ' +
                         ('sim' if c['decision_in_part'] else 'não') + '</p>' +
                         '<video controls preload="metadata" src="' +
                         escape(c['filename'], quote=True) + '"></video><p>' +
                         '<a href="' + escape(c['metadata'], quote=True) +
                         '">Metadados SHA-256</a></p></article>')
        parts.append('</section>')
    parts.append('<h2>Cortes sem correspondência segura</h2><ul>')
    for c in index['unlinked_clips']:
        parts.append('<li>' + escape(c['clip_id']) + ': ' + escape(c['reason']) + '</li>')
    parts.append('</ul><h2>Decisões bloqueadas</h2><ul>')
    for c in index['blocked_clips']:
        parts.append('<li>' + escape(c['clip_id']) + ': ' + escape(c['reason']) + '</li>')
    parts.append('</ul><p><a href="' + REPORT + '">Índice JSON e hashes</a></p></body></html>')
    return ''.join(parts)


def export(video, observations, street_dir, batch_dir, review_json, split_dir):
    streets, entries, blocked, sources = preflight(video, observations, street_dir,
                                                  batch_dir, review_json, split_dir)
    index = build_index(streets, entries, blocked, sources)
    output = Path(split_dir)
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix='plo_join_write_', dir=output) as tmp:
            temp = Path(tmp)
            (temp / REPORT).write_text(json.dumps(index, ensure_ascii=False, indent=2,
                                                  allow_nan=False) + '\n', encoding='utf-8')
            (temp / PAGE).write_text(page(index), encoding='utf-8')
            require(all(crop.digest(path) == digest for path, digest in sources),
                    'source changed before publication')
            for name in (REPORT, PAGE):
                split.existing.no_collision(output / name)
                os.link(temp / name, output / name)
                created.append(output / name)
        return index
    except BaseException:
        for dest in reversed(created):
            dest.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'observations', 'street_dir', 'batch_dir',
                 'temporal_review_json', 'split_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    result = export(args.video, args.observations, args.street_dir, args.batch_dir,
                    args.temporal_review_json, args.split_dir)
    print(json.dumps({'hands': len(result['hands']),
                      'linked_clips': sum(len(h['clips']) for h in result['hands']),
                      'unlinked_clips': len(result['unlinked_clips']),
                      'blocked_clips': len(result['blocked_clips'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
