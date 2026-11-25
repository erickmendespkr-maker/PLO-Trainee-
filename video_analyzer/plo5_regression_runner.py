"""Reproducible selected offline PLO5 regression gate; no network or deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parent
BASELINE = '7e6490bc27d8867182e121dc92490d16cddf09c5'
EQUITY_SHA = 'bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a'
GROUPS = {
    'contracts': (8, ('test_plo5_offline_contracts',)),
    'performance': (5, ('test_plo5_performance',)),
    'integration': (47, ('test_plo5_decision_analysis','test_plo5_hand_classes','test_plo5_hand_structure','test_plo5_preflop_context','test_plo5_individual_report')),
    'strategy': (78, ('test_strategic_backup','test_strategic_coverage','test_strategic_import','test_strategic_normalize','test_strategic_sources','test_strategic_store')),
    'math': (93, ('test_plo5_evaluator','test_plo5_equity','test_plo5_action_ev','test_plo5_financial_reconcile','test_plo5_ev_comparison','test_plo5_stackoff','test_plo5_board_texture','test_plo5_postflop_draws','test_plo5_multiway_implied','test_plo5_leak_review')),
    'ingest': (47, ('test_local_ingest','test_offline_ingest_audited_pipeline','test_offline_video_ingest_probe','test_plo5_ingest_job','test_plo5_equity_store')),
    'recognition': (42, ('test_plo5_boundary_candidates','test_plo5_card_candidates','test_plo5_context_candidates','test_plo5_action_candidates','test_plo5_hand_drafts','test_plo5_result_candidates')),
    'export': (8, ('test_plo5_session_export',)),
}


def need(ok, message):
    if not ok: raise ValueError(message)


def git_blob(path):
    p=Path(path);need(p.is_file() and not p.is_symlink(),'Missing or unsafe source: '+p.name)
    raw=p.read_bytes()
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def inventory(root=ROOT, *, candidate=False):
    root=Path(root);manifest=root/'plo5_regression_baseline.txt'
    need(manifest.is_file() and not manifest.is_symlink(),'Missing baseline manifest')
    expected={}
    for line in manifest.read_text('utf-8').splitlines():
        name,h=line.split()
        need(re.fullmatch(r'[a-z0-9_]+',name) and re.fullmatch(r'[0-9a-f]{40}',h) and name not in expected,'Invalid baseline entry')
        expected[name]=h
    need(len(expected)==81,'Unexpected baseline inventory size')
    observed={name:git_blob(root/(name+'.py')) for name in expected}
    mismatches=sorted(name for name,h in expected.items() if observed[name]!=h)
    need(candidate or not mismatches,'Baseline source mismatch: '+', '.join(mismatches))
    return {'baseline_commit':BASELINE,'baseline_manifest_blob':git_blob(manifest),
            'baseline_files':len(expected),'baseline_mismatches':mismatches,
            'source_blobs':{**observed,**{n:git_blob(root/(n+'.py')) for n in ('plo5_regression_runner','test_plo5_offline_contracts')}}}


def snapshot(path):
    p=Path(path);need(p.is_file() and not p.is_symlink(),'Reviewed equity SQLite required')
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    need(h.hexdigest()==EQUITY_SHA,'Unreviewed equity snapshot')
    return str(p.resolve())


def preflight(db):
    os.environ['PLO5_REVIEWED_EQUITY_DB']=snapshot(db)
    from PIL import __version__ as pillow
    import sqlite3
    tools={name:shutil.which(name) for name in ('ffmpeg','ffprobe','tesseract')}
    need(all(tools.values()),'Missing FFmpeg, FFprobe or Tesseract')
    return {'python':platform.python_version(),'platform':platform.platform(),'pillow':pillow,'sqlite':sqlite3.sqlite_version,'tools':tools,'equity_sha256':EQUITY_SHA}


def test_ids(suite):
    ids=[]
    for test in suite:
        if isinstance(test,unittest.TestSuite):ids.extend(test_ids(test))
        else:ids.append(test.id())
    return ids


def run_suite(suite, expected, *, stream=None):
    ids=test_ids(suite)
    need(len(ids)==expected and len(set(ids))==expected,'Unexpected or duplicate test collection')
    need(not any(name.startswith('unittest.loader._FailedTest.') for name in ids),'Test import failed')
    start=time.perf_counter();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    bad=len(result.failures)+len(result.errors)+len(result.skipped)+len(result.expectedFailures)+len(result.unexpectedSuccesses)
    ok=result.wasSuccessful() and bad==0 and result.testsRun==expected
    return {'expected':expected,'executed':result.testsRun,'test_ids':ids,'seconds':time.perf_counter()-start,
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'expected_failures':len(result.expectedFailures),'unexpected_successes':len(result.unexpectedSuccesses),
            'strict_pass':ok}


def execute(db, groups, *, candidate=False):
    need(groups and len(set(groups))==len(groups) and all(g in GROUPS for g in groups),'Invalid group selection')
    before=inventory(candidate=candidate);env=preflight(db);results={};all_ids=set()
    for group in groups:
        expected,modules=GROUPS[group]
        loader=unittest.TestLoader();suite=loader.loadTestsFromNames(modules)
        need(not loader.errors,'Test collection failed: '+str(loader.errors))
        ids=test_ids(suite);need(all(n.split('.')[0] in modules for n in ids) and not all_ids.intersection(ids),'Foreign or repeated test collection')
        all_ids.update(ids);results[group]=run_suite(suite,expected)
    need(inventory(candidate=candidate)==before and snapshot(db)==env_path(),'Source or snapshot changed during tests')
    passed=all(r['strict_pass'] for r in results.values())
    return {'variant':5,'status':'SELECTED_OFFLINE_REGRESSION_PASS' if passed else 'SELECTED_OFFLINE_REGRESSION_FAIL',
            'environment':env,'inventory':before,'groups':results,'unique_tests_collected':len(all_ids),
            'tests_executed':sum(r['executed'] for r in results.values()),'all_selected_groups_passed':passed,
            'full_repository_suite':False,'real_session_validated':False,'gto_solution':False,'mvp_certified':False}


def env_path(): return os.environ['PLO5_REVIEWED_EQUITY_DB']


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--equity-db',required=True);p.add_argument('--output',required=True)
    p.add_argument('--group',choices=tuple(GROUPS),action='append');p.add_argument('--candidate',action='store_true',help='Allow changed baseline source blobs, but record every mismatch')
    a=p.parse_args(argv);out=Path(a.output)
    need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    report=execute(a.equity_db,a.group or list(GROUPS),candidate=a.candidate)
    with out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False)
    return 0 if report['all_selected_groups_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
