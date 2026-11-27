"""Offline exact-PTS extraction for selected errors. Semantic binding remains upstream.
No action inferred from a display label; no OCR in the extraction pass.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from threading import Timer
from PIL import Image
from plo5_pre_gto_context import need
from plo5_selective_review import select, street_filter, identity, evidence_request, hash_ok, VERSION, STREETS
from plo5_video_stream import digest, roster, SIZE, FRAME_BYTES
from plo5_mixed_money import STARTS

MAX_REQUESTS=512


def stamp(v):
    need(type(v) is str and len(v)<=64 and re.fullmatch(r'[0-9]+(?:/[1-9][0-9]*)?',v) is not None,'Exact rational timestamp required')
    p=Fraction(v);need(p<=10**8,'Timestamp exceeds budget');return p


def frame_index(manifest):
    need(type(manifest) is dict and manifest.get('variant')==5 and hash_ok(manifest.get('source_sha256')),'Invalid source manifest')
    rows=manifest.get('frames');need(type(rows) is list and len(rows)<=100000,'Frame budget exceeded')
    frames={};prev=None
    for f in rows:
        p=stamp(f['pts']);need(prev is None or p>prev,'Duplicate or unordered frame timestamps');prev=p
        need(hash_ok(f.get('rgb_sha256')),'Missing frame RGB digest')
        frames[p]=f
    return frames


def active_table(frame,table):
    rows=[r for r in frame['observations'] if r['table_id']==table]
    need(len(rows)==2 and {r['field'] for r in rows}=={'pot','stack'},'Missing table observations')
    need(all(r.get('layout_candidate_active') is True and r.get('platform') in ('pppoker','suprema') for r in rows) and len({r['platform'] for r in rows})==1,'Table not active in manifest')
    return rows[0]['platform']


def bind(manifest,decision,pts,table,phase,*,index=None):
    """Bind an explicitly supplied decision anchor; not semantic proof of action."""
    hand,ident=identity(decision);p=stamp(pts)
    frames=frame_index(manifest) if index is None else index
    need(p in frames,'Timestamp absent from recognition manifest')
    need(type(table) is int and 1<=table<=4,'Invalid table');f=frames[p];active_table(f,table)
    # When complete candidate board is present, reject a mismatched street.
    for c in f.get('cards',[]):
        if c['table_id']==table and c.get('board_cards') is not None:
            board=c['board_cards']
            if type(board) is list and len(board) in (0,3,4,5) and all(type(x) is str for x in board):
                need(len(board)=={'preflop':0,'flop':3,'turn':4,'river':5}[decision['street']],'Candidate board street mismatch')
    e=dict(source_sha256=manifest['source_sha256'],rgb_sha256=f['rgb_sha256'],pts=str(p),table_id=table,phase=phase,hand_id=hand,decision_id=ident,street=decision['street'])
    evidence_request(dict(decision,evidence=e));return e


def anchor_candidates(manifest, intervals):
    """Suggest before/after anchors for visible Hero label changes only.
    Intervals come from existing temporal inspection; never assign hand IDs.
    """
    frames=frame_index(manifest);out=[];ordered=list(frames);successor=dict(zip(ordered,ordered[1:]))
    need(type(intervals) is list and len(intervals)<=100000,'Interval budget')
    for r in intervals:
        pair=r.get('label_changes',{}).get('hero_bottom')
        if r.get('status') not in ('CONSISTENT_DISPLAY_DELTAS','UNCHANGED_DISPLAYS') or not pair or len(pair)!=2 or pair[0]==pair[1] or pair[1] not in ('fold','check','call','bet','raise','all_in'):continue
        a,b=stamp(r['before_pts']),stamp(r['after_pts']);t=r['table_id']
        need(successor.get(a)==b and 0<b-a<=Fraction(3,2),'Unbound temporal interval')
        need(active_table(frames[a],t)==active_table(frames[b],t),'Platform mismatch')
        out.append(dict(table_id=t,before_pts=str(a),after_pts=str(b),label=pair[1],before_rgb_sha256=frames[a]['rgb_sha256'],after_rgb_sha256=frames[b]['rgb_sha256'],action_verified=False,decision_identity_verified=False))
    return out


def temporal_anchors(manifest):
    """Run the existing seat/temporal pipeline on the supplied structured frames."""
    from plo5_temporal_evidence import inspect
    r=inspect(manifest['frames'])
    return dict(status='CANDIDATE_ANCHORS_ONLY',source_sha256=manifest['source_sha256'],anchors=anchor_candidates(manifest,r['intervals']),actions_verified=False)


def groups(points):
    batch=[]
    for p in sorted(points):
        if batch and (p-batch[0]>15 or len(batch)>=32):yield batch;batch=[]
        batch.append(p)
    if batch:yield batch


def decode(source,points,expected,consume,timeout):
    start=max(0,int(points[0])-1);seconds=int(points[-1])-start+2
    tb,known,_=roster(source,start,seconds)
    ticks=[p/tb for p in points]
    need(all(v.denominator==1 and 0<=v<2**53 and int(v) in known for v in ticks),'Requested PTS absent from source roster')
    ticks=list(map(int,ticks));expression='+'.join(f'eq(pts,{v})' for v in ticks)
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','info','-threads','1','-filter_threads','1','-ss',str(start),'-t',str(seconds+1),'-copyts','-i',str(source),'-map','0:v:0','-vf',f"select='{expression}',showinfo",'-frames:v',str(len(points)),'-fps_mode','passthrough','-pix_fmt','rgb24','-c:v','rawvideo','-threads:v','1','-an','-sn','-dn','-f','rawvideo','pipe:1']
    with tempfile.TemporaryFile() as log:
        with subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=log) as p:
            timer=Timer(timeout,p.kill);timer.daemon=True;timer.start()
            try:
                for pts in points:
                    raw=p.stdout.read(FRAME_BYTES);need(len(raw)==FRAME_BYTES,'Missing requested frame')
                    need(hashlib.sha256(raw).hexdigest()==expected[pts],'Requested RGB hash mismatch')
                    consume(pts,Image.frombytes('RGB',SIZE,raw))
                need(p.stdout.read(1)==b'' and p.wait()==0,'Extraction failed')
            finally:
                timer.cancel();timer.join()
                if p.poll() is None:p.kill()
                p.wait()
        need(log.tell()<=8*1024**2,'Log budget exceeded');log.seek(0);logs=log.read().decode('utf-8')
    bases=re.findall(r'config in time_base: (\d+/\d+)',logs)
    observed=[(int(n),int(v)) for n,v in re.findall(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:',logs)]
    need(bases and all(Fraction(x)==tb for x in bases) and observed==list(enumerate(ticks)),'Decoded timestamp mismatch')


def capture(source,manifest,records,output,streets=STREETS,*,timeout=120):
    """Recompute selection; only eligible requests yield crops. Stage before publish."""
    source=Path(source);out=Path(output)
    need(source.is_file() and not source.is_symlink() and source.suffix.lower()=='.mp4','Local MP4 required')
    need(not out.exists() and not out.is_symlink() and out.parent.is_dir(),'New output directory required')
    need(type(timeout) is int and 1<=timeout<=300,'Invalid timeout')
    frames=frame_index(manifest);selection=select(records,street_filter(streets));requests=selection['print_requests']
    need(len(requests)<=MAX_REQUESTS,'Split into batches of at most 512 requests')
    source_hash=digest(source);need(source_hash==manifest['source_sha256'],'Source hash mismatch')
    wanted=defaultdict(set);expected={};by_key={}
    for e in requests:
        p=stamp(e['pts']);t=e['table_id'];ref=bind(manifest,e,e['pts'],t,e['phase'],index=frames)
        need(all(e[k]==v for k,v in ref.items()),'Reference does not match manifest')
        wanted[p].add(t);expected[p]=e['rgb_sha256']
    with tempfile.TemporaryDirectory(prefix='.plo17-',dir=out.parent) as tmp:
        stage=Path(tmp)/'prints';stage.mkdir();total_bytes=0
        def consume(p,im):
            nonlocal total_bytes
            for t in sorted(wanted[p]):
                x=STARTS[t-1];right=STARTS[t] if t<4 else SIZE[0]
                name=f'frame_{len(by_key)+1:05d}_table_{t}.png';path=stage/name
                im.crop((x,0,right,SIZE[1])).save(path,format='PNG');total_bytes+=path.stat().st_size
                need(total_bytes<=512*1024**2,'Print storage budget exceeded')
                by_key[p,t]=dict(file=name,png_sha256=digest(path),crop=[x,0,right,SIZE[1]])
        batches=0
        for batch in groups(wanted):decode(source,batch,expected,consume,timeout);batches+=1
        need(digest(source)==source_hash,'Source changed during extraction')
        error_index={(e['hand_id'],e['decision_id']):e for e in selection['errors']}
        rows=[dict(e,error=error_index[e['hand_id'],e['decision_id']],**by_key[stamp(e['pts']),e['table_id']],status='EXACT_FRAME_CROP',semantic_binding_verified=False) for e in requests]
        result=dict(version='plo5-error-prints-v1',source_sha256=source_hash,streets=selection['streets'],selected_errors=len(selection['errors']),adequate_count=selection['adequate_count'],unresolved_count=len(selection['unresolved']),missing_references=sum(e['evidence'] is None for e in selection['errors']),errors=selection['errors'],unresolved=selection['unresolved'],decision_prints=rows,unique_frames=len(wanted),unique_crops=len(by_key),decode_batches=batches,png_bytes=total_bytes,certificates_independently_verified=False,semantic_binding_verified=False)
        (stage/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return result


def read(path):
    p=Path(path);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32*1024**2,'Invalid JSON input');return json.loads(p.read_text('utf-8'))


def main(argv=None):
    import sys
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv[:1]==['anchors']:
        p=argparse.ArgumentParser(description='Candidate temporal anchors');p.add_argument('manifest');p.add_argument('output');a=p.parse_args(argv[1:]);out=Path(a.output)
        need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON required')
        r=temporal_anchors(read(a.manifest))
        with out.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,allow_nan=False,indent=2)
        return 0
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video');p.add_argument('manifest');p.add_argument('decisions');p.add_argument('output');p.add_argument('--streets',nargs='+',choices=STREETS,default=list(STREETS));a=p.parse_args(argv)
    d=read(a.decisions);need(type(d) is dict and set(d)=={'version','decisions'} and d['version']==VERSION,'Invalid decision contract')
    r=capture(a.video,read(a.manifest),d['decisions'],a.output,a.streets);print(json.dumps({k:v for k,v in r.items() if k not in ('decision_prints','errors','unresolved')}));return 0

if __name__=='__main__':raise SystemExit(main())
