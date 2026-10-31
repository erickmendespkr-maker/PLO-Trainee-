"""Auditable human review of offline street observations (never live poker).

Usage: python offline_street_human_review.py VIDEO OBSERVATIONS STREET_DIR REVIEW.json OUTPUT_DIR
The review is an explicit human assertion, not proof of optical correctness.
No automatic equity, EV, range or strategy verdict is authorized.
"""
from __future__ import annotations
import argparse
from html import escape
import json
import os
from pathlib import Path
import tempfile

import offline_ev_table_crop as media
import offline_street_evidence as street

REPORT = 'street_human_review.json'
PAGE = 'street_human_review.html'
STATUS = 'offline_human_reviewed_evidence_not_math_authorized'


def require(ok, message):
    media.check(ok, message)


def valid_value(kind, value, variant, street_name):
    if kind in ('hero_cards', 'board'):
        if type(value) is not list or not all(type(c) is str and street.CARD.fullmatch(c) for c in value):
            return False
        if len(value) != len(set(value)):
            return False
        if kind == 'hero_cards':
            return len(value) == (5 if variant == 'PLO5' else 6)
        return street_name in ('flop', 'turn', 'river') and len(value) == {
            'flop': 3, 'turn': 4, 'river': 5}[street_name]
    return type(value) is str and 1 <= len(value) <= 120 and all(ord(c) >= 32 for c in value)


def validate(video, observations, street_dir, review_file, output_dir):
    video, observations, street_dir, review_file, output_dir = map(Path, (
        video, observations, street_dir, review_file, output_dir))
    require(street_dir.is_dir() and not street_dir.is_symlink() and
            output_dir.is_dir() and not output_dir.is_symlink(), 'unsafe directories')
    paths = (video, observations, street_dir, review_file, output_dir)
    require(len({p.resolve() for p in paths}) == len(paths), 'paths must differ')
    for name in (REPORT, PAGE):
        require(not (output_dir / name).exists() and not (output_dir / name).is_symlink(),
                'output collision')
    ledger_path = street_dir / street.REPORT
    stored = media.read_json(ledger_path)
    with tempfile.TemporaryDirectory(prefix='plo_review_check_', dir=output_dir) as tmp:
        expected, original_sources = street.validate(video, observations, tmp)
    require(stored == expected, 'street report altered or mismatched')
    review = media.read_json(review_file)
    require(type(review) is dict and set(review) == {
        'schema_version', 'status', 'source_street_report_sha256', 'reviewer_label', 'hands'} and
        type(review['schema_version']) is int and review['schema_version'] == 1 and
        review['status'] == 'manual_offline_street_review' and
        review['source_street_report_sha256'] == media.digest(ledger_path) and
        type(review['reviewer_label']) is str and media.ID.fullmatch(review['reviewer_label']) and
        type(review['hands']) is list and len(review['hands']) == len(expected['hands']),
        'invalid review envelope')
    lookup = {(h['table_id'], h['hand_id']): h for h in expected['hands']}
    reviewed, seen_hands = [], set()
    for hand_review in review['hands']:
        require(type(hand_review) is dict and set(hand_review) == {
            'table_id', 'hand_id', 'decisions'}, 'invalid hand review')
        key = (hand_review['table_id'], hand_review['hand_id'])
        require(key in lookup and key not in seen_hands, 'unknown or duplicate hand')
        seen_hands.add(key)
        source = lookup[key]
        events = [(s, e) for s, items in source['streets'].items() for e in items]
        decisions = hand_review['decisions']
        require(type(decisions) is list and len(decisions) == len(events),
                'every observation must receive one review decision')
        checked, accepted = [], []
        for i, ((street_name, original), decision) in enumerate(zip(events, decisions)):
            require(type(decision) is dict and set(decision) == {
                'event_index', 'decision', 'value', 'reason'}, 'invalid decision schema')
            require(type(decision['event_index']) is int and decision['event_index'] == i and
                    decision['decision'] in ('confirm', 'correct', 'reject') and
                    type(decision['reason']) is str and len(decision['reason']) <= 300 and
                    all(ord(c) >= 32 for c in decision['reason']), 'invalid decision or reason')
            choice, value, reason = decision['decision'], decision['value'], decision['reason']
            if choice == 'confirm':
                require(value is None and reason == '', 'confirmation must not modify data')
                value = original['value']
            elif choice == 'reject':
                require(value is None and bool(reason.strip()), 'rejection needs a reason')
            else:
                require(bool(reason.strip()) and value != original['value'] and
                        valid_value(original['kind'], value, expected['variant'], street_name),
                        'invalid correction')
            item = {'event_index': i, 'timestamp_seconds': original['timestamp_seconds'],
                    'street': street_name, 'kind': original['kind'], 'decision': choice,
                    'original_value': original['value'], 'reviewed_value': value,
                    'reason': reason, 'origin': original['origin'],
                    'proposal_confidence_uncalibrated': original['confidence']}
            checked.append(item)
            if choice != 'reject':
                accepted.append(item)
        flags = []
        hero, board = None, None
        for e in accepted:
            val = e['reviewed_value']
            if e['kind'] == 'hero_cards':
                if hero is not None and hero != val:
                    flags.append('conflicting_reviewed_hero_cards')
                hero = val
            if e['kind'] == 'board':
                if board is not None and (len(val) < len(board) or val[:len(board)] != board):
                    flags.append('conflicting_reviewed_board')
                board = val
            if hero is not None and board is not None and set(hero) & set(board):
                flags.append('hero_board_overlap')
        reviewed.append({'table_id': key[0], 'hand_id': key[1],
                         'start_seconds': source['start_seconds'],
                         'end_seconds': source['end_seconds'], 'events': checked,
                         'review_flags': sorted(set(flags)),
                         'rejected_event_count': len(checked) - len(accepted),
                         'card_evidence_consistent': not flags,
                         'automatic_math_authorization': False})
    sources = list(original_sources) + [(ledger_path, media.digest(ledger_path)),
                                         (review_file, media.digest(review_file))]
    require(all(media.digest(p) == sha for p, sha in sources), 'source changed')
    return {'schema_version': 1, 'status': STATUS,
            'source_video_sha256': expected['source_video_sha256'],
            'source_observations_sha256': expected['source_observations_sha256'],
            'source_street_report_sha256': sources[-2][1],
            'source_manual_review_sha256': sources[-1][1],
            'variant': expected['variant'], 'reviewer_label': review['reviewer_label'],
            'hands': reviewed, 'confidence_calibrated': False,
            'automatic_ocr_math_authorization': False,
            'warning': 'Manual assertions are not independently verified; no equity/EV authorization.'}, sources


