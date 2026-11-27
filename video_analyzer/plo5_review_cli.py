"""Offline review CLI for candidate manifests or explicitly declared model inputs."""
import argparse
import json
from pathlib import Path
from plo5_pre_gto_context import need
from plo5_review import visual,postflop,preflop,from_preflop,declared_settlement
from plo5_review_html import write


def read(path):
    p=Path(path);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=64*1024**2,'Invalid JSON input')
    d=json.loads(p.read_text(encoding='utf-8'));need(type(d) is dict,'JSON object required');return d


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('visual','postflop','preflop','bridge','settlement'));p.add_argument('source');p.add_argument('output')
    p.add_argument('--cache');p.add_argument('--native');p.add_argument('--index');p.add_argument('--rank');p.add_argument('--screens',type=int,default=0)
    a=p.parse_args(argv);need(0<=a.screens<=20,'Invalid screenshot count')
    d=read(a.source);frames=[];root=Path(a.source).parent
    if a.mode=='visual':
        r=visual(d)
        if a.screens:
            all_frames=d['frames'];n=min(a.screens,len(all_frames))
            frames=[all_frames[i*(len(all_frames)-1)//max(1,n-1)] for i in range(n)]
    elif a.mode=='preflop':
        need(set(d) in ({'context'},{'context','policy'}),'Invalid preflop fields');r=preflop(**d)
    elif a.mode=='settlement':
        need(set(d)=={'stacks','sb','bb','events','holdings','rake_bps','rake_cap','rake_on_fold','observations'},'Invalid settlement fields');r=declared_settlement(**d)
    else:
        need(a.cache is not None,'Strategy cache required');need(bool(a.index)==bool(a.rank),'Supply both rank executables or neither')
        common={'context','history','holding','action'};extra={'iterations','pot_bps'}
        required=common|({'rake_on_fold'} if a.mode=='postflop' else {'policy','flop'})
        optional=extra|({'joint'} if a.mode=='postflop' else {'approximate_joint'})
        need(required<=set(d)<=required|optional,'Invalid model input fields')
        solver=postflop if a.mode=='postflop' else from_preflop
        r=solver(a.cache,**d,cfr_executable=a.native,rank_executables=(a.index,a.rank) if a.index else None)
    write(a.output,r,root=root,frames=frames)
    print(json.dumps(dict(status=r['status'],report=str(Path(a.output).resolve()),gto_solution=False),ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
