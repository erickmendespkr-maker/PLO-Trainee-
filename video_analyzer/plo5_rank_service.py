"""Resolve exact ranks by C++ canonical IDs, immutable shards and optional native misses.
A rank is not equity, EV or a strategy. No implicit persistence of computed misses.
"""
import subprocess
from pathlib import Path
from plo5_index_native import rank_batch,SIZES
from plo5_pre_gto_context import need


def calculate_missing(executable,street,ids,timeout=120):
    need(type(street) is int and street in (3,4,5),'Invalid street')
    need(type(ids) is list and len(ids)<=100000 and all(type(x) is int and 0<=x<SIZES[street] for x in ids),'Invalid indices')
    if not ids:return []
    p=subprocess.run([str(Path(executable).resolve(strict=True))],input=f'{street} {len(ids)}\n'+'\n'.join(map(str,ids))+'\n',text=True,capture_output=True,check=True,timeout=timeout)
    out=[int(v) for v in p.stdout.splitlines()]
    need(len(out)==len(ids) and all(1<=v<=7462 for v in out),'Invalid native ranks')
    return out


def lookup_states(index_executable,reader,street,states,*,rank_executable=None,timeout=120):
    need(type(street) is int and street in (3,4,5),'Invalid street')
    ids=rank_batch(index_executable,street,states,timeout=timeout)
    found={};missing=[]
    for i in dict.fromkeys(ids):
        v=reader.lookup(street,i) if reader is not None else None
        need(v is None or type(v) is int and 1<=v<=7462,'Invalid shard rank')
        found[i]=dict(index=i,rank=v,source='SHARD' if v is not None else 'UNSTORED')
        if v is None:missing.append(i)
    if missing and rank_executable is not None:
        for i,v in zip(missing,calculate_missing(rank_executable,street,missing,timeout)):
            found[i]=dict(index=i,rank=v,source='NATIVE_COMPUTED')
    return [dict(found[i]) for i in ids]
