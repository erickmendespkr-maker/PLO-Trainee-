"""Bind a single offline MP4 clip request to reviewed PLO5/PLO6 hand bounds.

Usage: python offline_clip_review_gate.py VIDEO DRAFTS_JSON BOUNDARY_REVIEW_JSON HAND_ID CROP_JSON NEW_OUTPUT_DIR

Produces request.json for the existing offline_reviewed_clip_export.py and
provenance.json. Reviewer labels are assertions, not proof of poker correctness.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

IDENT = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
EXPLANATION = ('Trecho selecionado de gravação offline por limites revisados '
               'manualmente. Mão, ações, equity e EV não verificados.')


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique(pairs):
    d = {}
    for k, v in pairs:
        need(k not in d, 'duplicate JSON key')
        d[k] = v
    return d


def load(path):
    p = Path(path)
    need(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 8 * 1024 * 1024,
         'unsafe JSON input')
    return json.loads(p.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def seconds(x):
    return type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 5400


def probe(path):
    try:
        p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                            'format=duration:stream=codec_type,width,height', '-of', 'json',
                            str(Path(path).resolve())], capture_output=True, timeout=30, check=True)
        data = json.loads(p.stdout)
        stream = next(x for x in data['streams'] if x['codec_type'] == 'video')
        w, h, duration = stream['width'], stream['height'], float(data['format']['duration'])
    except (OSError, subprocess.SubprocessError, KeyError, StopIteration, ValueError,
            TypeError) as exc:
        raise ValueError('invalid video metadata') from exc
    need(type(w) is int and type(h) is int and 2 <= w <= 7680 and 2 <= h <= 4320
         and math.isfinite(duration) and 0 < duration <= 3600.1, 'invalid video size or duration')
    return w, h, duration


def prepare(video, drafts_path, review_path, hand_id, crop_path, output_dir):
    video, drafts_path, review_path, crop_path, output_dir = map(
        Path, (video, drafts_path, review_path, crop_path, output_dir))
    need(video.is_file() and not video.is_symlink() and video.suffix.lower() in ('.mp4', '.webm')
         and 0 < video.stat().st_size <= 8 * 1024 ** 3, 'unsafe recording')
    need(type(hand_id) is str and IDENT.fullmatch(hand_id), 'invalid hand ID')
    need(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
         and not output_dir.exists() and not output_dir.is_symlink()
         and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name),
         'output must be a new safe directory')
    drafts, review, crop = load(drafts_path), load(review_path), load(crop_path)
    need(type(drafts) is dict and drafts.get('schema_version') == 1
         and drafts.get('analysis_status') == 'offline_reviewed_hand_drafts_only'
         and drafts.get('hands_reconstructed') is False
         and drafts.get('ready_for_equity_or_ev') is False
         and type(drafts.get('hands')) is list and 1 <= len(drafts['hands']) <= 200,
         'invalid draft provenance')
    need(type(review) is dict and review.get('schema_version') == 1
         and review.get('analysis_status') == 'offline_boundary_review_import_only'
         and review.get('source_hand_drafts_sha256') == sha(drafts_path)
         and review.get('source_reviewed_report_sha256') == drafts.get('source_reviewed_report_sha256')
         and review.get('ready_for_equity_or_ev') is False
         and review.get('reviewed_boundaries_are_poker_verified') is False
         and type(review.get('annotations')) is list
         and len(review['annotations']) == len(drafts['hands']), 'invalid review provenance')
    hands = {h.get('hand_id'): h for h in drafts['hands'] if type(h) is dict}
    need(len(hands) == len(drafts['hands']) and hand_id in hands, 'missing or duplicate hand')
    h = hands[hand_id]
    need(type(h.get('table_id')) is int and 1 <= h['table_id'] <= 4
         and h.get('variant') in ('PLO5', 'PLO6')
         and h.get('boundary_origin') == 'manual_unverified'
         and h.get('status') == 'draft_requires_human_reconstruction'
         and h.get('ready_for_equity_or_ev') is False
         and seconds(h.get('start_seconds')) and seconds(h.get('end_seconds'))
         and h['start_seconds'] < h['end_seconds'], 'invalid hand evidence')
    items = [x for x in review['annotations'] if type(x) is dict and x.get('hand_id') == hand_id]
    need(len(items) == 1, 'missing or duplicate hand review')
    r = items[0]
    need(r.get('review_status') in ('confirmed', 'corrected')
         and type(r.get('table_id')) is int and r['table_id'] == h['table_id']
         and r.get('source_start_seconds') == h['start_seconds']
         and r.get('source_end_seconds') == h['end_seconds']
         and seconds(r.get('revised_start_seconds')) and seconds(r.get('revised_end_seconds'))
         and type(r.get('changed')) is bool and type(r.get('review_note')) is str,
         'hand boundaries not reviewed')
    start, end = r['revised_start_seconds'], r['revised_end_seconds']
    changed = start != h['start_seconds'] or end != h['end_seconds']
    need(0.1 <= end - start <= 180 and r['changed'] == changed
         and ((r['review_status'] == 'corrected' and changed and r['review_note'].strip())
              or (r['review_status'] == 'confirmed' and not changed)),
         'invalid boundary revision')
    w, height, duration = probe(video)
    need(end <= duration, 'hand interval outside recording')
    need(type(crop) is dict and set(crop) == {'x', 'y', 'width', 'height'}
         and all(type(v) is int and v >= 0 and v % 2 == 0 for v in crop.values())
         and crop['width'] >= 2 and crop['height'] >= 2
         and crop['x'] + crop['width'] <= w
         and crop['y'] + crop['height'] <= height, 'invalid manual crop')
    request = {'schema_version': 1, 'hand_id': hand_id, 'table_id': h['table_id'],
               'start_seconds': start, 'end_seconds': end, 'crop': crop,
               'explanation': EXPLANATION, 'source_video_sha256': sha(video),
               'reviewer_confirmed_offline': True}
    provenance = {'schema_version': 1, 'analysis_status': 'offline_clip_review_gate_only',
                  'source_hand_drafts_sha256': sha(drafts_path),
                  'source_boundary_review_sha256': sha(review_path),
                  'source_crop_sha256': sha(crop_path),
                  'source_video_sha256': request['source_video_sha256'],
                  'hand_id': hand_id, 'table_id': h['table_id'],
                  'boundary_review_status': r['review_status'],
                  'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
                  'source_video_matches_ocr_source_verified': False,
                  'warning': 'Human review labels and manual crops are not proof of poker accuracy.'}
    with tempfile.TemporaryDirectory(prefix='.plo_clip_gate_', dir=output_dir.parent) as temp:
        stage = Path(temp)
        (stage / 'request.json').write_text(json.dumps(request, indent=2, ensure_ascii=False) + '\n', 'utf-8')
        (stage / 'provenance.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + '\n', 'utf-8')
        need(sha(video) == request['source_video_sha256']
             and sha(drafts_path) == provenance['source_hand_drafts_sha256']
             and sha(review_path) == provenance['source_boundary_review_sha256']
             and sha(crop_path) == provenance['source_crop_sha256'], 'source changed during gate')
        need(not output_dir.exists(), 'output appeared during gate')
        os.rename(stage, output_dir)
    return request, provenance


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'drafts', 'boundary_review', 'hand_id', 'crop_json', 'new_output_dir'):
        p.add_argument(name)
    a = p.parse_args(argv)
    req, _ = prepare(a.video, a.drafts, a.boundary_review, a.hand_id, a.crop_json, a.new_output_dir)
    print(json.dumps({'hand_id': req['hand_id'], 'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
