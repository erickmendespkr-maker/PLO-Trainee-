"""Synthetic offline four-table PLO5/PLO6 Monte Carlo throughput check.

Measures the existing engine, not OCR, FFmpeg, video processing, or live play.
Usage: python offline_mc_four_table_benchmark.py NEW_RESULTS.json --samples 100
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time

import offline_omaha_equity_mc as mc

STATUS = 'synthetic_offline_four_table_mc_benchmark_not_video_validation'


def scenario(table_index: int, samples: int) -> dict:
    if type(table_index) is not int or table_index not in range(4):
        raise ValueError('table_index must be 0..3')
    if type(samples) is not int or not 100 <= samples <= 2000:
        raise ValueError('samples must be integer 100..2000')
    variant = 'PLO5' if table_index % 2 == 0 else 'PLO6'
    return {
        'schema_version': 1, 'game_type': variant,
        'hero_hole': ['As', 'Kd', 'Qc', 'Jh', 'Ts'] + (['9s'] if variant == 'PLO6' else []),
        'known_board': ['2c', '3d', '4h'],
        'explicit_villain_hands': [
            ['7c', '8d', '9h', 'Tc', 'Js'] + (['6c'] if variant == 'PLO6' else []),
            ['2h', '3s', '5d', '6h', '8c'] + (['7d'] if variant == 'PLO6' else []),
        ],
        'samples': samples, 'seed': 25700 + table_index,
        'range_assumption': 'Two artificial uniformly weighted opponent combinations; no video or OCR evidence.'
    }


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()


def benchmark(samples: int = 100, clock=time.perf_counter) -> dict:
    scenarios = [scenario(i, samples) for i in range(4)]
    engine = Path(mc.__file__).resolve()
    engine_blob_sha = git_blob_sha(engine.read_bytes())
    rows = []
    for index, raw in enumerate(scenarios):
        start = clock()
        result = mc.estimate(raw)
        elapsed = clock() - start
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('invalid elapsed time')
        if (result['samples'] != samples or
            result['wins'] + result['ties'] + result['losses'] != samples or
            result['exactly_two_private_three_board'] is not True or
            result['ready_for_ev'] is not False or
            result['video_evidence_verified'] is not False):
            raise ValueError('unexpected engine contract')
        rows.append({
            'table_id': f'synthetic_table_{index + 1}', 'variant': raw['game_type'],
            'seed': raw['seed'], 'samples': samples,
            'scenario_sha256': hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'wins': result['wins'], 'ties': result['ties'], 'losses': result['losses'],
            'equity_estimate': result['equity_estimate'],
            'equity_95pct_hoeffding_interval': result['equity_95pct_hoeffding_interval'],
            'elapsed_seconds': round(elapsed, 6),
        })
    return {'schema_version': 1, 'status': STATUS, 'engine_git_blob_sha': engine_blob_sha,
            'tables': rows, 'total_trials': 4 * samples,
            'total_elapsed_seconds': round(sum(x['elapsed_seconds'] for x in rows), 6),
            'limitations': ['synthetic fixed hands and ranges', 'no OCR or real videos',
                            'single process, sequential execution', 'timing depends on hardware',
                            'sampling CI excludes range and model uncertainty',
                            'not a strategy or betting recommendation']}


def write_new(report: dict, path: str | Path) -> None:
    target = Path(path)
    if (target.suffix != '.json' or not target.parent.is_dir() or
        target.parent.is_symlink() or target.exists() or target.is_symlink()):
        raise ValueError('output must be a new JSON file in an existing directory')
    staged = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=target.parent, prefix='.plo_mc_bench_',
                                         suffix='.tmp', delete=False, encoding='utf-8') as handle:
            staged = handle.name
            json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
        os.link(staged, target)
    finally:
        if staged and os.path.exists(staged):
            os.unlink(staged)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('new_results_json')
    parser.add_argument('--samples', type=int, default=100)
    args = parser.parse_args(argv)
    write_new(benchmark(args.samples), args.new_results_json)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