def page(report):
    out = ['<!doctype html><html lang="pt-BR"><meta charset="utf-8">',
           '<title>PLO Trainee — revisão humana</title>',
           '<h1>Revisão humana de evidências offline</h1>',
           '<p>Correções declaradas, não verificadas externamente. Nenhum cálculo automático autorizado.</p>']
    for hand in report['hands']:
        out.append('<section><h2>Mesa ' + escape(hand['table_id']) + ' · mão ' +
                   escape(hand['hand_id']) + '</h2><p>Conflitos: ' +
                   escape(', '.join(hand['review_flags']) or 'nenhum detectado') + '</p><ul>')
        for e in hand['events']:
            value = e['reviewed_value']
            value = ' '.join(value) if type(value) is list else str(value)
            out.append('<li>' + escape(e['street'] + ' · ' + e['kind'] + ' · ' +
                       e['decision'] + ' · ' + value + ' · ' + e['reason']) + '</li>')
        out.append('</ul></section>')
    out.append('<p><a href="' + REPORT + '">JSON auditável</a></p>')
    return ''.join(out) + '</html>'


def export(video, observations, street_dir, review_file, output_dir):
    report, sources = validate(video, observations, street_dir, review_file, output_dir)
    output = Path(output_dir)
    created = []
    try:
        with tempfile.TemporaryDirectory(prefix='plo_review_write_', dir=output) as tmp:
            tmp = Path(tmp)
            (tmp / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                 allow_nan=False) + '\n', encoding='utf-8')
            (tmp / PAGE).write_text(page(report), encoding='utf-8')
            require(all(media.digest(p) == sha for p, sha in sources), 'source changed')
            for name in (REPORT, PAGE):
                require(not (output / name).exists() and not (output / name).is_symlink(),
                        'output collision')
                os.link(tmp / name, output / name)
                created.append(output / name)
        return report
    except BaseException:
        for p in reversed(created):
            p.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'observations', 'street_dir', 'review_file', 'output_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    result = export(args.video, args.observations, args.street_dir,
                    args.review_file, args.output_dir)
    print(json.dumps({'status': result['status'], 'hands': len(result['hands'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
