"""Lossless bounded sparse cache of offline multiway postflop solutions.
Physical context identity is deliberately distinct from single-hand suit classes.
Only trusted local cache files; checksum is corruption detection, not authentication.
"""
import hashlib
import json
import sqlite3
import sys
import zlib
from contextlib import closing
from pathlib import Path
from plo5_pre_gto_context import need, cards
from plo5_post_gto_context import normalize
from plo5_post_gto_multiway import prior, model_identity, solve

VERSION = 'multiway-strategy-zlib-v1'
MAX_RAW = 64*1024**2
MAX_PACKED = 32*1024**2
CACHE_MAX_BYTES = 128*1024**2
CACHE_MAX_ENTRIES = 512
SOURCES = ('plo5_strategy_cache.py','plo5_post_gto_multiway.py','plo5_post_gto_multiway_ledger.py',
           'plo5_post_gto_context.py','plo5_post_gto_tree.py','plo5_pre_gto_context.py',
           'plo5_multiway_native.py','plo5_evaluator.py','plo5_rank_cache.py','offline_omaha_showdown.py')


def encode(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def sha(data):return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def specification(context,iterations=100,pot_bps=(),*,rake_on_fold,joint=None,
                  max_deals=4096,max_outcomes=100000,node_limit=100000,max_work=20000000,
                  cfr_executable=None,include_deal_values=False):
    c=normalize(context)
    need(all(c['stacks'].values()),'Positive stacks required')
    need(type(rake_on_fold) is bool and type(include_deal_values) is bool,'Invalid flag')
    for x,hi in ((iterations,50000),(max_deals,4096),(max_outcomes,155648),(node_limit,100000),(max_work,100000000)):
        need(type(x) is int and 1<=x<=hi,'Invalid budget')
    need(type(pot_bps) in (tuple,list) and len(pot_bps)<=16 and all(type(x) is int and 1<=x<=10000 for x in pot_bps),'Invalid sizing')
    rows=prior(context,joint,max_deals)
    sizes=sorted(set(pot_bps))
    spec=dict(schema=VERSION,model_key=model_identity(context,rows,rake_on_fold,sizes),iterations=iterations,
              include_deal_values=include_deal_values,backend='native' if cfr_executable is not None else 'python',
              executable_sha256=file_sha(cfr_executable) if cfr_executable is not None else None,
              python=list(sys.version_info[:3]),source_sha256={n:file_sha(Path(__file__).with_name(n)) for n in SOURCES},
              budgets=[max_deals,max_outcomes,node_limit,max_work])
    return sha(encode(spec)),spec


def pack(result):
    raw=encode(result);need(len(raw)<=MAX_RAW,'Raw payload budget exceeded')
    blob=zlib.compress(raw,6);need(len(blob)<=MAX_PACKED,'Compressed payload budget exceeded')
    return blob,len(raw),sha(raw)


def unpack(blob,size,checksum):
    need(type(size) is int and 0<=size<=MAX_RAW and type(blob) is bytes and len(blob)<=MAX_PACKED,'Payload budget exceeded')
    d=zlib.decompressobj()
    try:raw=d.decompress(blob,size+1)
    except zlib.error as e:raise ValueError('Invalid compressed payload') from e
    need(d.eof and not d.unused_data and not d.unconsumed_tail and len(raw)==size,'Compressed size mismatch')
    need(sha(raw)==checksum,'Cache checksum mismatch')
    return json.loads(raw)


def connection(path):
    con=sqlite3.connect(path,timeout=10)
    con.execute('CREATE TABLE IF NOT EXISTS strategy_zlib_v1 (cache_key TEXT PRIMARY KEY, spec BLOB NOT NULL, raw_size INTEGER NOT NULL, checksum TEXT NOT NULL, payload BLOB NOT NULL)')
    return con


def _validate(r,spec):
    need(r['model_key']==spec['model_key'] and r['iterations']==spec['iterations'] and r['backend']==spec['backend']
         and ('conditional_values' in r)==spec['include_deal_values'] and r['nodes']==len(r['tree']), 'Cache result mismatch')
    md,mo,nl,mw=spec['budgets']
    need(r['legal_deals']<=md and r['chance_outcomes']<=mo and r['nodes']<=nl and r['work_per_iteration']*(r['iterations']+5)<=mw,'Cache budget mismatch')


def prune(con,*,max_bytes=CACHE_MAX_BYTES,max_entries=CACHE_MAX_ENTRIES):
    """FIFO logical byte/row budget, caller owns write transaction. No VACUUM.
    SQLite pages and journal can exceed the logical budget; free pages are reusable.
    """
    need(type(max_bytes) is int and 0<=max_bytes<=2**31 and type(max_entries) is int and 0<=max_entries<=100000,'Invalid cache quota')
    total,count=con.execute('SELECT COALESCE(SUM(length(spec)+length(payload)+length(cache_key)+length(checksum)+8),0),COUNT(*) FROM strategy_zlib_v1').fetchone()
    removed=0
    while total>max_bytes or count>max_entries:
        row=con.execute('SELECT rowid,length(spec)+length(payload)+length(cache_key)+length(checksum)+8 FROM strategy_zlib_v1 ORDER BY rowid LIMIT 1').fetchone()
        if row is None:break
        con.execute('DELETE FROM strategy_zlib_v1 WHERE rowid=?',(row[0],));total-=row[1];count-=1;removed+=1
    return dict(entries=count,logical_bytes=total,removed=removed)


def solve_cached(path,context,iterations=100,pot_bps=(),*,rake_on_fold,joint=None,
                 max_deals=4096,max_outcomes=100000,node_limit=100000,max_work=20000000,
                 cfr_executable=None,native_timeout=120,include_deal_values=False):
    opts=dict(rake_on_fold=rake_on_fold,joint=joint,max_deals=max_deals,max_outcomes=max_outcomes,node_limit=node_limit,
              max_work=max_work,cfr_executable=cfr_executable,include_deal_values=include_deal_values)
    key,spec=specification(context,iterations,pot_bps,**opts);encoded=encode(spec)
    with closing(connection(path)) as con:
        row=con.execute('SELECT spec,raw_size,checksum,CASE WHEN length(payload)<=? THEN payload ELSE NULL END FROM strategy_zlib_v1 WHERE cache_key=?',(MAX_PACKED,key)).fetchone()
        if row is not None:
            saved,size,checksum,blob=row;need(saved==encoded,'Cache specification mismatch')
            r=unpack(blob,size,checksum);_validate(r,spec)
            return dict(cache_key=key,cache_hit=True,result=r,raw_bytes=size,stored_bytes=len(blob))
        r=solve(context,iterations,sorted(set(pot_bps)),native_timeout=native_timeout,**opts);_validate(r,spec)
        need(specification(context,iterations,pot_bps,**opts)[0]==key,'Model changed during solve')
        blob,size,checksum=pack(r)
        with con:
            con.execute('INSERT OR IGNORE INTO strategy_zlib_v1 VALUES (?,?,?,?,?)',(key,encoded,size,checksum,blob))
            prune(con)
        return dict(cache_key=key,cache_hit=False,result=r,raw_bytes=size,stored_bytes=len(blob))


def lookup(data,history,holding):
    need(type(history) is list,'Invalid history');h=cards(holding);r=data['result']
    nodes=[x['node'] for x in r['tree'] if x['history']==history]
    if len(nodes)!=1:return dict(status='UNMODELED_HISTORY')
    rows=[x for x in r['policy'] if x['node']==nodes[0] and x['holding']==h]
    if len(rows)!=1:return dict(status='UNMODELED_HOLDING_OR_TERMINAL')
    if rows[0]['opponent_reach_mass']<=0:return dict(status='ZERO_OPPONENT_REACH')
    return dict(status='CONDITIONAL_POLICY',cache_key=data['cache_key'],policy=rows[0],nashconv_bb=r['nashconv_bb'],gto_solution=False)
