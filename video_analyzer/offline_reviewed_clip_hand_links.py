"""Offline, fail-closed provenance links: reviewed hand candidates -> exported MP4 batch.

Usage: python offline_reviewed_clip_hand_links.py RECORDING HANDS_JSON
       BATCH_MANIFEST_JSON BATCH_DIRECTORY NEW_REPORT_JSON [--equity REPORT ...]

This is a consistency audit, NOT independent OCR, reviewer, equity or EV verification.
Never selects clips, alters MP4s or authorizes action recommendations.
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

MAX_JSON = 4 * 1024 * 1024
SAFE_FILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), 'Missing or symlinked input')
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique(pairs):
    d = {}
    for key, value in pairs:
        require(key not in d, 'Duplicate JSON key')
        d[key] = value
    return d


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
            'Invalid JSON file')
    return json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def number(v):
    require(type(v) in (int, float) and math.isfinite(v), 'Invalid timestamp')
    return float(v)


def safe_member(directory, name):
    require(type(name) is str and SAFE_FILE.fullmatch(name) and name not in ('.', '..'),
            'Unsafe batch filename')
    p = directory / name
    require(p.parent == directory and p.is_file() and not p.is_symlink(),
            'Missing or symlinked batch member')
    return p


def link(recording, hands_path, manifest_path, batch_directory, output_path,
         *, equity_paths=()):
    recording, hands_path, manifest_path = map(Path, (recording, hands_path, manifest_path))
    directory, output = Path(batch_directory), Path(output_path)
    require(directory.is_dir() and not directory.is_symlink(), 'Invalid batch directory')
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            not output.resolve().is_relative_to(directory.resolve()),
            'Output must be new and outside batch directory')
    equity_paths = tuple(map(Path, equity_paths))
    inputs = (recording, hands_path, manifest_path, directory / 'batch_report.json', *equity_paths)
    require(all(output.resolve() != p.resolve() for p in inputs), 'Output overlaps input')
    initial = {str(p.resolve()): sha(p) for p in inputs}
    video_sha, hands_sha, manifest_sha = (initial[str(p.resolve())]
                                          for p in (recording, hands_path, manifest_path))
    hands, manifest, batch = read(hands_path), read(manifest_path), read(directory / 'batch_report.json')
    require(type(hands) is dict and hands.get('schema_version') == 1 and
            hands.get('recording_sha256') == video_sha and
            hands.get('analysis_status') == 'human_declared_incomplete_hand_candidates' and
            hands.get('complete_hand_reconstructed') is False and
            hands.get('automatic_clip_selection_authorized') is False and
            type(hands.get('hands')) is list,
            'Untrusted hand candidate report')
    require(type(manifest) is dict and manifest.get('schema_version') == 1 and
            manifest.get('source_video_sha256') == video_sha and
            manifest.get('reviewer_confirmed_offline') is True and
            type(manifest.get('clips')) is list,
            'Untrusted batch manifest')
    require(type(batch) is dict and batch.get('schema_version') == 1 and
            batch.get('analysis_status') == 'manually_selected_offline_clip_batch_only' and
            batch.get('source_video_sha256') == video_sha and
            batch.get('source_manifest_sha256') == manifest_sha and
            batch.get('automatic_clip_selection_authorized') is False and
            batch.get('video_evidence_verified') is False and
            type(batch.get('clips')) is list and
            batch.get('clip_count') == len(batch['clips']) == len(manifest['clips']) and
            1 <= len(batch['clips']) <= 12,
            'Untrusted batch export report')
    index = {}
    for hand in hands['hands']:
        require(type(hand) is dict and type(hand.get('hand_id')) is str and
                type(hand.get('table_id')) is int and 1 <= hand['table_id'] <= 4 and
                hand.get('declared_game_type') in ('PLO5', 'PLO6') and
                hand.get('boundaries_human_declared_and_visually_checked') is True and
                hand.get('complete_hand_reconstructed') is False and
                hand.get('ready_for_equity_or_ev') is False and
                type(hand.get('observations')) is list,
                'Untrusted hand candidate')
        key = (hand['table_id'], hand['hand_id'])
        require(key not in index, 'Duplicate hand identity')
        start, end = number(hand.get('start_pts_seconds')), number(hand.get('end_pts_seconds'))
        require(0 <= start < end, 'Invalid hand window')
        index[key] = hand
    equities = {}
    for p in equity_paths:
        eq = read(p)
        require(type(eq) is dict and eq.get('schema_version') == 1 and
                eq.get('analysis_status') == 'reviewed_visible_snapshot_conditional_equity_only' and
                eq.get('source_hand_candidates_sha256') == hands_sha and
                eq.get('recording_sha256') == video_sha and
                eq.get('video_evidence_verified') is False and
                eq.get('complete_hand_reconstructed') is False and
                eq.get('ready_for_ev') is False and
                eq.get('automatic_clip_selection_authorized') is False,
                'Equity attachment not bound to candidate report')
        key = (eq.get('table_id'), eq.get('hand_id'))
        require(key in index and key not in equities, 'Unknown or duplicate equity attachment')
        hand = index[key]
        require(eq.get('game_type') == hand['declared_game_type'], 'Equity game mismatch')
        observations = {o['reviewed_candidate_index']: o for o in hand['observations']}
        for evidence_key, field, value_key in (('hero_evidence', 'hero_cards', 'hero_hole'),
                                               ('board_evidence', 'board', 'known_board')):
            evidence = eq.get(evidence_key)
            require(type(evidence) is dict and
                    type(evidence.get('source_observation_index')) is int and
                    evidence['source_observation_index'] in observations,
                    'Missing equity observation')
            obs = observations[evidence['source_observation_index']]
            require(obs['field'] == field and obs['value'].split() == eq.get(value_key) and
                    obs['pts_seconds'] == evidence.get('pts_seconds') and
                    obs['source_crop_sha256'] == evidence.get('source_crop_sha256'),
                    'Equity cards/evidence mismatch')
        estimate, bounds = eq.get('equity_estimate'), eq.get('equity_95pct_hoeffding_interval')
        require(type(estimate) in (int, float) and math.isfinite(estimate) and
                0 <= estimate <= 1 and type(bounds) is list and len(bounds) == 2 and
                all(type(v) in (int, float) and math.isfinite(v) for v in bounds) and
                0 <= bounds[0] <= estimate <= bounds[1] <= 1 and
                type(eq.get('samples')) is int and 100 <= eq['samples'] <= 10000 and
                type(eq.get('seed')) is int and 0 <= eq['seed'] <= 2**32 - 1 and
                type(eq.get('range_assumption')) is str and
                1 <= len(eq['range_assumption'].strip()) <= 1000,
                'Invalid conditional equity metadata')
        equities[key] = (eq, p)
    linked, used, member_hashes = [], set(), {}
    for item, req in zip(batch['clips'], manifest['clips']):
        require(type(item) is dict and type(req) is dict, 'Invalid clip entry')
        key = (req.get('table_id'), req.get('hand_id'))
        require(key in index and key not in used and
                item.get('table_id') == key[0] and item.get('hand_id') == key[1] and
                req.get('reviewer_confirmed_offline') is True and
                req.get('source_video_sha256') == video_sha,
                'Clip hand identity or approval mismatch')
        used.add(key)
        hand = index[key]
        start, end = number(req.get('start_seconds')), number(req.get('end_seconds'))
        hs, he = number(hand['start_pts_seconds']), number(hand['end_pts_seconds'])
        require(0 <= start <= hs < he <= end and hs-start <= 15 and end-he <= 15,
                'Clip does not contain hand window with <=15s padding')
        require(item.get('start_seconds') == start and item.get('end_seconds') == end,
                'Batch timestamp mismatch')
        clip = safe_member(directory, item.get('clip_file'))
        request = safe_member(directory, item.get('request_file'))
        sidecar = safe_member(directory, item.get('sidecar_file'))
        require(item['sidecar_file'] == item['clip_file'] + '.json' and
                item['clip_file'].endswith('.mp4') and
                item['request_file'].endswith('_request.json') and
                read(request) == req and
                sha(request) == item.get('request_sha256') and
                sha(clip) == item.get('clip_sha256'),
                'Exported clip/request mismatch')
        member_hashes.update({str(p.resolve()): sha(p) for p in (clip, request, sidecar)})
        meta = read(sidecar)
        require(type(meta) is dict and
                meta.get('analysis_status') == 'manually_selected_offline_clip' and
                meta.get('hand_id') == key[1] and meta.get('table_id') == key[0] and
                meta.get('source_video_sha256') == video_sha and
                meta.get('source_request_sha256') == sha(request) and
                meta.get('clip_sha256') == sha(clip) and
                meta.get('start_seconds') == start and meta.get('end_seconds') == end and
                meta.get('crop') == req.get('crop') and
                meta.get('explanation') == req.get('explanation') and
                meta.get('video_evidence_verified') is False and
                meta.get('automatic_clip_selection_authorized') is False,
                'Clip sidecar mismatch')
        eq_info = None
        if key in equities:
            eq, p = equities[key]
            eq_info = {'report_sha256': initial[str(p.resolve())],
                       'equity_estimate': eq.get('equity_estimate'),
                       'equity_95pct_hoeffding_interval': eq.get('equity_95pct_hoeffding_interval'),
                       'samples': eq.get('samples'), 'seed': eq.get('seed'),
                       'range_assumption': eq.get('range_assumption'),
                       'report_authenticity_independently_verified': False}
        linked.append({'hand_id': key[1], 'table_id': key[0],
                       'game_type_human_declared': hand['declared_game_type'],
                       'candidate_window_seconds': [hs, he],
                       'clip_window_seconds': [start, end],
                       'clip_file': item['clip_file'], 'clip_sha256': sha(clip),
                       'equity_attachment': eq_info,
                       'ev_attachment': None, 'decision_quality_verified': False})
    require(set(equities).issubset(used), 'Equity attachment has no selected clip')
    require(all(sha(Path(k)) == digest for k, digest in
                {**initial, **member_hashes}.items()), 'Source changed during audit')
    result = {'schema_version': 1,
              'analysis_status': 'offline_clip_hand_provenance_links_only',
              'source_video_sha256': video_sha, 'source_hand_candidates_sha256': hands_sha,
              'source_batch_manifest_sha256': manifest_sha,
              'source_batch_report_sha256': initial[str((directory / 'batch_report.json').resolve())],
              'linked_clips': linked, 'clip_count': len(linked),
              'video_evidence_verified': False, 'equity_authenticity_verified': False,
              'ev_verified': False, 'automatic_clip_selection_authorized': False,
              'action_recommendation_authorized': False,
              'warning': 'Hash/ID/timestamp consistency only. Human windows, OCR, crops, ranges and EV are not independently verified.'}
    with tempfile.TemporaryDirectory(prefix='plo_links_', dir=output.parent) as tmp:
        staged = Path(tmp) / 'report.json'
        staged.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                          encoding='utf-8')
        os.link(staged, output)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('recording', 'hand_candidates', 'batch_manifest', 'batch_directory', 'new_report'):
        p.add_argument(name)
    p.add_argument('--equity', nargs='*', default=[])
    a = p.parse_args(argv)
    result = link(a.recording, a.hand_candidates, a.batch_manifest, a.batch_directory,
                  a.new_report, equity_paths=a.equity)
    print(json.dumps({'status': result['analysis_status'], 'clips': result['clip_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
