"""Versioned, sparse offline river solution cache and exact public-path replay."""
import hashlib
import json
import sqlite3
from pathlib import Path
from plo5_post_gto_context import identity, normalize
from plo5_post_gto_tree import start, actions, step
from plo5_post_gto_river import solve
from plo5_pre_gto_context import need

VERSION = 'plo5-river-store-v1'
MAX_BYTES = 32 * 1024 * 1024
SOURCES = ('plo5_post_gto_store.py', 'plo5_post_gto_river.py',
           'plo5_post_gto_context.py', 'plo5_post_gto_tree.py',
           'plo5_pre_gto_context.py', 'plo5_pre_gto_cfr_native.py',
           'plo5_evaluator.py', 'plo5_rank_cache.py', 'offline_omaha_showdown.py',
           'plo5_post_gto_rake.py', 'plo5_post_gto_rake_solver.py')


def encode(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def file_digest(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def specification(context, iterations=500, pot_bps=(5000, 10000), *, cfr_executable=None, rake_on_fold=None):
    c = normalize(context)
    need(len(c['board']) == 5 and len(c['seats']) == 2
         and all(c['stacks'].values()), 'HU river only')
    need(rake_on_fold is None or type(rake_on_fold) is bool, 'Invalid fold rake rule')
    need(c['rake_bps'] == 0 or rake_on_fold is not None, 'Explicit fold rake rule required')
    use_rake = rake_on_fold is not None
    need(not use_rake or cfr_executable is None, 'Rake solver requires Python backend')
    need(type(iterations) is int and 1 <= iterations <= 50000, 'Invalid iterations')
    need(type(pot_bps) in (tuple, list) and len(pot_bps) <= 16 and
         all(type(x) is int and 1 <= x <= 10000 for x in pot_bps), 'Invalid sizings')
    sources = {p: file_digest(Path(__file__).with_name(p)) for p in SOURCES}
    spec = dict(schema=VERSION, context_key=identity(context), iterations=iterations,
                pot_bps=sorted(set(pot_bps)), source_sha256=sources,
                backend='python-rake' if use_rake else ('native' if cfr_executable is not None else 'python'),
                rake_on_fold=rake_on_fold,
                executable_sha256=file_digest(cfr_executable) if cfr_executable is not None else None)
    return digest(encode(spec)), spec


def manifest(context, pot_bps, node_limit=2000):
    need(type(node_limit) is int and 1 <= node_limit <= 10000, 'Invalid node budget')
    rows = []
    def visit(s, history):
        need(len(rows) < node_limit, 'Tree budget exceeded')
        n = len(rows)
        row = dict(node=n, history=history, position=s.actor, status=s.status,
                   pot=s.pot, remaining=list(s.remaining), total_paid=list(s.total_paid), actions=[])
        rows.append(row)
        if s.pending:
            for a, b in actions(s, pot_bps):
                entry = dict(action=a, amount=b, position=s.actor)
                child = visit(step(s, s.actor, a, b), history+[entry])
                row['actions'].append(dict(entry, child=child))
        return n
    visit(start(context), [])
    return rows


def _connection(path):
    con = sqlite3.connect(path, timeout=10)
    con.execute('CREATE TABLE IF NOT EXISTS river_cache_v1 (model_key TEXT PRIMARY KEY, spec TEXT NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)')
    return con


def solve_cached(path, context, iterations=500, pot_bps=(5000, 10000), *,
                 cfr_executable=None, node_limit=2000, max_work=20000000, native_timeout=120, rake_on_fold=None):
    key, spec = specification(context, iterations, pot_bps, cfr_executable=cfr_executable, rake_on_fold=rake_on_fold)
    need(type(node_limit) is int and 1 <= node_limit <= 10000, 'Invalid node budget')
    need(type(max_work) is int and 1 <= max_work <= 100000000, 'Invalid work budget')
    spec_json = encode(spec)
    con = _connection(path)
    try:
        row = con.execute('SELECT spec, length(CAST(payload AS BLOB)), checksum FROM river_cache_v1 WHERE model_key=?', (key,)).fetchone()
        if row is not None:
            saved_spec, size, checksum = row
            need(saved_spec == spec_json and size <= MAX_BYTES, 'Cache metadata mismatch')
            payload, = con.execute('SELECT payload FROM river_cache_v1 WHERE model_key=?', (key,)).fetchone()
            need(digest(payload) == checksum, 'Cache checksum mismatch')
            data = json.loads(payload)
            r = data['result']
            need(r['context_key'] == spec['context_key'] and r['backend'] == spec['backend'] and
                 r['iterations'] == iterations and r['nodes'] == len(data['tree']), 'Cache result mismatch')
            need(r['nodes'] <= node_limit and r['nodes']*r['legal_pairs']*(iterations+5) <= max_work, 'Cached result exceeds budget')
            return dict(data, cache_hit=True)
        tree = manifest(context, spec['pot_bps'], node_limit)
        if rake_on_fold is not None:
            from plo5_post_gto_rake_solver import solve as solve_rake
            r = solve_rake(context, iterations=iterations, pot_bps=spec['pot_bps'], node_limit=node_limit,
                           max_work=max_work, rake_on_fold=rake_on_fold)
        else:
            r = solve(context, iterations=iterations, pot_bps=spec['pot_bps'], node_limit=node_limit,
                      max_work=max_work, cfr_executable=cfr_executable, native_timeout=native_timeout)
        need(len(tree) == r['nodes'], 'Tree mismatch')
        need(specification(context, iterations, pot_bps, cfr_executable=cfr_executable, rake_on_fold=rake_on_fold)[0] == key, 'Model changed during solve')
        data = dict(model_key=key, specification=spec, tree=tree, result=r)
        payload = encode(data)
        need(len(payload.encode('utf-8')) <= MAX_BYTES, 'Cache payload budget exceeded')
        with con:
            con.execute('INSERT OR IGNORE INTO river_cache_v1 VALUES (?,?,?,?)', (key, spec_json, payload, digest(payload)))
        return dict(data, cache_hit=False)
    finally:
        con.close()


def lookup(data, history, holding):
    from plo5_pre_gto_context import cards
    h = cards(holding)
    need(type(history) is list, 'History must be a list')
    hits = [row for row in data['tree'] if row['history'] == history]
    if len(hits) != 1:
        return dict(status='UNMODELED_HISTORY')
    n = hits[0]['node']
    rows = [r for r in data['result']['policy'] if r['node'] == n and r['holding'] == h]
    if len(rows) != 1:
        return dict(status='UNMODELED_HOLDING_OR_TERMINAL')
    if rows[0]['opponent_reach_mass'] <= 0:
        return dict(status='ZERO_OPPONENT_REACH')
    return dict(status='CONDITIONAL_POLICY', model_key=data['model_key'], policy=rows[0],
                gap_bb=data['result'].get('nash_gap_bb'), nashconv_bb=data['result'].get('nashconv_bb'), gto_solution=False)
