"""Offline, human-review-only street evidence ledger from timestamped observations.

Usage: python offline_street_evidence.py VIDEO.mp4 OBSERVATIONS.json EMPTY_OUTPUT_DIR
No OCR recognition is performed here; observations are untrusted OCR proposals or
human claims. Never authorize automatic equity/EV or assert hidden cards.
"""
from __future__ import annotations
import argparse
from html import escape
import json
import math
import os
from pathlib import Path
import re
import tempfile

import offline_ev_table_crop as media

STREETS = ('preflop', 'flop', 'turn', 'river')
KINDS = ('hero_cards', 'board', 'pot', 'stack', 'action')
CARD = re.compile(r'[2-9TJQKA][CDHS]\Z')
REPORT = 'street_evidence_report.json'
PAGE = 'street_evidence_overview.html'
MAX_HANDS = 500
MAX_EVENTS = 200


def require(ok, reason):
    media.check(ok, reason)


def number(x, lower, upper):
    return type(x) in (int, float) and math.isfinite(x) and lower <= x <= upper


def validate(video, observations, output):
    video, observations, output = map(Path, (video, observations, output))
    require(video.suffix.lower() in ('.mp4', '.mov', '.webm'), 'unsupported video')
    media.safe_file(video)
    require(output.is_dir() and not output.is_symlink(), 'unsafe output directory')
    require(len({p.resolve() for p in (video, observations, output)}) == 3,
            'inputs and output must differ')
    for name in (REPORT, PAGE):
        require(not (output / name).exists() and not (output / name).is_symlink(),
                'output already exists')
    _, _, duration = media.media_info(video)
    video_sha = media.digest(video)
    source_sha = media.digest(observations)
    raw = media.read_json(observations)
    require(type(raw) is dict and set(raw) ==
            {'schema_version', 'status', 'source_video_sha256', 'variant', 'hands'} and
            type(raw['schema_version']) is int and raw['schema_version'] == 1 and
            raw['status'] == 'offline_unverified_street_observations' and
            raw['source_video_sha256'] == video_sha and
            raw['variant'] in ('PLO5', 'PLO6') and
            type(raw['hands']) is list and 1 <= len(raw['hands']) <= MAX_HANDS,
            'invalid observations or video hash')
    hand_ids, tables, hands = set(), set(), []
    for hand in raw['hands']:
        require(type(hand) is dict and set(hand) ==
                {'table_id', 'hand_id', 'start_seconds', 'end_seconds', 'events'},
                'invalid hand schema')
        table, hid = hand['table_id'], hand['hand_id']
        require(all(type(x) is str and media.ID.fullmatch(x) for x in (table, hid)) and
                (table, hid) not in hand_ids, 'unsafe or duplicate hand identity')
        hand_ids.add((table, hid)); tables.add(table)
        require(len(tables) <= 4, 'more than four tables')
        start, end = hand['start_seconds'], hand['end_seconds']
        require(number(start, 0, duration) and number(end, 0, duration + .05) and
                end > start, 'invalid hand interval')
        events = hand['events']
        require(type(events) is list and len(events) <= MAX_EVENTS,
                'invalid event list')
        prev_t, prev_street = start, -1
        boards, hero, flags = [], None, set()
        streets = {s: [] for s in STREETS}
        for e in events:
            require(type(e) is dict and set(e) ==
                    {'timestamp_seconds', 'street', 'kind', 'value', 'origin', 'confidence'},
                    'invalid evidence schema')
            t, street, kind = e['timestamp_seconds'], e['street'], e['kind']
            require(number(t, start, end) and t >= prev_t and
                    street in STREETS and STREETS.index(street) >= prev_street and
                    kind in KINDS and e['origin'] in ('ocr_proposal', 'manual_claim') and
                    number(e['confidence'], 0, 1), 'invalid timestamp/street/evidence')
            prev_t, prev_street = t, STREETS.index(street)
            val = e['value']
            if kind in ('hero_cards', 'board'):
                require(type(val) is list and all(type(c) is str and CARD.fullmatch(c)
                        for c in val) and len(val) == len(set(val)), 'invalid cards')
                if kind == 'hero_cards':
                    require(len(val) == (5 if raw['variant'] == 'PLO5' else 6),
                            'wrong hero-card count')
                    if hero is not None and hero != val:
                        flags.add('conflicting_hero_proposals')
                    hero = val
                else:
                    require(street != 'preflop' and len(val) ==
                            {'flop': 3, 'turn': 4, 'river': 5}[street],
                            'board length/street mismatch')
                    if boards and (len(val) < len(boards[-1]) or
                                   val[:len(boards[-1])] != boards[-1]):
                        flags.add('conflicting_board_proposals')
                    boards.append(val)
                if hero is not None and boards and set(hero) & set(boards[-1]):
                    flags.add('hero_board_card_conflict')
            else:
                require(type(val) is str and 1 <= len(val) <= 120 and
                        all(ord(ch) >= 32 for ch in val), 'invalid textual evidence')
            streets[street].append(e)
        hands.append({'table_id': table, 'hand_id': hid,
                      'start_seconds': start, 'end_seconds': end,
                      'streets': streets, 'review_flags': sorted(flags),
                      'event_count': len(events), 'review_required': True,
                      'automatic_math_authorization': False})
    require(all(media.digest(p) == sha for p, sha in
                 ((video, video_sha), (observations, source_sha))), 'source changed')
    return ({'schema_version': 1, 'status': 'offline_street_evidence_review_required',
            'source_video_sha256': video_sha, 'source_observations_sha256': source_sha,
            'variant': raw['variant'], 'table_count': len(tables), 'hand_count': len(hands),
            'hands': hands, 'confidence_calibrated': False,
            'automatic_ocr_math_authorization': False,
            'warning': 'Only visible proposals and human claims; no inferred hidden cards, verified action or EV.'},
            ((video, video_sha), (observations, source_sha)))


