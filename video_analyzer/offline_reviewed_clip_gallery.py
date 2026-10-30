"""Offline, read-only gallery for human-reviewed MP4 cuts and optional conditional EV.

This does not identify hands, recognize cards, infer opponents, or grade actions.
It verifies file identity and declared provenance; hashes do not prove video content.
Usage: python offline_reviewed_clip_gallery.py CLIP_DIR NEW_INDEX_HTML [ATTACHMENTS_JSON]
Attachments must be local files within CLIP_DIR and are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re

ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def local_file(root, name, suffix=None, limit=None):
    require(type(name) is str and name == Path(name).name and name not in ('.', '..')
            and '/' not in name and '\\' not in name, 'unsafe file name')
    p = root / name
    require(p.is_file() and not p.is_symlink(), 'missing or linked file')
    require(suffix is None or p.suffix == suffix, 'wrong file extension')
    require(limit is None or p.stat().st_size <= limit, 'file too large')
    return p


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def number(x, minimum=0, maximum=1e9):
    return type(x) in (int, float) and math.isfinite(x) and minimum <= x <= maximum


def analysis(root, hand, clip_sha, video_sha, item):
    require(type(item) is dict and set(item) == {'acknowledged_report', 'sensitivity'},
            'invalid analysis attachment')
    rp = local_file(root, item['acknowledged_report'], '.json', 2_000_000)
    sp = local_file(root, item['sensitivity'], '.json', 4_000_000)
    require(rp != sp, 'analysis files must differ')
    report, sens = read_json(rp), read_json(sp)
    require(type(report) is dict and report.get('schema_version') == 1 and
            report.get('analysis_status') ==
            'offline_conditional_equity_after_human_frame_acknowledgement' and
            report.get('human_snapshot_acknowledgement_validated') is True and
            report.get('source_clip_sha256') == clip_sha and
            report.get('source_video_sha256_claim_from_binding') == video_sha and
            report.get('hand_id') == hand and
            report.get('hero_actor_at_selected_action_verified') is False and
            report.get('selected_action_strategic_correctness_verified') is False and
            report.get('card_visibility_machine_verified') is False,
            'unbound or unsupported acknowledged report')
    eq = report.get('equity_result')
    require(type(eq) is dict and eq.get('variant') in ('PLO5', 'PLO6') and
            number(eq.get('equity'), 0, 1), 'invalid conditional equity')
    require(type(sens) is dict and sens.get('schema_version') == 1 and
            sens.get('analysis_status') ==
            'offline_hypothetical_ev_sensitivity_not_an_action_grade' and
            sens.get('source_acknowledged_report_sha256') == sha(rp) and
            sens.get('source_clip_sha256') == clip_sha and
            sens.get('source_hand_id') == hand and
            sens.get('variant') == eq['variant'] and
            sens.get('hero_cards') == eq.get('hero_cards') and
            sens.get('board_cards') == eq.get('board_cards') and
            sens.get('action_observed_or_graded') is False and
            sens.get('range_models_are_reviewer_assumptions') is True and
            sens.get('fold_probabilities_are_assumptions') is True and
            sens.get('confidence_intervals_cover_sampling_only') is True,
            'unbound or overstated EV sensitivity')
    require(type(sens.get('hypotheses')) is list and
            1 <= len(sens['hypotheses']) <= 5, 'invalid sensitivity hypotheses')
    return {'variant': eq['variant'], 'equity': eq['equity'],
            'hypotheses': len(sens['hypotheses']),
            'acknowledged_report': rp.name, 'sensitivity': sp.name,
            'acknowledged_report_sha256': sha(rp), 'sensitivity_sha256': sha(sp)}


def build(root, attachments=None):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'invalid clip directory')
    mp = local_file(root, 'manifest.json', '.json', 2_000_000)
    manifest = read_json(mp)
    require(type(manifest) is dict and manifest.get('schema_version') == 1 and
            manifest.get('status') == 'human_reviewed_clips_not_verified_hands' and
            manifest.get('automatic_hand_detection') is False and
            manifest.get('equity_or_ev_calculated') is False and
            type(manifest.get('source_video_sha256')) is str and
            SHA.fullmatch(manifest['source_video_sha256']), 'invalid clip manifest')
    clips = manifest.get('clips')
    require(type(clips) is list and 1 <= len(clips) <= 100, 'invalid clip count')
    entries, seen = [], set()
    for clip in clips:
        require(type(clip) is dict, 'invalid clip entry')
        hand = clip.get('hand_id')
        require(type(hand) is str and ID.fullmatch(hand) and hand not in seen,
                'invalid or repeated hand ID')
        seen.add(hand)
        require(clip.get('file') == hand + '.mp4' and
                clip.get('sidecar') == hand + '.mp4.json' and
                type(clip.get('clip_sha256')) is str and SHA.fullmatch(clip['clip_sha256']),
                'unsafe clip declaration')
        video = local_file(root, clip['file'], '.mp4')
        sidecar = local_file(root, clip['sidecar'], '.json', 2_000_000)
        require(sha(video) == clip['clip_sha256'], 'MP4 hash mismatch')
        info = read_json(sidecar)
        require(type(info) is dict and info.get('schema_version') == 1 and
                info.get('analysis_status') == 'manually_selected_offline_clip' and
                info.get('hand_id') == hand and
                info.get('clip_sha256') == clip['clip_sha256'] and
                info.get('source_video_sha256') == manifest['source_video_sha256'] and
                info.get('video_evidence_verified') is False and
                info.get('automatic_clip_selection_authorized') is False and
                number(info.get('start_seconds'), 0, 4*3600) and
                number(info.get('end_seconds'), 0, 4*3600) and
                info['end_seconds'] > info['start_seconds'] and
                type(info.get('explanation')) is str and
                1 <= len(info['explanation'].strip()) <= 1000,
                'invalid clip sidecar')
        require(type(clip.get('source_table_id')) is str and
                ID.fullmatch(clip['source_table_id']), 'invalid table ID')
        entries.append({'hand_id': hand, 'table_id': clip['source_table_id'],
                        'video': video.name, 'clip_sha256': clip['clip_sha256'],
                        'sidecar': sidecar.name, 'sidecar_sha256': sha(sidecar),
                        'start_seconds': info['start_seconds'],
                        'end_seconds': info['end_seconds'],
                        'explanation': info['explanation'], 'analysis': None})
    if attachments is not None:
        a = read_json(local_file(root, attachments, '.json', 2_000_000))
        require(type(a) is dict and set(a) == {'schema_version', 'analyses'} and
                a['schema_version'] == 1 and type(a['analyses']) is dict and
                set(a['analyses']) <= seen, 'invalid attachment index')
        for entry in entries:
            if entry['hand_id'] in a['analyses']:
                entry['analysis'] = analysis(root, entry['hand_id'], entry['clip_sha256'],
                                             manifest['source_video_sha256'],
                                             a['analyses'][entry['hand_id']])
    return {'schema_version': 1,
            'status': 'offline_human_reviewed_clip_gallery_not_hand_detection',
            'source_manifest_sha256': sha(mp),
            'source_video_sha256_claim': manifest['source_video_sha256'],
            'clips': entries, 'action_graded': False,
            'visual_card_recognition_verified': False,
            'range_or_fold_probability_observed': False}


def render(result):
    cards = []
    for item in result['clips']:
        hand = escape(item['hand_id']); table = escape(item['table_id'])
        notes = escape(item['explanation'])
        extra = '<p>Sem análise matemática anexada. Nenhuma equity ou EV foi inferida.</p>'
        if item['analysis']:
            a = item['analysis']
            extra = (f'<p>Equity condicional {100*a["equity"]:.2f}% ({a["variant"]}); '
                     f'{a["hypotheses"]} hipótese(s) de EV. Ranges e fold são suposições; '
                     'IC de Monte Carlo cobre apenas amostragem. Não é nota da jogada.</p>'
                     f'<p><a href="{escape(a["acknowledged_report"], quote=True)}">'
                     'Relatório de cartas declaradas</a> · '
                     f'<a href="{escape(a["sensitivity"], quote=True)}">'
                     'Sensibilidade hipotética JSON</a></p>')
        cards.append(f'<article><h2>{hand} · {table}</h2>'
                     f'<p>{item["start_seconds"]:.3f}–{item["end_seconds"]:.3f} s</p>'
                     f'<video controls preload="metadata" src="{escape(item["video"], quote=True)}"></video>'
                     f'<p>{notes}</p>{extra}</article>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'media-src \'self\' blob:; style-src \'unsafe-inline\';">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PLO Trainee — cortes revisados</title>'
            '<style>body{font:16px system-ui;max-width:850px;margin:2rem auto;padding:0 1rem;'
            'background:#f8fafc;color:#172332}article{background:white;border:1px solid #d6dfe8;'
            'padding:1rem;border-radius:12px;margin:1rem 0}video{width:100%;max-height:460px;'
            'background:#101820}p{line-height:1.5}</style></head><body>'
            '<h1>PLO Trainee · Cortes de revisão humana</h1><p>Vídeos gravados; '
            'intervalos declarados por revisor, não mãos identificadas automaticamente. '
            'Hashes confirmam identidade de arquivos, não precisão de OCR ou cartas.</p>'
            + ''.join(cards) + '</body></html>')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('clip_dir'); p.add_argument('new_index_html')
    p.add_argument('attachments_json', nargs='?')
    args = p.parse_args(argv)
    root = Path(args.clip_dir)
    dest = Path(args.new_index_html)
    require(dest.parent.resolve() == root.resolve() and dest.suffix == '.html' and
            not dest.exists() and not dest.is_symlink(), 'output must be a new HTML inside clip directory')
    before = sha(local_file(root, 'manifest.json'))
    result = build(root, args.attachments_json)
    html = render(result)
    require(sha(local_file(root, 'manifest.json')) == before, 'manifest changed during rendering')
    with dest.open('x', encoding='utf-8') as f:
        f.write(html)
    print(json.dumps({'index': str(dest), 'clips': len(result['clips']),
                      'conditional_analyses': sum(x['analysis'] is not None for x in result['clips']),
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
