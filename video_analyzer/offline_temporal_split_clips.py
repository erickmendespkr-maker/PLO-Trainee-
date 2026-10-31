"""Split OFFLINE, reviewed PLO decision clips at uncertain table-layout changes.

Usage: python offline_temporal_split_clips.py VIDEO BATCH_DIR TEMPORAL_REVIEW OUT_DIR

Produces separate MP4s for each safely reviewed geometry interval, never
concatenates across a transition, and explicitly records omitted time windows.
A decision within the transition guard is blocked entirely. Human review of
geometry is a *claim*, not verification of table identity, OCR, equity or EV.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

import offline_ev_table_crop as crop
import offline_temporal_batch_crops as existing
import offline_temporal_decision_locator as locator

STATUS = 'offline_temporal_split_crops_conditional_ev_unverified'
PART_STATUS = 'offline_temporal_split_crop_unverified'
MIN_PART_SECONDS = 0.5
MAX_PARTS = 48
GUARD_SECONDS = existing.GUARD_SECONDS


def require(ok, reason):
    crop.check(ok, reason)


def intersections(start, end, segments, table):
    """Return (segment number, start, end, region) for safe nonempty pieces."""
    pieces = []
    for idx, seg in enumerate(segments):
        left = max(start, seg['start_seconds'] + (GUARD_SECONDS if idx else 0))
        right = min(end, seg['end_seconds'] - (GUARD_SECONDS if idx + 1 < len(segments) else 0))
        if right - left >= MIN_PART_SECONDS - 1e-8:
            region = next(r for r in seg['regions'] if r['table_id'] == table)
            pieces.append((idx + 1, round(left, 6), round(right, 6), region))
    return pieces


def omitted_intervals(start, end, pieces):
    """All gaps, including discarded sub-0.5s pieces, remain visible in ledger."""
    omitted, cursor = [], start
    for _, left, right, _ in pieces:
        if left > cursor + 1e-6:
            omitted.append({'start_seconds': round(cursor, 6), 'end_seconds': round(left, 6)})
        cursor = right
    if end > cursor + 1e-6:
        omitted.append({'start_seconds': round(cursor, 6), 'end_seconds': round(end, 6)})
    return omitted


def preflight(video, batch_dir, review_json, output_dir):
    # Reuse the prior cycle's strict verification of ALL original batch entries,
    # report/video hashes, table identity claims, timestamps and review geometry.
    video, review_json, batch_path, out, _, _, inputs = existing.preflight(
        video, batch_dir, review_json, output_dir)
    w, h, duration = crop.media_info(video)
    video_sha = crop.digest(video)
    review = crop.read_json(review_json)
    segments = locator.validate_review(review, video_sha, w, h, duration)
    batch = crop.read_json(batch_path)
    plans, blocked = [], []
    used = set()
    for item in batch['clips']:
        cid, table, hand = item['clip_id'], item['table_id'], item['hand_id']
        report = crop.read_json(Path(batch_dir) / (cid + '.json'))
        start, length, pts = (report['clip_start_seconds'], report['clip_duration_seconds'],
                              report['decision_pts_seconds_claim'])
        end = min(duration, start + length)
        location = locator.locate(review, video_sha256=video_sha, width=w, height=h,
                                  duration=duration, table_id=table, timestamp=pts,
                                  boundary_guard_seconds=GUARD_SECONDS)
        if location['status'] != 'manual_geometry_claim_only':
            blocked.append({'clip_id': cid, 'table_id': table, 'hand_id': hand,
                            'reason': 'decision_near_uncertain_transition'})
            continue
        pieces = intersections(start, end, segments, table)
        # If the decision itself would be discarded, no useful annotated cut.
        if not any(left - 1e-6 <= pts < right - 1e-6 for _, left, right, _ in pieces):
            blocked.append({'clip_id': cid, 'table_id': table, 'hand_id': hand,
                            'reason': 'decision_not_in_safe_renderable_piece'})
            continue
        for idx, left, right, region in pieces:
            filename = f'split_{cid}_s{idx:02d}.mp4'
            metadata = f'split_{cid}_s{idx:02d}.json'
            require(filename not in used, 'duplicate output name')
            used.add(filename)
            for name in (filename, metadata):
                existing.no_collision(out / name)
            plans.append({'clip_id': cid, 'table_id': table, 'hand_id': hand,
                          'segment_index': idx, 'start': left, 'end': right,
                          'region': region, 'report': report,
                          'decision_in_part': left - 1e-6 <= pts < right - 1e-6,
                          'filename': filename, 'metadata': metadata,
                          'source_clip_report_sha256': crop.digest(Path(batch_dir) / (cid + '.json')),
                          'omitted_intervals': omitted_intervals(start, end, pieces)})
    require(len(plans) <= MAX_PARTS, 'too many split outputs')
    existing.no_collision(out / 'temporal_split_report.json')
    require(all(crop.digest(p) == sha for p, sha in inputs), 'input changed during preflight')
    return video, out, plans, blocked, inputs


def export(video, batch_dir, review_json, output_dir):
    video, out, plans, blocked, inputs = preflight(video, batch_dir, review_json, output_dir)
    created, parts = [], []
    try:
        for p in plans:
            with tempfile.TemporaryDirectory(prefix='plo_split_', dir=out) as directory:
                temp = Path(directory)
                r = p['region']
                report = p['report']
                overlay = (f"PLO {report['variant']} | {report['street']} | Mesa {p['table_id']}\n"
                           f"Acao declarada: {report.get('action_taken_claim_unverified', 'incerta')}\n"
                           "Trecho separado: transicao omitida; EV condicional nao verificado.")
                (temp / 'overlay.txt').write_text(overlay, encoding='utf-8')
                result = temp / 'result.mp4'
                filt = (f"crop={r['width']}:{r['height']}:{r['x']}:{r['y']},"
                        'drawtext=textfile=overlay.txt:expansion=none:fontcolor=white:'
                        'fontsize=12:box=1:boxcolor=black@0.75:x=4:y=4')
                subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                                '-ss', f"{p['start']:.6f}", '-i', str(video),
                                '-t', f"{p['end'] - p['start']:.6f}", '-map', '0:v:0',
                                '-vf', filt, '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                                '-crf', '28', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                                str(result)], cwd=temp, capture_output=True, text=True,
                               check=True, timeout=180)
                rw, rh, rd = crop.media_info(result)
                require((rw, rh) == (r['width'], r['height']) and
                        rd >= min(.4, (p['end'] - p['start']) * .5), 'invalid split MP4')
                require(all(crop.digest(f) == sha for f, sha in inputs),
                        'source changed during rendering')
                metadata = {'schema_version': 1, 'status': PART_STATUS,
                            'clip_id': p['clip_id'], 'table_id_claim': p['table_id'],
                            'hand_id': p['hand_id'], 'segment_index': p['segment_index'],
                            'source_video_sha256': inputs[0][1],
                            'source_temporal_review_sha256': inputs[1][1],
                            'source_batch_report_sha256': inputs[2][1],
                            'source_clip_report_sha256': p['source_clip_report_sha256'],
                            'region_claim': r, 'start_seconds': p['start'],
                            'end_seconds': p['end'],
                            'decision_pts_seconds_claim': report['decision_pts_seconds_claim'],
                            'decision_in_part': p['decision_in_part'],
                            'omitted_intervals_seconds': p['omitted_intervals'],
                            'rendered_duration_seconds': rd,
                            'filename': p['filename'], 'sha256': crop.digest(result),
                            'table_identity_verified': False,
                            'automatic_ocr_math_authorization': False,
                            'warning': 'Separate segments, no transition continuity or verified strategy.'}
                meta = temp / 'metadata.json'
                meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2,
                                           allow_nan=False) + '\n', encoding='utf-8')
                for src, name in ((result, p['filename']), (meta, p['metadata'])):
                    dest = out / name
                    existing.no_collision(dest)
                    os.link(src, dest)
                    created.append(dest)
                parts.append({'clip_id': p['clip_id'], 'table_id': p['table_id'],
                              'hand_id': p['hand_id'], 'segment_index': p['segment_index'],
                              'filename': p['filename'], 'metadata': p['metadata'],
                              'sha256': metadata['sha256'], 'start_seconds': p['start'],
                              'end_seconds': p['end'], 'decision_in_part': p['decision_in_part'],
                              'omitted_intervals_seconds': p['omitted_intervals']})
        require(all(crop.digest(f) == sha for f, sha in inputs),
                'source changed before ledger publication')
        ledger = {'schema_version': 1, 'status': STATUS,
                  'source_video_sha256': inputs[0][1],
                  'source_temporal_review_sha256': inputs[1][1],
                  'source_batch_report_sha256': inputs[2][1],
                  'rendered_count': len(parts), 'blocked_count': len(blocked),
                  'parts': parts, 'blocked': blocked,
                  'transition_guard_seconds': GUARD_SECONDS,
                  'min_part_seconds': MIN_PART_SECONDS,
                  'table_identity_verified': False,
                  'automatic_ocr_math_authorization': False,
                  'warning': 'Omitted intervals are NOT analyzed or reconstructed; no seamless continuity.'}
        with tempfile.TemporaryDirectory(prefix='plo_split_ledger_', dir=out) as directory:
            temp = Path(directory) / 'temporal_split_report.json'
            temp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2,
                                       allow_nan=False) + '\n', encoding='utf-8')
            dest = out / temp.name
            existing.no_collision(dest)
            os.link(temp, dest)
            created.append(dest)
        return ledger
    except BaseException:
        for f in reversed(created):
            f.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'batch_dir', 'temporal_review_json', 'output_dir'):
        parser.add_argument(name)
    a = parser.parse_args(argv)
    ledger = export(a.video, a.batch_dir, a.temporal_review_json, a.output_dir)
    print(json.dumps({'status': ledger['status'], 'rendered': ledger['rendered_count'],
                      'blocked': ledger['blocked_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