def html_page(report):
    sections = []
    for hand in report['hands']:
        rows = []
        for street, events in hand['streets'].items():
            for event in events:
                value = event['value']
                if type(value) is list:
                    value = ' '.join(value)
                rows.append('<tr><td>' + escape(street) + '</td><td>' +
                            escape(str(event['timestamp_seconds'])) + '</td><td>' +
                            escape(event['kind']) + '</td><td>' + escape(value) +
                            '</td><td>' + escape(event['origin']) + '</td><td>' +
                            escape(str(event['confidence'])) + '</td></tr>')
        sections.append('<section><h2>Mesa ' + escape(hand['table_id']) +
                        ' · Mão ' + escape(hand['hand_id']) + '</h2><p>Intervalo: ' +
                        escape(str(hand['start_seconds'])) + '–' +
                        escape(str(hand['end_seconds'])) + 's; revisão obrigatória.</p>' +
                        '<p>Conflitos: ' + escape(', '.join(hand['review_flags']) or 'nenhum sinalizado') +
                        '</p><table><thead><tr><th>Street</th><th>Tempo</th><th>Campo</th>' +
                        '<th>Proposta</th><th>Origem</th><th>Confiança não calibrada</th>' +
                        '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></section>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<title>PLO Trainee — evidências por street</title><style>'
            'body{font:15px sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}'
            'table{border-collapse:collapse;width:100%;overflow-wrap:anywhere}'
            'th,td{border:1px solid #888;padding:.4rem;text-align:left}'
            'section{margin:2rem 0}p{line-height:1.5}</style></head><body>'
            '<h1>Evidências por street — revisão humana obrigatória</h1>'
            '<p>Propostas OCR e alegações manuais não são fatos confirmados. '
            'Confiança não calibrada. Nenhuma autorização automática para equity, EV '
            'ou classificação de erros.</p>' + ''.join(sections) +
            '<p><a href="street_evidence_report.json">Histórico JSON e SHA-256</a></p>'
            '</body></html>')


def export(video, observations, output):
    report, sources = validate(video, observations, output)
    out = Path(output)
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix='plo_streets_', dir=out) as folder:
            tmp = Path(folder)
            (tmp / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                 allow_nan=False) + '\n', encoding='utf-8')
            (tmp / PAGE).write_text(html_page(report), encoding='utf-8')
            require(all(media.digest(p) == sha for p, sha in sources), 'source changed')
            for name in (REPORT, PAGE):
                require(not (out / name).exists() and not (out / name).is_symlink(),
                        'output collision')
                os.link(tmp / name, out / name)
                created.append(out / name)
        return report
    except BaseException:
        for file in reversed(created):
            file.unlink(missing_ok=True)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('video', 'observations', 'output_dir'):
        p.add_argument(arg)
    a = p.parse_args(argv)
    result = export(a.video, a.observations, a.output_dir)
    print(json.dumps({'status': result['status'], 'hands': result['hand_count'],
                      'tables': result['table_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
