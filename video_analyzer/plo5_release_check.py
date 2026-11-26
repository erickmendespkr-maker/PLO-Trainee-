"""Offline release diagnostic for PLO5. Imports are checked in isolated subprocesses."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from plo5_launcher import preflight

ROOT = Path(__file__).resolve().parent
VISUAL = ('plo5_windows_candidate', 'plo5_ingest_job', 'plo5_dense_timeline',
          'plo5_recognition_cache', 'plo5_financial_observations',
          'plo5_window_review', 'plo5_balance_review', 'plo5_review_pipeline')
STRATEGY = ('plo5_equity_store', 'plo5_reference_audit', 'plo5_evaluator',
            'plo5_river_solver', 'plo5_river_accelerated',
            'plo5_river_report_audit', 'plo5_strategy_integration',
            'plo5_study_report', 'plo5_visual_report')
PROBE = ('import importlib, pathlib, sys; root=pathlib.Path(sys.argv[1]).resolve(); '
         'sys.path.insert(0,str(root)); module=importlib.import_module(sys.argv[2]); '
         'assert pathlib.Path(module.__file__).resolve()==root/(sys.argv[2]+".py"), "Wrong module origin"')


def imports(root, names, *, timeout=20):
    root = Path(root).resolve()
    rows = {}
    for name in names:
        if not name.isidentifier() or name in rows:
            raise ValueError('Invalid or duplicate module name')
        source = root / (name + '.py')
        if not source.is_file() or source.is_symlink():
            rows[name] = {'ok': False, 'status': 'MISSING_SOURCE'}
            continue
        try:
            p = subprocess.run([sys.executable, '-I', '-B', '-c', PROBE, str(root), name],
                               cwd=root, stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, errors='replace', timeout=timeout, check=False)
            rows[name] = {'ok': p.returncode == 0, 'status': 'IMPORTED' if p.returncode == 0 else 'IMPORT_FAILED'}
            if p.returncode:
                rows[name]['detail'] = (p.stderr or p.stdout)[-2000:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            rows[name] = {'ok': False, 'status': 'PROBE_FAILED', 'detail': str(exc)}
    return rows


def check(equity=None, *, root=ROOT):
    started = time.perf_counter()
    env = preflight(equity, root=root)
    visual = imports(root, VISUAL)
    strategy = imports(root, STRATEGY)
    visual_ready = env['visual_preflight_ok'] and env['checks']['tkinter'] and all(r['ok'] for r in visual.values())
    strategy_ready = all(r['ok'] for r in strategy.values())
    return {'variant': 5, 'status': 'DEPENDENCY_DIAGNOSTIC_ONLY', 'environment': env,
            'visual_imports': visual, 'strategy_imports': strategy,
            'visual_startup_preflight_ok': visual_ready,
            'strategy_imports_ok': strategy_ready,
            'strategy_snapshot_reviewed': env['equity_status'] == 'REVIEWED_BINARY',
            'wall_seconds': time.perf_counter()-started,
            'complete_session_verified': False, 'windows_verified': False, 'mvp_certified': False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--equity'); p.add_argument('--require-strategy', action='store_true'); p.add_argument('--output')
    a = p.parse_args(argv)
    r = check(a.equity)
    raw = json.dumps(r, ensure_ascii=True, indent=2)
    if a.output:
        out = Path(a.output)
        if out.is_symlink() or out.exists():
            raise ValueError('New diagnostic output required')
        with out.open('x', encoding='utf-8') as f: f.write(raw+'\n')
    print(raw)
    ok = r['visual_startup_preflight_ok']
    if a.require_strategy:
        ok = ok and r['strategy_imports_ok'] and r['strategy_snapshot_reviewed']
    return 0 if ok else 1


if __name__ == '__main__': raise SystemExit(main())
