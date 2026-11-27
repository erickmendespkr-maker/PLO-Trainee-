"""Offline PLO5 review candidate: bounded RGB scan, selective evidence and model review."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from plo5_pre_gto_context import need
from plo5_video_stream import scan, digest
from plo5_review_session import visual_session, review_batch, model_page, read_json


class EvidenceReader:
    """Second pass reuses observations; only selected RGB frames become PNGs."""
    def __init__(self, first, wanted, folder):
        self.frames=first['frames'];self.wanted=wanted;self.folder=folder;self.i=0;self.saved={}
        self.cache=self.layout=self
    def stats(self):return {'replayed_frames':self.i}
    def scan(self,image):
        need(self.i<len(self.frames),'Unexpected evidence frame')
        row=self.frames[self.i];self.i+=1
        need(hashlib.sha256(image.tobytes()).hexdigest()==row['rgb_sha256'],'RGB evidence mismatch')
        if row['file'] in self.wanted:
            name=Path(row['file']).with_suffix('.png').name;p=self.folder/name
            with p.open('xb') as f:image.save(f,format='PNG')
            self.saved[row['file']]=(name,digest(p))
        return row['observations']


def review_video(source,output,*,start=0,seconds=20,workers=2,ppp_card_bank=None):
    out=Path(output);need(not out.exists() and not out.is_symlink() and out.parent.is_dir(),'New output directory required')
    if ppp_card_bank is None:first=scan(source,start,seconds,workers=workers)
    else:
        from plo5_ppp_card_reader import PPPCardReader
        bank_hash=digest(ppp_card_bank);reader_cards=PPPCardReader(ppp_card_bank)
        first=scan(source,start,seconds,workers=workers,card_reader=reader_cards)
        need(digest(ppp_card_bank)==bank_hash,'Card bank changed');first['ppp_card_bank_sha256']=bank_hash
    changes=first['evidence']['display_changes'];need(len(changes)<=100,'Too many changes; use a shorter window')
    wanted={c[k] for c in changes for k in ('before_file','after_file')}
    segments=first['evidence']['card_segments'];need(len(segments)<=100,'Too many card segments; use a shorter window')
    wanted.update(c['first_file'] for c in segments)
    with tempfile.TemporaryDirectory(prefix='.plo5-',dir=out.parent) as temp:
        stage=Path(temp)/'report';stage.mkdir();reader=EvidenceReader(first,wanted,stage)
        if wanted:
            second=scan(source,start,seconds,reader=reader)
            need(second['source_sha256']==first['source_sha256'] and [(f['pts'],f['rgb_sha256']) for f in second['frames']]==[(f['pts'],f['rgb_sha256']) for f in first['frames']],'Source or timestamp mismatch')
        need(set(reader.saved)==wanted,'Missing selected evidence')
        for row in first['frames']:
            if row['file'] in reader.saved:row['file'],row['sha256']=reader.saved[row['file']]
        # Recompute references after replacing logical IDs with real PNG names.
        from plo5_reconstruction_candidates import collect
        first['evidence']=collect(first['frames']);first['png_evidence_written']=bool(wanted)
        first['selective_png_count']=len(wanted);first['evidence_rgb_reextracted']=bool(wanted)
        m=stage/'manifest.json';m.write_text(json.dumps(first,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        html,stats=visual_session(m,source);(stage/'index.html').write_text(html,encoding='utf-8')
        need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return dict(stats,selected_pngs=len(wanted),sampled_frames=len(first['frames']),report=str(out/'index.html'))


def review_models(source,output,cache,*,native=None,rank=None):
    out=Path(output);need(out.suffix.lower()=='.html' and not out.exists() and not out.is_symlink(),'New HTML required')
    d,_=read_json(source);need(set(d)=={'decisions'},'Expected decisions list')
    if rank:
        from plo5_rank_worker import RankWorker
        with RankWorker(rank) as w:rows=review_batch(cache,d['decisions'],cfr_executable=native,rank_worker=w)
    else:rows=review_batch(cache,d['decisions'],cfr_executable=native)
    with out.open('x',encoding='utf-8') as f:f.write(model_page(rows))
    return dict(decisions=len(rows),cache_hits=sum(x['result']['cache_hit'] for x in rows),report=str(out),gto_solution=False)


def preflight():
    import importlib.util
    checks={n:shutil.which(n) is not None for n in ('ffmpeg','ffprobe','tesseract')}
    checks.update(python=sys.version_info>=(3,11),pillow=importlib.util.find_spec('PIL') is not None,tkinter=importlib.util.find_spec('tkinter') is not None)
    return dict(checks=checks,visual_ready=all(checks[n] for n in ('ffmpeg','ffprobe','tesseract','python','pillow')),windows_certified=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    sub.add_parser('check');h=sub.add_parser('history');h.add_argument('source');h.add_argument('output');v=sub.add_parser('video');v.add_argument('source');v.add_argument('output');v.add_argument('--start',type=int,default=0);v.add_argument('--seconds',type=int,default=20);v.add_argument('--workers',type=int,choices=(1,2,3),default=2);v.add_argument('--ppp-card-bank')
    m=sub.add_parser('models');m.add_argument('source');m.add_argument('output');m.add_argument('--cache',required=True);m.add_argument('--native');m.add_argument('--rank')
    a=p.parse_args(argv)
    if a.mode=='check':r=preflight()
    elif a.mode=='history':
        from plo5_history_intake import report
        r=report(a.source,a.output)
    elif a.mode=='video':r=review_video(a.source,a.output,start=a.start,seconds=a.seconds,workers=a.workers,ppp_card_bank=a.ppp_card_bank)
    else:r=review_models(a.source,a.output,a.cache,native=a.native,rank=a.rank)
    print(json.dumps(r,ensure_ascii=True));return 0 if a.mode!='check' or r['visual_ready'] else 1

if __name__=='__main__':raise SystemExit(main())
