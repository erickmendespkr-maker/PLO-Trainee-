"""Review-only triage of sparse, real-video table/OCR proposals.

Usage: python offline_real_probe_review_handoff.py VIDEO CONFIG.json PROBE.json NEW_QUEUE.json

Consumes output from offline_real_video_probe.py; never treats pot OCR
changes as hand boundaries or strategic decisions. Draft clip requests are
unapproved and intentionally rejected by offline_reviewed_clip_export.
No video frames or private metadata are uploaded by this module.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile

from offline_real_video_probe import config_read, sha256, require

MAX_INPUT = 256 * 1024
MAX_EVENTS = 44


def strict_json(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_INPUT, 'invalid source JSON')
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            require(k not in obj, 'duplicate JSON key')
            obj[k] = v
        return obj
    return json.loads(path.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def finite(value, lower, upper):
    return type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper


def validate_report(report, cfg, source_sha, cfg_sha):
    require(type(report) is dict and report.get('schema_version') == 1 and
            type(report['schema_version']) is int and
            report.get('status') == 'real_video_ocr_and_layout_proposals_only' and
            report.get('source_video_sha256') == source_sha and
            report.get('source_layout_sha256') == cfg_sha and
            report.get('hands_reconstructed') is False and
            report.get('equity_ev_authorized') is False and
            report.get('automatic_clip_selection_authorized') is False,
            'probe source/status mismatch')
    recording = report.get('recording')
    require(type(recording) is dict and
            set(recording) == {'width', 'height', 'duration_seconds'} and
            type(recording['width']) is int and type(recording['height']) is int and
            recording['width'] >= 300 and recording['height'] >= 400 and
            finite(recording['duration_seconds'], .1, 3900),
            'invalid probe geometry/duration')
    slots = config_read(cfg, (recording['width'], recording['height']))['slots']
    slot_ids = {s['table_id'] for s in slots}
    samples = report.get('samples')
    require(type(samples) is list and 2 <= len(samples) <= 12, 'require 2..12 real probes')
    last_t = last_pts = -math.inf
    for sample in samples:
        require(type(sample) is dict and set(sample) == {
            'requested_playback_seconds', 'decoded_source_pts_seconds', 'table_proposals'},
            'invalid probe sample fields')
        t, pts = sample['requested_playback_seconds'], sample['decoded_source_pts_seconds']
        require(finite(t, 0, recording['duration_seconds']) and
                finite(pts, -86400, 86400) and t > last_t and pts > last_pts and
                (last_t == -math.inf or abs((pts-last_pts)-(t-last_t)) <= .5),
                'unordered or inconsistent sample timestamps')
        last_t, last_pts = t, pts
        rows = sample['table_proposals']
        require(type(rows) is list and len(rows) == len(slots), 'missing table probes')
        ids = set()
        for item in rows:
            require(type(item) is dict and set(item) == {
                'table_id', 'proposal', 'matched_felt_probes',
                'rgb_distances', 'human_verified', 'pot_ocr'},
                'invalid table proposal fields')
            tid = item['table_id']
            require(type(tid) is int and tid in slot_ids and tid not in ids and
                    item['proposal'] in ('likely_visible', 'absent_or_uncertain') and
                    type(item['proposal']) is str and item['human_verified'] is False and
                    type(item['matched_felt_probes']) is int and
                    0 <= item['matched_felt_probes'] <= 4 and
                    type(item['rgb_distances']) is list and len(item['rgb_distances']) == 4 and
                    all(finite(d, 0, 500) for d in item['rgb_distances']),
                    'malformed or duplicate table proposal')
            ids.add(tid)
            ocr = item['pot_ocr']
            require(ocr is None or (item['proposal'] == 'likely_visible' and
                    type(ocr) is dict and set(ocr) == {
                        'raw_text', 'minimum_word_confidence', 'candidate_bb', 'status'} and
                    ocr['status'] == 'needs_human_review' and
                    type(ocr['raw_text']) is str and len(ocr['raw_text']) <= 120 and
                    finite(ocr['minimum_word_confidence'], 0, 1) and
                    (ocr['candidate_bb'] is None or finite(ocr['candidate_bb'], 0, 10000))),
                    'invalid provisional OCR payload')
    return samples, slots


def assemble(video, config, probe):
    video, config, probe = map(Path, (video, config, probe))
    require(video.is_file() and not video.is_symlink() and
            video.suffix.lower() in ('.mp4', '.webm') and
            0 < video.stat().st_size <= 8 * 1024**3, 'invalid recording')
    video_sha, config_sha, report_sha = (sha256(p) for p in (video, config, probe))
    report = strict_json(probe)
    samples, slots = validate_report(report, config, video_sha, config_sha)
    duration = report['recording']['duration_seconds']
    events, requests = [], []
    for i in range(1, len(samples)):
        left, right = samples[i-1], samples[i]
        previous = {x['table_id']: x for x in left['table_proposals']}
        current = {x['table_id']: x for x in right['table_proposals']}
        a, b = left['requested_playback_seconds'], right['requested_playback_seconds']
        for slot in slots:
            tid = slot['table_id']
            before, after = previous[tid], current[tid]
            kinds = []
            if before['proposal'] != after['proposal']:
                kinds.append('table_visibility_change_unverified')
            old, new = before['pot_ocr'], after['pot_ocr']
            if (old is not None and new is not None and
                    old['candidate_bb'] is not None and new['candidate_bb'] is not None and
                    old['minimum_word_confidence'] >= .5 and
                    new['minimum_word_confidence'] >= .5 and
                    old['candidate_bb'] != new['candidate_bb']):
                kinds.append('pot_ocr_change_unverified')
            if not kinds:
                continue
            event = {'event_index': len(events), 'table_id': tid,
                     'between_samples_seconds': [a, b],
                     'event_kinds': kinds, 'sample_gap_seconds': b-a,
                     'pot_ocr_before_candidate_bb': old['candidate_bb'] if old else None,
                     'pot_ocr_after_candidate_bb': new['candidate_bb'] if new else None,
                     'hand_boundary_verified': False,
                     'action_or_cards_verified': False, 'ready_for_math': False,
                     'status': 'needs_human_review'}
            events.append(event)
            # A nearby sample is only an excerpt for locating evidence, NOT hand bounds.
            if b-a <= 90 and all(slot[k] % 2 == 0 for k in ('x','y','width','height')):
                start, end = max(0., b-4.), min(duration, b+4.)
                if .1 <= end-start <= 180:
                    requests.append({'schema_version': 1,
                        'hand_id': f'review_candidate_t{tid}_sample{i}',
                        'table_id': tid, 'start_seconds': start, 'end_seconds': end,
                        'crop': {'x': slot['x'], 'y': slot['y'],
                                 'width': slot['width'], 'height': slot['height']},
                        'explanation': ('Revisao pendente: mudanca de visibilidade/pote OCR '
                                        'nao confirma mao, acao ou erro; equity/EV indisponiveis.'),
                        'source_video_sha256': video_sha,
                        'reviewer_confirmed_offline': False})
    require(len(events) <= MAX_EVENTS, 'too many triage events')
    require(all(sha256(p) == h for p, h in ((video, video_sha),
                 (config, config_sha), (probe, report_sha))), 'input changed during triage')
    return {'schema_version': 1, 'analysis_status': 'unverified_real_video_review_candidates',
            'source_video_sha256': video_sha,
            'source_layout_sha256': config_sha,
            'source_probe_sha256': report_sha,
            'sample_count': len(samples), 'table_slot_count': len(slots),
            'events': events, 'unapproved_clip_request_drafts': requests,
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'warning': ('Events lie BETWEEN sparse timestamps, not at exact hand/action times. '
                        'Drafts are intentionally unapproved, and must not be exported '
                        'as reviewed technical analyses without independent human review.')}


def run(video, config, probe, output):
    output = Path(output)
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            output.suffix == '.json' and
            output.resolve() not in {Path(x).resolve() for x in (video, config, probe)},
            'output must be a distinct new JSON')
    result = assemble(video, config, probe)
    with tempfile.TemporaryDirectory(prefix='.plo_triage_', dir=output.parent) as tmp:
        staged = Path(tmp) / 'queue.json'
        staged.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                     allow_nan=False)+'\n', encoding='utf-8')
        os.link(staged, output)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'layout_json', 'probes_json', 'new_review_queue_json'):
        p.add_argument(name)
    a = p.parse_args(argv)
    result = run(a.video, a.layout_json, a.probes_json, a.new_review_queue_json)
    print(json.dumps({'events': len(result['events']),
                      'unapproved_clip_drafts': len(result['unapproved_clip_request_drafts']),
                      'hands_reconstructed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
