"""Fail-closed temporal crops for OFFLINE, manually reviewed PLO session clips.

Usage: python offline_temporal_batch_crops.py VIDEO.mp4 BATCH_DIR TEMPORAL_REVIEW.json OUT_DIR

Uses existing conditional-EV batch clips only as unverified annotation references.
Rejects a crop if its *entire* requested interval does not fit within a single
reviewed geometry segment with a safety margin around internal transitions.
No OCR promotion, poker client, live assistance, or strategy verdict.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

import offline_ev_table_crop as crop
import offline_temporal_decision_locator as locator

STATUS = 'offline_temporal_crops_conditional_ev_unverified'
CROP_STATUS = 'offline_temporal_crop_unverified'
GUARD_SECONDS = 0.25


def require(ok, why):
    crop.check(ok, why)


def safe_output(out):
    out = Path(out)
    require(out.is_dir() and not out.is_symlink(), 'unsafe output directory')
    return out


def safe_name(value):
    return type(value) is str and crop.ID.fullmatch(value) is not None


def num(value):
    return type(value) in (int, float) and math.isfinite(value)


def no_collision(path):
    require(not path.exists() and not path.is_symlink(), 'output collision')


def preflight(video, batch_dir, review_json, out):
    video, batch_dir, review_json, out = map(Path, (video, batch_dir, review_json, out))
    crop.safe_file(video)
    crop.safe_file(review_json, json_file=True)
    require(video.suffix.lower() in ('.mp4', '.webm', '.mov'), 'unsupported video format')
    require(batch_dir.is_dir() and not batch_dir.is_symlink(), 'unsafe batch directory')
    safe_output(out)
    require(len({p.resolve() for p in (video, batch_dir, review_json, out)}) == 4,
            'inputs and output must be distinct')
    no_collision(out / 'temporal_crop_batch_report.json')
    w, h, duration = crop.media_info(video)
    video_sha = crop.digest(video)
    review = crop.read_json(review_json)
    segments = locator.validate_review(review, video_sha, w, h, duration)
    batch_path = batch_dir / 'batch_report.json'
    batch = crop.read_json(batch_path)
    require(type(batch) is dict and batch.get('schema_version') == 1 and
            batch.get('status') == 'offline_conditional_ev_batch_unverified_not_strategy_verdict' and
            batch.get('automatic_ocr_math_authorization') is False and
            batch.get('source_video_sha256') == video_sha and
            type(batch.get('clips')) is list and
            type(batch.get('rendered_count')) is int and
            0 <= batch['rendered_count'] == len(batch['clips']) <= crop.MAX_CLIPS,
            'untrusted batch ledger')
    inputs = [(p, crop.digest(p)) for p in (video, review_json, batch_path)]
    plans, blocked, seen = [], [], set()
    for item in batch['clips']:
        require(type(item) is dict, 'invalid clip entry')
        cid, table, hand = item.get('clip_id'), item.get('table_id'), item.get('hand_id')
        require(safe_name(cid) and safe_name(table) and safe_name(hand) and
                table in {r['table_id'] for r in segments[0]['regions']} and cid not in seen,
                'unsafe/duplicate clip or missing table')
        seen.add(cid)
        mp4_name, report_name = cid + '.mp4', cid + '.json'
        require(item.get('clip_filename') == mp4_name and
                item.get('clip_report_filename') == report_name, 'unsafe clip filenames')
        full_mp4, report_path = batch_dir / mp4_name, batch_dir / report_name
        full_sha = crop.digest(full_mp4)
        report = crop.read_json(report_path)
        require(item.get('clip_sha256') == full_sha and
                report.get('rendered_clip_sha256') == full_sha and
                report.get('clip_filename') == mp4_name and
                report.get('status') == 'offline_conditional_ev_clip_not_strategy_verdict' and
                report.get('automatic_ocr_math_authorization') is False and
                report.get('source_video_sha256') == video_sha and
                report.get('table_id') == table and report.get('hand_id') == hand and
                report.get('variant') in ('PLO5', 'PLO6', '5', '6') and
                report.get('street') in ('preflop', 'flop', 'turn', 'river'),
                'invalid clip report/provenance')
        start, length, pts = (report.get('clip_start_seconds'),
                              report.get('clip_duration_seconds'),
                              report.get('decision_pts_seconds_claim'))
        require(num(start) and num(length) and num(pts) and 0 <= start and
                length >= .5 and start + length <= duration + .05 and
                start <= pts < min(duration, start + length) and
                num(item.get('clip_start_seconds')) and
                num(item.get('clip_duration_seconds')) and
                num(item.get('decision_pts_seconds_claim')) and
                abs(start - item['clip_start_seconds']) < 1e-5 and
                abs(length - item['clip_duration_seconds']) < 1e-5 and
                abs(pts - item['decision_pts_seconds_claim']) < 1e-5,
                'invalid clip interval or decision timestamp')
        inputs.extend(((full_mp4, full_sha), (report_path, crop.digest(report_path))))
        for filename in (f'temporal_{cid}.mp4', f'temporal_{cid}.json'):
            no_collision(out / filename)
        location = locator.locate(review, video_sha256=video_sha, width=w, height=h,
                                  duration=duration, table_id=table, timestamp=pts,
                                  boundary_guard_seconds=GUARD_SECONDS)
        if location['status'] == 'blocked_transition_uncertainty':
            blocked.append({'clip_id': cid, 'table_id': table, 'hand_id': hand,
                            'reason': 'decision_near_uncertain_transition'})
            continue
        index = location['segment_index']
        seg = segments[index - 1]
        # Crop is static for the whole MP4: decision-only checks are insufficient.
        safe_start = seg['start_seconds'] + (GUARD_SECONDS if index > 1 else 0)
        safe_end = seg['end_seconds'] - (GUARD_SECONDS if index < len(segments) else 0)
        if start < safe_start - 1e-6 or start + length > safe_end + 1e-6:
            blocked.append({'clip_id': cid, 'table_id': table, 'hand_id': hand,
                            'reason': 'clip_overlaps_or_approaches_geometry_transition'})
            continue
        plans.append((cid, table, hand, report, location['region_claim'], index))
    require(all(crop.digest(p) == sha for p, sha in inputs), 'input modified during preflight')
    return video, review_json, batch_path, out, plans, blocked, inputs


def export(video, batch_dir, review_json, out):
    video, review_json, batch_path, out, plans, blocked, inputs = preflight(
        video, batch_dir, review_json, out)
    created = []
    try:
        clips = []
        for cid, table, hand, report, region, index in plans:
            with tempfile.TemporaryDirectory(prefix='plo_temporal_crop_', dir=out) as folder:
                temp = Path(folder)
                overlay = (f"PLO {report['variant']} | {report['street']} | Mesa {table}\n"
                           f"Acao declarada: {report.get('action_taken_claim_unverified', 'incerta')}\n"
                           "Geometria humana e EV condicionais; nao verificados.")
                (temp / 'overlay.txt').write_text(overlay, encoding='utf-8')
                result = temp / 'crop.mp4'
                filt = (f"crop={region['width']}:{region['height']}:{region['x']}:{region['y']},"
                        "drawtext=textfile=overlay.txt:expansion=none:fontcolor=white:"
                        "fontsize=12:box=1:boxcolor=black@0.75:x=4:y=4")
                subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                                '-ss', f"{report['clip_start_seconds']:.6f}", '-i', str(video),
                                '-t', f"{report['clip_duration_seconds']:.6f}", '-map', '0:v:0',
                                '-vf', filt, '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                                '-crf', '28', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                                str(result)], cwd=temp, capture_output=True, text=True,
                               check=True, timeout=180)
                rw, rh, rd = crop.media_info(result)
                require((rw, rh) == (region['width'], region['height']) and
                        rd >= min(.4, report['clip_duration_seconds'] * .5),
                        'invalid rendered crop')
                require(all(crop.digest(p) == sha for p, sha in inputs),
                        'source changed during rendering')
                filename = f'temporal_{cid}.mp4'
                meta = {'schema_version': 1, 'status': CROP_STATUS,
                        'clip_id': cid, 'table_id_claim': table, 'hand_id': hand,
                        'source_video_sha256': inputs[0][1],
                        'source_temporal_review_sha256': inputs[1][1],
                        'source_batch_report_sha256': inputs[2][1],
                        'source_clip_report_sha256': crop.digest(Path(batch_dir) / (cid + '.json')),
                        'temporal_segment_index': index, 'region_claim': region,
                        'clip_start_seconds': report['clip_start_seconds'],
                        'clip_duration_seconds_claim': report['clip_duration_seconds'],
                        'decision_pts_seconds_claim': report['decision_pts_seconds_claim'],
                        'crop_filename': filename, 'crop_sha256': crop.digest(result),
                        'rendered_duration_seconds': rd,
                        'table_identity_verified': False,
                        'automatic_ocr_math_authorization': False,
                        'warning': 'Human geometry claim and conditional EV, not verified poker strategy.'}
                meta_path = temp / 'meta.json'
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
                for src, name in ((result, filename), (meta_path, f'temporal_{cid}.json')):
                    dest = out / name
                    no_collision(dest)
                    os.link(src, dest)
                    created.append(dest)
                clips.append({'clip_id': cid, 'table_id': table, 'hand_id': hand,
                              'filename': filename, 'metadata': f'temporal_{cid}.json',
                              'sha256': meta['crop_sha256'], 'segment_index': index})
        require(all(crop.digest(p) == sha for p, sha in inputs),
                'source changed before ledger publication')
        ledger = {'schema_version': 1, 'status': STATUS,
                  'source_video_sha256': inputs[0][1],
                  'source_temporal_review_sha256': inputs[1][1],
                  'source_batch_report_sha256': inputs[2][1],
                  'rendered_count': len(clips), 'blocked_count': len(blocked),
                  'clips': clips, 'blocked': blocked,
                  'boundary_guard_seconds': GUARD_SECONDS,
                  'table_identity_verified': False,
                  'automatic_ocr_math_authorization': False,
                  'warning': 'Offline synthetic-capable crop only; review geometry, action and EV assumptions.'}
        with tempfile.TemporaryDirectory(prefix='plo_temporal_ledger_', dir=out) as folder:
            tmp = Path(folder) / 'temporal_crop_batch_report.json'
            tmp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
            dest = out / tmp.name
            no_collision(dest)
            os.link(tmp, dest)
            created.append(dest)
        return ledger
    except BaseException:
        for f in reversed(created):
            f.unlink(missing_ok=True)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'batch_dir', 'temporal_review_json', 'output_dir'):
        p.add_argument(name)
    a = p.parse_args(argv)
    result = export(a.video, a.batch_dir, a.temporal_review_json, a.output_dir)
    print(json.dumps({'status': result['status'], 'rendered': result['rendered_count'],
                      'blocked': result['blocked_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
