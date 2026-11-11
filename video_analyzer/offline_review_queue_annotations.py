"""Offline human annotation template/validation for sparse video review candidates.

python offline_review_queue_annotations.py template QUEUE.json NEW_TEMPLATE.json
python offline_review_queue_annotations.py validate QUEUE.json FILLED.json NEW_VALIDATED.json
Never infers hands, hole cards, actions or poker math from OCR.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

CARD = re.compile(r'^[2-9TJQKA][cdhs]$')
ID = re.compile(r'^[A-Za-z0-9_.-]{1,80}$')
ACTIONS = {'fold', 'check', 'call', 'bet', 'raise'}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def read(path):
    p = Path(path)
    check(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 2_000_000, 'invalid input')
    def unique(pairs):
        d = {}
        for k,v in pairs:
            check(k not in d, 'duplicate JSON key')
            d[k] = v
        return d
    return json.loads(p.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def number(v, lo=0, hi=1e9):
    return type(v) in (int,float) and math.isfinite(v) and lo <= v <= hi


def queue_check(q):
    check(type(q) is dict and q.get('schema_version') == 1 and
          type(q.get('schema_version')) is int and
          q.get('analysis_status') == 'unverified_real_video_review_candidates' and
          q.get('hands_reconstructed') is False and
          q.get('ready_for_equity_or_ev') is False and
          q.get('automatic_clip_selection_authorized') is False and
          type(q.get('events')) is list and len(q['events']) <= 44,
          'unsafe or invalid review queue')
    for k in ('source_video_sha256','source_layout_sha256','source_probe_sha256'):
        check(type(q.get(k)) is str and re.fullmatch('[a-f0-9]{64}',q[k]), 'invalid provenance hash')
    seen = set()
    for i, e in enumerate(q['events']):
        check(type(e) is dict and e.get('event_index') == i and
              type(e.get('event_index')) is int and
              type(e.get('table_id')) is int and 1 <= e['table_id'] <= 4 and
              type(e.get('between_samples_seconds')) is list and
              len(e['between_samples_seconds']) == 2 and
              all(number(v,0,3900) for v in e['between_samples_seconds']) and
              e['between_samples_seconds'][0] < e['between_samples_seconds'][1] and
              e.get('hand_boundary_verified') is False and
              e.get('action_or_cards_verified') is False and
              e.get('ready_for_math') is False and
              e.get('status') == 'needs_human_review' and
              type(e.get('event_kinds')) is list and len(e['event_kinds']) >= 1 and
              all(x in ('table_visibility_change_unverified','pot_ocr_change_unverified')
                  for x in e['event_kinds']), 'unsafe review event')
        check(i not in seen, 'duplicate event')
        seen.add(i)


def template(q, digest):
    queue_check(q)
    return {'schema_version': 1, 'status': 'human_annotation_template_not_approved',
            'source_queue_sha256': digest,
            'source_video_sha256': q['source_video_sha256'],
            'instructions': ('Fill each item only after checking the source video. '
                             'A pot OCR change is not a hand boundary. Uncertain data stays null.'),
            'annotations': [{'event_index':e['event_index'], 'table_id':e['table_id'],
                             'review_status':'pending', 'hand_id':None,
                             'hand_start_seconds':None, 'hand_end_seconds':None,
                             'variant':None, 'hero_cards':None, 'board_cards':None,
                             'hero_action':None, 'pot_before_action_bb':None,
                             'to_call_bb':None, 'review_note':''}
                            for e in q['events']],
            'hands_reconstructed':False, 'ready_for_equity_or_ev':False}


def validate(q, filled, digest):
    queue_check(q)
    check(type(filled) is dict and filled.get('schema_version') == 1 and
          type(filled.get('schema_version')) is int and
          filled.get('status') == 'human_annotation_template_not_approved' and
          filled.get('source_queue_sha256') == digest and
          filled.get('source_video_sha256') == q['source_video_sha256'] and
          filled.get('hands_reconstructed') is False and
          filled.get('ready_for_equity_or_ev') is False and
          type(filled.get('annotations')) is list and
          len(filled['annotations']) == len(q['events']), 'annotation source mismatch')
    reviewed = []
    expected = set(template(q,digest)['annotations'][0]) if q['events'] else set()
    for original, a in zip(q['events'],filled['annotations']):
        check(type(a) is dict and set(a) == expected and
              type(a['event_index']) is int and a['event_index'] == original['event_index'] and
              type(a['table_id']) is int and a['table_id'] == original['table_id'],
              'annotation/event mismatch')
        status = a['review_status']
        check(type(status) is str and status in ('pending','rejected','reviewed_incomplete','reviewed_complete'),
              'invalid review status')
        if status in ('pending','rejected','reviewed_incomplete'):
            check(all(a[k] is None for k in ('hand_id','hand_start_seconds','hand_end_seconds',
                  'variant','hero_cards','board_cards','hero_action','pot_before_action_bb','to_call_bb')),
                  'partial or rejected annotation cannot assert a hand')
            check(type(a['review_note']) is str and len(a['review_note']) <= 500,
                  'invalid review note')
            reviewed.append({'event_index':a['event_index'],'status':status,
                             'hand_verified':False,'ready_for_equity_or_ev':False})
            continue
        check(type(a['hand_id']) is str and ID.fullmatch(a['hand_id']) and
              a['variant'] in ('PLO5','PLO6') and type(a['variant']) is str and
              number(a['hand_start_seconds'],0,3900) and
              number(a['hand_end_seconds'],0,3900) and
              a['hand_start_seconds'] < a['hand_end_seconds'] and
              a['hand_start_seconds'] <= original['between_samples_seconds'][1] and
              a['hand_end_seconds'] >= original['between_samples_seconds'][0],
              'invalid manually reviewed hand boundaries')
        n = 5 if a['variant']=='PLO5' else 6
        hole, board = a['hero_cards'],a['board_cards']
        check(type(hole) is list and len(hole)==n and
              type(board) is list and len(board) in (0,3,4,5) and
              all(type(c) is str and CARD.fullmatch(c) for c in hole+board) and
              len(set(hole+board))==len(hole+board), 'invalid or duplicated cards')
        check(type(a['hero_action']) is str and a['hero_action'] in ACTIONS and
              number(a['pot_before_action_bb'],0,1e6) and
              number(a['to_call_bb'],0,1e6) and
              type(a['review_note']) is str and 5 <= len(a['review_note'].strip()) <= 500,
              'incomplete manual action evidence')
        reviewed.append({'event_index':a['event_index'],'status':status,
                         'hand_verified':False,'ready_for_equity_or_ev':False,
                         'hand_id_claim':a['hand_id']})
    return {'schema_version':1,'status':'manual_annotations_schema_validated_not_independently_verified',
            'source_queue_sha256':digest,
            'source_video_sha256':q['source_video_sha256'],
            'reviewed':reviewed,'hands_independently_verified':False,
            'ready_for_equity_or_ev':False,
            'warning':'Schema validation cannot verify actual cards/actions or certify strategic analysis.'}


def run(mode, queue_path, filled_path, output_path):
    inputs = [Path(queue_path)] + ([Path(filled_path)] if filled_path else [])
    out = Path(output_path)
    check(out.suffix=='.json' and out.parent.is_dir() and not out.parent.is_symlink() and
          not out.exists() and not out.is_symlink() and
          out.resolve() not in [p.resolve() for p in inputs], 'output must be a new JSON file')
    hashes = [sha(p) for p in inputs]
    q = read(queue_path)
    result = template(q, hashes[0]) if mode=='template' else validate(q,read(filled_path),hashes[0])
    check(hashes == [sha(p) for p in inputs], 'source modified during review')
    with tempfile.TemporaryDirectory(prefix='.plo_review_',dir=out.parent) as d:
        stage = Path(d)/'result.json'
        stage.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n','utf-8')
        os.link(stage,out)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['template','validate'])
    p.add_argument('queue');p.add_argument('paths',nargs='+')
    a=p.parse_args()
    check(len(a.paths)==(1 if a.mode=='template' else 2), 'wrong arguments')
    print(json.dumps(run(a.mode,a.queue,a.paths[0] if a.mode=='validate' else None,a.paths[-1])['status']))

if __name__=='__main__':main()
