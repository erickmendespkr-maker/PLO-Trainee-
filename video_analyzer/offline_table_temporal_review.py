"""Human-audited temporal table layouts for OFFLINE recorded PLO sessions.

Generate editable draft (NEVER approved automatically):
  python offline_table_temporal_review.py template VIDEO TEMPORAL_JSON DRAFT.json
Human edits segments, boundaries, geometry and reviewer_note, then explicitly runs:
  python offline_table_temporal_review.py approve VIDEO TEMPORAL_JSON DRAFT.json OUT_DIR --confirm-reviewed
Optional bounded visual evidence (1 second per segment/table, not session export):
  python offline_table_temporal_review.py previews VIDEO OUT_DIR/temporal_review.json PREVIEW_DIR

All table identities remain human *claims*, not verified detections. This module
never authorizes OCR, equity, EV, live poker, or automated strategic decisions.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

import offline_table_region_proposals as base
import offline_table_temporal_regions as temporal

APPROVED = 'manual_offline_temporal_layout_claim_unverified'
DRAFT = 'offline_temporal_layout_review_draft_unapproved'
PREVIEW = 'offline_temporal_layout_previews_unverified'
ID = re.compile(r'T[1-4]\Z')
MAX_SEGMENTS = 12
MAX_OUTPUTS = 48
PLACEHOLDER = 'REVIEW VIDEO; ENTER HUMAN REASON AND CHECK EVERY REGION'


def canonical(value):
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'


def safe_dest(path):
    path = Path(path)
    base.require(path.is_dir() and not path.is_symlink(), 'unsafe output directory')
    return path


def no_collision(path):
    base.require(not path.exists() and not path.is_symlink(), 'output collision')


def link_atomic(src, dst):
    no_collision(dst)
    os.link(src, dst)


def validate_temporal(video, temporal_json, *, recompute=False):
    video, temporal_json = Path(video), Path(temporal_json)
    base.safe_file(video)
    p = base.read_json(temporal_json)
    w, h, duration = base.probe(video)
    base.require(type(p) is dict and p.get('schema_version') == 1 and
                 p.get('status') == temporal.STATUS and p.get('method') == temporal.METHOD and
                 p.get('source_video_sha256') == base.sha256(video) and
                 p.get('source_width') == w and p.get('source_height') == h and
                 p.get('source_duration_seconds') == duration and
                 p.get('human_confirmation') is False and
                 p.get('crop_authorized') is False and
                 p.get('automatic_ocr_math_authorization') is False,
                 'invalid temporal evidence/source')
    interval = p.get('sample_interval_seconds')
    times = temporal.sample_times(duration, interval, 720)
    observations = p.get('observations')
    base.require(type(observations) is list and len(observations) == len(times) and
                 all(type(o) is dict and o.get('timestamp_seconds') == t
                     for o, t in zip(observations, times)) and
                 type(p.get('transitions')) is list,
                 'invalid temporal samples')
    if recompute:
        frames = [base.sample(video, t) for t in times]
        expected_observations, expected_transitions = temporal.analyze_frames(frames, times, w, h)
        base.require(observations == expected_observations and
                     p['transitions'] == expected_transitions,
                     'temporal evidence altered or stale')
    return p, (w, h, duration)


def template(video, temporal_json, draft_path):
    draft_path = Path(draft_path)
    no_collision(draft_path)
    p, (_, _, duration) = validate_temporal(video, temporal_json)
    first = next((o for o in p['observations'] if o['status'] == 'candidate_only'), None)
    base.require(first is not None, 'no supported geometry to draft; inspect video manually')
    result = {'schema_version': 1, 'status': DRAFT,
              'source_video_sha256': p['source_video_sha256'],
              'temporal_evidence_sha256': base.sha256(temporal_json),
              'reviewer_note': PLACEHOLDER,
              'segments': [{'start_seconds': 0.0, 'end_seconds': duration,
                            'regions': first['regions']}]}
    base.require(draft_path.parent.is_dir() and not draft_path.parent.is_symlink(),
                 'unsafe draft directory')
    with tempfile.TemporaryDirectory(prefix='plo_temporal_draft_', dir=draft_path.parent) as folder:
        tmp = Path(folder) / 'draft.json'
        tmp.write_text(canonical(result), encoding='utf-8')
        link_atomic(tmp, draft_path)
    return result


def validate_segments(segments, width, height, duration):
    base.require(type(segments) is list and 1 <= len(segments) <= MAX_SEGMENTS,
                 'invalid segment count')
    previous = 0.0
    reference_ids = None
    for i, seg in enumerate(segments):
        base.require(type(seg) is dict and set(seg) ==
                     {'start_seconds', 'end_seconds', 'regions'}, 'invalid segment keys')
        start, end = seg['start_seconds'], seg['end_seconds']
        base.require(type(start) in (int, float) and type(end) in (int, float) and
                     math.isfinite(start) and math.isfinite(end) and
                     abs(start - previous) <= 0.001 and end > start and
                     end - start >= 0.5 and end <= duration + 0.001,
                     'noncontiguous/out-of-range segments')
        if i == 0:
            base.require(abs(start) <= 0.001, 'first segment must begin at zero')
        previous = end
        regions = seg['regions']
        base.require(type(regions) is list and 1 <= len(regions) <= 4,
                     'invalid table count')
        ids = []
        for r in regions:
            base.require(type(r) is dict and set(r) ==
                         {'table_id', 'x', 'y', 'width', 'height'}, 'invalid region keys')
            table = r['table_id']
            base.require(type(table) is str and ID.fullmatch(table) and table not in ids,
                         'invalid/duplicate table ID')
            ids.append(table)
            x, y, rw, rh = (r[k] for k in ('x', 'y', 'width', 'height'))
            base.require(all(type(v) is int for v in (x, y, rw, rh)) and
                         x >= 0 and y >= 0 and rw >= 32 and rh >= 32 and
                         x % 2 == 0 and y % 2 == 0 and rw % 2 == 0 and rh % 2 == 0 and
                         x + rw <= width and y + rh <= height,
                         'invalid crop geometry')
        base.require(reference_ids is None or ids == reference_ids,
                     'table identity/order changed; manual mapping unsupported')
        reference_ids = ids
        for j, a in enumerate(regions):
            for b in regions[j + 1:]:
                base.require(min(a['x'] + a['width'], b['x'] + b['width']) <=
                             max(a['x'], b['x']) or
                             min(a['y'] + a['height'], b['y'] + b['height']) <=
                             max(a['y'], b['y']), 'overlapping regions')
    base.require(abs(previous - duration) <= 0.001, 'segments must cover video')
    base.require(len(segments) * len(reference_ids) <= MAX_OUTPUTS,
                 'too many preview clips')


def approve(video, temporal_json, draft_path, output_dir, *, confirmed=False):
    base.require(confirmed is True, 'explicit human review required')
    output_dir = safe_dest(output_dir)
    dest = output_dir / 'temporal_review.json'
    no_collision(dest)
    p, (w, h, duration) = validate_temporal(video, temporal_json, recompute=True)
    d = base.read_json(draft_path)
    base.require(type(d) is dict and set(d) == {'schema_version', 'status',
                 'source_video_sha256', 'temporal_evidence_sha256', 'reviewer_note', 'segments'}
                 and type(d['schema_version']) is int and d['schema_version'] == 1 and
                 d['status'] == DRAFT and
                 d['source_video_sha256'] == p['source_video_sha256'] and
                 d['temporal_evidence_sha256'] == base.sha256(temporal_json),
                 'draft provenance mismatch')
    note = d['reviewer_note']
    base.require(type(note) is str and 12 <= len(note.strip()) <= 1000 and
                 note != PLACEHOLDER, 'reviewer must replace placeholder note')
    validate_segments(d['segments'], w, h, duration)
    video_hash = base.sha256(video)
    evidence_hash = base.sha256(temporal_json)
    draft_hash = base.sha256(draft_path)
    result = {'schema_version': 1, 'status': APPROVED,
              'source_video_sha256': video_hash,
              'temporal_evidence_sha256': evidence_hash,
              'review_draft_sha256': draft_hash,
              'source_width': w, 'source_height': h,
              'source_duration_seconds': duration,
              'reviewer_note': note.strip(),
              'human_confirmation_claimed': True,
              'segments': d['segments'],
              'automatic_ocr_math_authorization': False,
              'table_identity_verified': False,
              'warning': 'Human-reviewed geometry CLAIM only; table identity and transition timestamps unverified. Never promote to OCR/equity/EV facts.'}
    with tempfile.TemporaryDirectory(prefix='plo_temporal_approved_', dir=output_dir) as folder:
        tmp = Path(folder) / 'temporal_review.json'
        tmp.write_text(canonical(result), encoding='utf-8')
        base.require(base.sha256(video) == video_hash and
                     base.sha256(temporal_json) == evidence_hash and
                     base.sha256(draft_path) == draft_hash,
                     'input changed before publication')
        link_atomic(tmp, dest)
    return result


def previews(video, review_json, output_dir):
    output_dir = safe_dest(output_dir)
    video, review_json = Path(video), Path(review_json)
    base.safe_file(video)
    review = base.read_json(review_json)
    w, h, duration = base.probe(video)
    base.require(type(review) is dict and review.get('status') == APPROVED and
                 review.get('schema_version') == 1 and
                 review.get('source_video_sha256') == base.sha256(video) and
                 review.get('source_width') == w and review.get('source_height') == h and
                 review.get('source_duration_seconds') == duration and
                 review.get('human_confirmation_claimed') is True and
                 review.get('table_identity_verified') is False and
                 review.get('automatic_ocr_math_authorization') is False,
                 'invalid review/source')
    validate_segments(review['segments'], w, h, duration)
    no_collision(output_dir / 'temporal_previews.json')
    no_collision(output_dir / 'temporal_previews.html')
    video_sha, review_sha = base.sha256(video), base.sha256(review_json)
    published = []
    try:
        with tempfile.TemporaryDirectory(prefix='plo_temporal_previews_', dir=output_dir) as folder:
            tmp = Path(folder)
            clips = []
            for i, seg in enumerate(review['segments'], 1):
                duration_seg = seg['end_seconds'] - seg['start_seconds']
                clip_len = min(1.0, duration_seg)
                clip_start = seg['start_seconds'] + (duration_seg - clip_len) / 2
                for r in seg['regions']:
                    name = f"segment_{i:02d}_{r['table_id']}.mp4"
                    dest = output_dir / name
                    no_collision(dest)
                    file = tmp / name
                    crop = f"crop={r['width']}:{r['height']}:{r['x']}:{r['y']}"
                    subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                                    '-y', '-ss', f'{clip_start:.6f}', '-i', str(video),
                                    '-t', f'{clip_len:.6f}', '-map', '0:v:0', '-vf', crop,
                                    '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                                    '-crf', '28', '-pix_fmt', 'yuv420p',
                                    '-movflags', '+faststart', str(file)],
                                   capture_output=True, check=True, timeout=120)
                    cw, ch, cd = base.probe(file)
                    base.require((cw, ch) == (r['width'], r['height']) and
                                 cd >= min(0.4, clip_len * 0.5),
                                 'invalid rendered preview')
                    clips.append({'segment_index': i, 'table_id_claim': r['table_id'],
                                  'filename': name, 'sha256': base.sha256(file),
                                  'sample_start_seconds': round(clip_start, 6),
                                  'sample_duration_seconds': round(clip_len, 6),
                                  'crop_region_claim': r})
            base.require(base.sha256(video) == video_sha and
                         base.sha256(review_json) == review_sha,
                         'input changed during export')
            ledger = {'schema_version': 1, 'status': PREVIEW,
                      'source_video_sha256': video_sha,
                      'temporal_review_sha256': review_sha,
                      'rendered_count': len(clips), 'clips': clips,
                      'automatic_ocr_math_authorization': False,
                      'warning': 'Bounded visual previews only, no verified table identity or strategic analysis.'}
            (tmp / 'temporal_previews.json').write_text(canonical(ledger), encoding='utf-8')
            cards = '\n'.join(f'<article><h2>Segmento {c["segment_index"]} — Mesa {html.escape(c["table_id_claim"])}</h2>'
                              f'<video controls preload="metadata" src="{html.escape(c["filename"], quote=True)}"></video>'
                              f'<p>Tempo: {c["sample_start_seconds"]:.3f}s; geometria revisada, identidade não comprovada.</p></article>'
                              for c in clips)
            page = ('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Revisão temporal offline</title>'
                    '<style>body{font:16px sans-serif;max-width:900px;margin:2rem auto}article{padding:1rem;border:1px solid #888;margin:1rem 0}video{max-width:100%}</style>'
                    '<h1>Prévia temporal — dados não verificados</h1><p>Não autoriza OCR, equity ou EV.</p>' + cards + '</html>')
            (tmp / 'temporal_previews.html').write_text(page, encoding='utf-8')
            for src in sorted(tmp.iterdir()):
                dest = output_dir / src.name
                link_atomic(src, dest)
                published.append(dest)
        return ledger
    except BaseException:
        for f in reversed(published):
            f.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('template')
    for n in ('video', 'temporal_json', 'draft'):
        a.add_argument(n)
    b = sub.add_parser('approve')
    for n in ('video', 'temporal_json', 'draft', 'output_dir'):
        b.add_argument(n)
    b.add_argument('--confirm-reviewed', action='store_true')
    c = sub.add_parser('previews')
    for n in ('video', 'review_json', 'output_dir'):
        c.add_argument(n)
    args = parser.parse_args(argv)
    if args.command == 'template':
        result = template(args.video, args.temporal_json, args.draft)
    elif args.command == 'approve':
        result = approve(args.video, args.temporal_json, args.draft, args.output_dir,
                         confirmed=args.confirm_reviewed)
    else:
        result = previews(args.video, args.review_json, args.output_dir)
    print(json.dumps({'status': result['status'],
                      'segments': len(result.get('segments', [])),
                      'previews': result.get('rendered_count', 0)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
