"""Review-only PLO5 table presence and board reset candidates on audited job crops."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

from PIL import Image
from offline_real_video_probe import classify
from offline_board_street_proposals import sample_board
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest, unique_pairs
from offline_video_ingest_probe import sha256, require
from plo5_ingest_job import read_bound_evidence

BOARD = {'flop_candidate', 'turn_candidate', 'river_candidate'}
EMPTY = 'no_faceup_board_detected'


def validate_calibration(cfg, regions):
    require(type(cfg) is dict and set(cfg) == {'felt_rgb', 'tolerance', 'board_strip'}, 'Invalid calibration fields')
    rgb, tol, strip = cfg['felt_rgb'], cfg['tolerance'], cfg['board_strip']
    require(type(rgb) is list and len(rgb) == 3 and all(type(v) is int and 0 <= v <= 255 for v in rgb)
            and type(tol) is int and 1 <= tol <= 80, 'Invalid felt calibration')
    keys = {'offset_x', 'offset_y', 'step_x', 'width', 'height', 'white_min_rgb', 'min_white_fraction'}
    require(type(strip) is dict and set(strip) == keys, 'Invalid board strip fields')
    require(all(type(strip[k]) is int and 0 <= strip[k] <= 8192 for k in keys - {'min_white_fraction'})
            and strip['step_x'] >= strip['width'] >= 8 and strip['height'] >= 8
            and 170 <= strip['white_min_rgb'] <= 250
            and type(strip['min_white_fraction']) in (int,float) and .25 <= strip['min_white_fraction'] <= .9,
            'Invalid board strip')
    for r in regions:
        require(strip['offset_x'] + 4 * strip['step_x'] + strip['width'] <= r['width']
                and strip['offset_y'] + strip['height'] <= r['height'], 'Board strip outside crop')


def observe(image, region, calibration):
    """Reuse existing calibrated classifiers on a crop, not a full frame."""
    require(image.size == (region['width'], region['height']), 'Crop geometry mismatch')
    slot = dict(region, x=0, y=0)
    presence = classify(image, slot, calibration['felt_rgb'], calibration['tolerance'])
    board = sample_board(image, slot, calibration['board_strip']) if presence['proposal'] == 'likely_visible' else None
    return presence, board


def propose_resets(observations, *, max_gap=10.):
    """Two distinct board observations followed by two empty ones; never an exact boundary."""
    require(type(max_gap) in (int,float) and math.isfinite(max_gap) and 0 < max_gap <= 30, 'Invalid maximum gap')
    groups = defaultdict(list)
    for row in observations:
        t, pts = row['table_id'], row['pts']
        require(type(t) is int and 1 <= t <= 4 and type(pts) in (int,float) and math.isfinite(pts), 'Invalid observation')
        groups[t].append(row)
    candidates, duplicates = [], 0
    for t, rows in sorted(groups.items()):
        previous, board_run, empty_run, anchor = None, [], [], None
        for row in sorted(rows, key=lambda r: r['pts']):
            pts = row['pts']
            if previous is not None and pts == previous:
                duplicates += 1
                continue
            if previous is not None and pts - previous > max_gap:
                board_run, empty_run, anchor = [], [], None
            previous = pts
            stage = row['street'] if row['visible'] else None
            if stage in BOARD:
                board_run.append(row)
                board_run = board_run[-2:]
                empty_run, anchor = [], None
            elif stage == EMPTY:
                if len(board_run) == 2 and not empty_run:
                    anchor = list(board_run)
                board_run = []
                if anchor is not None:
                    empty_run.append(row)
                    if len(empty_run) == 2:
                        candidates.append({'table_id': t, 'interval_pts': [anchor[-1]['pts'], empty_run[0]['pts']],
                                           'confirmation_observation_pts': pts,
                                           'evidence_files': [a['file'] for a in anchor] + [empty_run[0]['file'], row['file']],
                                           'status': 'board_reset_candidate_needs_review', 'hand_boundary_verified': False})
                        empty_run, anchor = [], None
            else:
                board_run, empty_run, anchor = [], [], None
    return candidates, duplicates


def analyze_job(database, job_id, calibration_path, *, max_gap=10.):
    binding = read_bound_evidence(database, job_id)
    job = OfflineJobStore(database).get(job_id)
    folder = Path(job['result_path']).parent / 'evidence/ingest'
    cfg_path = Path(calibration_path)
    require(cfg_path.is_file() and not cfg_path.is_symlink() and 0 < cfg_path.stat().st_size <= 8192, 'Unsafe calibration')
    cfg_sha = sha256(cfg_path)
    cfg = json.loads(cfg_path.read_text('utf-8'), object_pairs_hook=unique_pairs)
    manifest = read_manifest(folder / 'manifest.json')
    validate_calibration(cfg, manifest['regions'])
    regions = {r['table_id']: r for r in manifest['regions']}
    observations = []
    for s in manifest['samples']:
        crop = folder / s['file']
        with Image.open(crop) as image:
            presence, board = observe(image.convert('RGB'), regions[s['table_id']], cfg)
        observations.append({'table_id': s['table_id'], 'pts': s['actual_frame_timestamp_seconds'],
                             'file': s['file'], 'crop_sha256': s['sha256'],
                             'visible': presence['proposal'] == 'likely_visible', 'presence': presence,
                             'street': board['street_proposal'] if board else None, 'board': board})
    candidates, duplicates = propose_resets(observations, max_gap=max_gap)
    require(sha256(cfg_path) == cfg_sha and read_bound_evidence(database, job_id) == binding, 'Inputs changed')
    return {'schema_version': 1, 'job_id': job_id, 'variant': 5, 'source_sha256': binding['source_sha256'],
            'manifest_sha256': binding['reports']['evidence/ingest/manifest.json'], 'calibration_sha256': cfg_sha,
            'status': 'unverified_table_presence_and_board_reset_candidates', 'max_gap_seconds': max_gap,
            'observations': observations, 'candidates': candidates, 'duplicate_pts_skipped': duplicates,
            'hands_reconstructed': False, 'automatic_hand_boundaries_authorized': False,
            'automatic_clip_selection_authorized': False, 'equity_ev_authorized': False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database'); p.add_argument('job_id'); p.add_argument('calibration'); p.add_argument('output')
    p.add_argument('--max-gap', type=float, default=10.)
    a = p.parse_args(argv)
    target = Path(a.output)
    require(target.suffix == '.json' and not target.exists() and not target.is_symlink(), 'New JSON output required')
    report = analyze_job(a.database, a.job_id, a.calibration, max_gap=a.max_gap)
    with target.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, allow_nan=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
