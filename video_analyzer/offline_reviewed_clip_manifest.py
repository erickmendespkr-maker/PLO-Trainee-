"""Join human-reviewed street evidence with offline MP4 clips, for navigation only.

Usage: python offline_reviewed_clip_manifest.py REVIEWED_JSON INDEX_JSON SPLIT_DIR OUT_DIR
Inputs are existing reports from offline_street_human_review and
offline_street_split_index. This join never authorizes equity/EV or proves OCR.
The original upstream validators must be run to establish source provenance.
"""
from __future__ import annotations
import argparse
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote

REPORT = 'reviewed_clip_manifest.json'
PAGE = 'reviewed_clip_manifest.html'
STATUS = 'offline_reviewed_clip_navigation_only'
SAFE_MP4 = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,180}\.mp4\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')


def check(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    path = Path(path)
    check(path.is_file() and not path.is_symlink() and path.stat().st_size <= 8_000_000,
          'unsafe or oversized JSON')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            check(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def no_constant(x):
        raise ValueError('non-finite JSON constant')
    with path.open(encoding='utf-8') as f:
        return json.load(f, object_pairs_hook=unique, parse_constant=no_constant)


def number(x):
    return type(x) in (int, float) and math.isfinite(x)


def validate(review_path, index_path, split_dir, output_dir):
    review_path, index_path, split_dir, output_dir = map(
        Path, (review_path, index_path, split_dir, output_dir))
    check(split_dir.is_dir() and not split_dir.is_symlink() and
          output_dir.is_dir() and not output_dir.is_symlink(), 'unsafe directory')
    check(len({p.resolve() for p in (review_path, index_path, split_dir, output_dir)}) == 4,
          'source/output paths must differ')
    for name in (REPORT, PAGE):
        check(not (output_dir / name).exists() and not (output_dir / name).is_symlink(),
              'output collision')
    review, index = read_json(review_path), read_json(index_path)
    check(type(review) is dict and type(index) is dict, 'invalid report')
    check(review.get('schema_version') == index.get('schema_version') == 1 and
          review.get('status') == 'offline_human_reviewed_evidence_not_math_authorized' and
          index.get('status') == 'offline_street_split_index_review_required' and
          review.get('variant') == index.get('variant') and
          review.get('variant') in ('PLO5', 'PLO6') and
          type(review.get('source_video_sha256')) is str and
          HEX.fullmatch(review['source_video_sha256']) and
          review['source_video_sha256'] == index.get('source_video_sha256') and
          review.get('source_street_report_sha256') == index.get('source_street_report_sha256') and
          type(review.get('source_street_report_sha256')) is str and
          HEX.fullmatch(review['source_street_report_sha256']) and
          review.get('automatic_ocr_math_authorization') is False and
          index.get('automatic_ocr_math_authorization') is False and
          review.get('confidence_calibrated') is False and
          index.get('confidence_calibrated') is False and
          index.get('table_identity_verified') is False,
          'incompatible or unauthorized reports')
    rh, ih = review.get('hands'), index.get('hands')
    check(type(rh) is list and type(ih) is list and len(rh) == len(ih) and
          1 <= len(rh) <= 500, 'hand count mismatch')
    lookup = {}
    for hand in ih:
        check(type(hand) is dict and type(hand.get('table_id')) is str and
              type(hand.get('hand_id')) is str, 'invalid index hand')
        key = (hand['table_id'], hand['hand_id'])
        check(key not in lookup, 'duplicate index hand')
        lookup[key] = hand
    rows, seen, clip_ids = [], set(), set()
    for hand in rh:
        check(type(hand) is dict and type(hand.get('table_id')) is str and
              type(hand.get('hand_id')) is str, 'invalid reviewed hand')
        key = (hand['table_id'], hand['hand_id'])
        check(key in lookup and key not in seen, 'unknown/duplicate reviewed hand')
        seen.add(key)
        base = lookup[key]
        check(number(hand.get('start_seconds')) and number(hand.get('end_seconds')) and
              hand['start_seconds'] == base.get('start_seconds') and
              hand['end_seconds'] == base.get('end_seconds') and
              hand['start_seconds'] < hand['end_seconds'] and
              hand.get('automatic_math_authorization') is False and
              base.get('automatic_math_authorization') is False and
              type(hand.get('events')) is list and type(base.get('streets')) is dict and
              type(hand.get('review_flags')) is list and
              type(hand.get('card_evidence_consistent')) is bool,
              'invalid reviewed hand envelope')
        original = [(s, e) for s, events in base['streets'].items() for e in events]
        check(len(original) == len(hand['events']) and len(original) <= 200,
              'event count mismatch')
        events = []
        for i, (event, (street, proposal)) in enumerate(zip(hand['events'], original)):
            check(type(event) is dict and type(proposal) is dict and
                  type(event.get('event_index')) is int and event['event_index'] == i and
                  event.get('street') == street and event.get('kind') == proposal.get('kind') and
                  event.get('timestamp_seconds') == proposal.get('timestamp_seconds') and
                  event.get('original_value') == proposal.get('value') and
                  event.get('origin') == proposal.get('origin') and
                  event.get('proposal_confidence_uncalibrated') == proposal.get('confidence') and
                  event.get('decision') in ('confirm', 'correct', 'reject'),
                  'review does not match street proposal')
            choice = event['decision']
            if choice == 'confirm':
                check(event.get('reviewed_value') == event.get('original_value') and
                      event.get('reason') == '', 'invalid confirmation')
            elif choice == 'reject':
                check(event.get('reviewed_value') is None and
                      type(event.get('reason')) is str and bool(event['reason'].strip()),
                      'invalid rejection')
            else:
                check(event.get('reviewed_value') != event.get('original_value') and
                      event.get('reviewed_value') is not None and
                      type(event.get('reason')) is str and bool(event['reason'].strip()),
                      'invalid correction')
            events.append({'timestamp_seconds': event['timestamp_seconds'],
                           'street': street, 'kind': event['kind'],
                           'decision': choice, 'value': event['reviewed_value'],
                           'reason': event.get('reason', ''),
                           'source_origin': event['origin'],
                           'proposal_confidence_uncalibrated': event['proposal_confidence_uncalibrated']})
        clips = []
        check(type(base.get('clips')) is list and len(base['clips']) <= 1000,
              'invalid clips')
        for c in base['clips']:
            check(type(c) is dict and type(c.get('filename')) is str and
                  SAFE_MP4.fullmatch(c['filename']) and
                  type(c.get('sha256')) is str and HEX.fullmatch(c['sha256']) and
                  type(c.get('clip_id')) is str and type(c.get('segment_index')) is int and
                  type(c.get('decision_in_part')) is bool and
                  number(c.get('start_seconds')) and number(c.get('end_seconds')) and
                  c['start_seconds'] < c['end_seconds'] and
                  c.get('table_id') == key[0] and c.get('hand_id') == key[1],
                  'invalid clip metadata')
            identity = (c['clip_id'], c['segment_index'])
            check(identity not in clip_ids, 'duplicate clip segment')
            clip_ids.add(identity)
            file = split_dir / c['filename']
            check(file.is_file() and not file.is_symlink() and digest(file) == c['sha256'],
                  'MP4 missing or modified')
            clips.append({'clip_id': c['clip_id'], 'segment_index': c['segment_index'],
                          'filename': c['filename'], 'sha256': c['sha256'],
                          'start_seconds': c['start_seconds'],
                          'end_seconds': c['end_seconds'],
                          'decision_in_part': c['decision_in_part']})
        rows.append({'table_id': key[0], 'hand_id': key[1],
                     'start_seconds': hand['start_seconds'],
                     'end_seconds': hand['end_seconds'],
                     'review_flags': hand['review_flags'],
                     'card_evidence_consistent_claim': hand['card_evidence_consistent'],
                     'events': events, 'clips': clips,
                     'automatic_math_authorization': False})
    check(type(index.get('unlinked_clips')) is list and
          type(index.get('blocked_clips')) is list, 'missing blocked/unlinked records')
    sources = [(review_path, digest(review_path)), (index_path, digest(index_path))]
    return ({'schema_version': 1, 'status': STATUS, 'variant': review['variant'],
             'source_video_sha256': review['source_video_sha256'],
             'source_reviewed_report_sha256': sources[0][1],
             'source_street_index_sha256': sources[1][1],
             'reviewer_label': review.get('reviewer_label'), 'hands': rows,
             'unlinked_clip_count': len(index['unlinked_clips']),
             'blocked_clip_count': len(index['blocked_clips']),
             'confidence_calibrated': False, 'table_identity_verified': False,
             'automatic_math_authorization': False,
             'warning': 'Navigation only. Human assertions are not optical proof; no equity/EV authorization.'},
            sources)


def page(report, media_prefix):
    out = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
           '<title>PLO Trainee — revisão e clipes</title>',
           '<style>body{font:15px system-ui;max-width:1000px;margin:2rem auto;padding:1rem}',
           'section{border:1px solid #aaa;border-radius:8px;padding:1rem;margin:1rem 0}',
           'video{max-width:100%;width:420px}li{margin:.5rem 0}</style></head><body>',
           '<h1>Revisão humana vinculada aos clipes</h1>',
           '<p>Associações por ID e timestamp. Dados não são prova óptica; sem autorização de equity/EV.</p>']
    for h in report['hands']:
        out.append('<section><h2>Mesa ' + escape(h['table_id']) + ' · mão ' +
                   escape(h['hand_id']) + '</h2><p>Conflitos declarados: ' +
                   escape(', '.join(h['review_flags']) or 'nenhum') + '</p><ul>')
        for e in h['events']:
            value = e['value']
            value = ' '.join(value) if type(value) is list else str(value)
            out.append('<li>' + escape(e['street'] + ' · ' + e['kind'] + ' · ' +
                       e['decision'] + ' · ' + value + ' · ' + e['reason']) + '</li>')
        out.append('</ul>')
        for c in h['clips']:
            out.append('<p>' + escape(c['clip_id']) + ' · trecho ' +
                       str(c['segment_index']) + '</p><video controls preload="metadata" src="' +
                       escape(quote(media_prefix + '/' + c['filename'], safe='/.'), quote=True) + '"></video>')
        out.append('</section>')
    out.append('<p>Clipes sem vínculo: ' + str(report['unlinked_clip_count']) +
               ' · bloqueados: ' + str(report['blocked_clip_count']) + '</p>')
    out.append('<p><a href="' + REPORT + '">Manifesto JSON</a></p></body></html>')
    return ''.join(out)


def export(review_path, index_path, split_dir, output_dir):
    result, sources = validate(review_path, index_path, split_dir, output_dir)
    out, created = Path(output_dir), []
    try:
        with tempfile.TemporaryDirectory(prefix='plo_reviewed_clip_', dir=out) as tmp:
            temp = Path(tmp)
            (temp / REPORT).write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                 allow_nan=False) + '\n', encoding='utf-8')
            (temp / PAGE).write_text(page(result, Path(os.path.relpath(split_dir, out)).as_posix()), encoding='utf-8')
            check(all(digest(p) == sha for p, sha in sources), 'sources changed')
            for h in result['hands']:
                for c in h['clips']:
                    check(digest(Path(split_dir) / c['filename']) == c['sha256'], 'MP4 changed')
            for name in (REPORT, PAGE):
                check(not (out / name).exists() and not (out / name).is_symlink(),
                      'output collision')
                os.link(temp / name, out / name)
                created.append(out / name)
        return result
    except BaseException:
        for p in reversed(created):
            p.unlink(missing_ok=True)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('reviewed_json', 'street_split_index_json', 'split_dir', 'output_dir'):
        p.add_argument(arg)
    a = p.parse_args(argv)
    result = export(a.reviewed_json, a.street_split_index_json, a.split_dir, a.output_dir)
    print(json.dumps({'hands': len(result['hands']),
                      'clips': sum(len(h['clips']) for h in result['hands'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())