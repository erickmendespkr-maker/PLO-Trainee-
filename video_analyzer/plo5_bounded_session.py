"""Offline windowed scan: reuse recognition caches, persist bounded candidate manifests.
No full-session frame list, no OCR rerun for prints, no verified hand inference.
"""
import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from fractions import Fraction
from plo5_pre_gto_context import need
from plo5_video_stream import scan,digest
from plo5_fast_money import FastMoneyReader
from plo5_mixed_cards_v2 import MixedCardReader


def windows(start,seconds,chunk):
    need(type(start) is int and start>=0 and type(seconds) is int and 2<=seconds<=86400,'Invalid session range')
    need(type(chunk) is int and 2<=chunk<=120,'Invalid window size')
    n=(seconds+chunk-1)//chunk
    # Balance instead of leaving a one-second tail.
    if n>1 and seconds<2*n:raise ValueError('Window size leaves unsupported tail')
    q,r=divmod(seconds,n)
    for i in range(n):
        length=q+(i<r);yield start,length;start+=length


def run(source,output,start,seconds,*,chunk=120,capacity=512,workers=2,backend='cli',ppp=None,suprema=None,progress=None):
    """Write one independently audited window at a time; keep cache and OCR workers.
    Window boundaries are explicit; no automatic hand merging across them.
    The source is verified by the existing scanner per window, and each file hash
    is retained so later stages can reject changed manifests.
    """
    parts=list(windows(start,seconds,chunk));source=Path(source);out=Path(output)
    need(source.is_file() and not source.is_symlink() and source.suffix.lower()=='.mp4','Local MP4 required')
    need(not out.exists() and not out.is_symlink() and out.parent.is_dir(),'New output directory required')
    t=time.perf_counter();bank_hashes={p:digest(v) for p,v in [('pppoker',ppp),('suprema',suprema)] if v is not None}
    source_hash=digest(source);cards=MixedCardReader(ppp,suprema,capacity=capacity) if bank_hashes else None
    rows=[];frame_count=0;missing=0;both=0;active=0;last=None
    with tempfile.TemporaryDirectory(prefix='.plo22-',dir=out.parent) as temp:
        stage=Path(temp)/'session';stage.mkdir()
        with FastMoneyReader(capacity,workers,backend=backend) as money:
            for i,(a,n) in enumerate(parts,1):
                r=scan(source,a,n,reader=money,card_reader=cards);need(r['source_sha256']==source_hash,'Source changed between windows')
                stamps=[Fraction(f['pts']) for f in r['frames']]
                need(stamps and (last is None or stamps[0]>last),'Window overlap or missing frames');last=stamps[-1]
                buckets={int(v//1) for v in stamps};gaps=sorted(set(range(a,a+n))-buckets)
                # Keep unique logical IDs across chunks; recompute evidence references.
                from plo5_reconstruction_candidates import collect
                for f in r['frames']:
                    f['file']=f'w{i:05d}_'+f['file']
                    for c in f.get('cards',[]):
                        active+=c['platform'] is not None;both+=c['hero_cards'] is not None and c['board_cards'] is not None
                r['evidence']=collect(r['frames']);r['window_start']=a;r['window_seconds']=n;r['missing_sample_seconds']=gaps;r['card_bank_sha256']=bank_hashes;r['money_backend']=backend
                p=stage/f'window_{i:05d}.json'
                with p.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,allow_nan=False,separators=(',',':'))
                frame_count+=len(stamps);missing+=len(gaps)
                rows.append(dict(file=p.name,sha256=digest(p),start=a,seconds=n,frames=len(stamps),missing_sample_seconds=gaps,scan_seconds=r['wall_seconds']))
                if progress is not None:progress(dict(rows[-1]))
                del r
            stats=money.cache.stats();layout=money.layout.stats();calls=money.calls
        need(digest(source)==source_hash and all(digest(v)==bank_hashes[p] for p,v in [('pppoker',ppp),('suprema',suprema)] if v is not None),'Source or bank changed')
        result=dict(version='plo5-windowed-candidates-v1',variant=5,source_sha256=source_hash,card_bank_sha256=bank_hashes,windows=rows,frames=frame_count,missing_sample_seconds=missing,active_card_slots=active,complete_card_state_candidates=both,money_cache=stats,layout_cache=layout,card_cache=cards.stats() if cards else None,ocr_calls=calls,backend=backend,wall_seconds=time.perf_counter()-t,hands_reconstructed=False,strategy_authorized=False,drivehud_beta=False)
        (stage/'session.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video');p.add_argument('output');p.add_argument('--start',type=int,default=0);p.add_argument('--seconds',type=int,required=True);p.add_argument('--chunk',type=int,default=120);p.add_argument('--workers',type=int,choices=(1,2,3),default=2);p.add_argument('--capacity',type=int,default=512);p.add_argument('--backend',choices=('cli','native'),default='cli');p.add_argument('--ppp');p.add_argument('--suprema');a=p.parse_args(argv)
    r=run(a.video,a.output,a.start,a.seconds,chunk=a.chunk,workers=a.workers,capacity=a.capacity,backend=a.backend,ppp=a.ppp,suprema=a.suprema,progress=lambda row:print(json.dumps(row),flush=True));print(json.dumps({k:v for k,v in r.items() if k!='windows'}));return 0

if __name__=='__main__':raise SystemExit(main())
