"""Refine coarse PLO5 boundary brackets using targeted offline source samples."""
import argparse, hashlib, json, re, subprocess, tempfile
from fractions import Fraction
from pathlib import Path
from PIL import Image
from plo5_event_capture import probe, need, digest
from plo5_card_review import CardReader
from plo5_fourcolor_cards import load_bank
from plo5_suprema_soft import load_bank as load_soft
from plo5_seat_candidates import observe
from plo5_hand_boundaries import analyze, snapshot
from plo5_mixed_money import STARTS


def refine(samples, old, new, hz):
    """Require two consecutive samples for each endpoint; no hand certification."""
    runs=[];previous=None;gaps=[];seen_new=False;reversed_order=False
    for pts,state in samples:
        pts=Fraction(pts)
        if previous is not None and pts<=previous:raise ValueError('Unordered samples')
        adjacent=previous is not None and int(pts*hz)-int(previous*hz)==1 and pts-previous<=Fraction(2,hz)
        label='old' if state==old else 'new' if state==new else 'unknown'
        if previous is not None and not adjacent:gaps.append((previous,pts))
        if label=='new':seen_new=True
        if label=='old' and seen_new:reversed_order=True
        if adjacent and runs[-1]['label']==label:
            runs[-1]['last']=str(pts);runs[-1]['samples']+=1
        else:runs.append({'label':label,'first':str(pts),'last':str(pts),'samples':1})
        previous=pts
    # A reversal invalidates the two-state interpretation.
    # Unknown samples may contain additional hands, so only narrow the visual bracket.
    supported=[r for r in runs if r['label']!='unknown' and r['samples']>=2]
    a=[r for r in supported if r['label']=='old'];b=[r for r in supported if r['label']=='new']
    out={'runs':runs,'last_old':None,'first_new':None,'width_seconds':None,'boundary_verified':False,'hand_verified':False}
    if a and b and not reversed_order and Fraction(a[-1]['last'])<Fraction(b[0]['first']):
        u,v=Fraction(a[-1]['last']),Fraction(b[0]['first'])
        if not any(u<=left<right<=v for left,right in gaps):out.update(last_old=str(u),first_new=str(v),width_seconds=float(v-u))
    return out


def scan(source,start,seconds,hz,table,reader):
    tb,buckets=probe(source,start,seconds,hz);size=1504*696*3;rows=[]
    vf=f"select='gte(t,{start})*lt(t,{start+seconds})*(isnan(prev_selected_t)+gt(floor(t*{hz}),floor(prev_selected_t*{hz})))',showinfo"
    args=['ffmpeg','-nostdin','-hide_banner','-loglevel','info','-threads','1','-filter_threads','1','-ss',str(start),'-t',str(seconds+1),'-copyts','-i',str(source),'-map','0:v:0','-vf',vf,'-frames:v',str(len(buckets)),'-fps_mode','passthrough','-pix_fmt','rgb24','-c:v','rawvideo','-threads:v','1','-an','-sn','-dn','-f','rawvideo','pipe:1']
    with tempfile.TemporaryFile() as log:
        p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=log)
        try:
            for stamp in buckets.values():
                raw=p.stdout.read(size);need(len(raw)==size,'Incomplete frame')
                full=Image.frombytes('RGB',(1504,696),raw);x=STARTS[table-1];im=Image.new('RGB',full.size);im.paste(full.crop((x,0,x+372,696)),(x,0))
                c=reader.scan(im)[table-1];s=observe(im,table,c);rows.append((stamp*tb,snapshot(c,s)))
            need(not p.stdout.read(1) and p.wait(timeout=30)==0,'Decode failed')
        finally:
            if p.poll() is None:p.kill();p.wait()
            p.stdout.close()
        log.seek(0);txt=log.read().decode();stamps=[(int(i),int(t)) for i,t in re.findall(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:',txt)];bases=re.findall(r'config in time_base: (\d+/\d+)',txt)
        need(bases and all(Fraction(x)==tb for x in bases) and stamps==list(enumerate(buckets.values())),'PTS roster mismatch')
    return rows


def run(source,report,ppp,soft,hz=4):
    need(type(hz) is int and 2<=hz<=8,'Invalid rate');source=Path(source);p=Path(report)/'manifest.json';need(source.is_file() and not source.is_symlink() and source.suffix.lower()=='.mp4','Invalid source');need(p.is_file() and not p.is_symlink() and p.stat().st_size<32*2**20,'Invalid manifest')
    raw=p.read_bytes();m=json.loads(raw);h=digest(source);ph=digest(ppp);sh=digest(soft)
    need(m['variant']==5 and m['status']=='MIXED_LAYOUT_DISPLAY_REVIEW_ONLY' and m['source_sha256']==h and m['card_bank_sha256']==ph and m['suprema_soft_bank_sha256']==sh,'Source or bank mismatch')
    a=analyze(m['frames']);need(len(a['possible_new_hand_intervals'])<=32,'Too many intervals');runs={r['run_id']:r for r in a['runs']};reader=CardReader(load_bank(ppp),suprema_soft_bank=load_soft(soft));out=[]
    for q in a['possible_new_hand_intervals']:
        old=runs[q['before_run']]['state'];new=runs[q['after_run']]['state'];u=Fraction(q['last_old_state']['pts']);v=Fraction(q['first_new_state']['pts']);start=max(m['start'],int(u)-1);end=min(m['start']+m['seconds'],int(v)+2)
        need(2<=end-start<=19,'Invalid bracket window');rows=scan(source,start,end-start,hz,q['table_id'],reader);r=refine(rows,old,new,hz)
        # Never report a wider bracket as an improvement.
        if r['width_seconds'] is not None and (Fraction(r['last_old'])<u or Fraction(r['first_new'])>v or r['width_seconds']>=float(v-u)):r.update(last_old=None,first_new=None,width_seconds=None)
        out.append({'table_id':q['table_id'],'coarse_before':str(u),'coarse_after':str(v),'coarse_width_seconds':float(v-u),'samples':len(rows),**r})
    need(digest(source)==h and digest(ppp)==ph and digest(soft)==sh and p.read_bytes()==raw,'Input changed')
    return {'variant':5,'status':'REFINED_VISUAL_BRACKETS_ONLY','source_sha256':h,'manifest_sha256':hashlib.sha256(raw).hexdigest(),'sampling_hz':hz,'rows':out,'hands_reconstructed':False,'boundaries_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('report');p.add_argument('output');p.add_argument('--card-bank',required=True);p.add_argument('--suprema-soft-bank',required=True);p.add_argument('--hz',type=int,default=4);a=p.parse_args(argv);r=run(a.source,a.report,a.card_bank,a.suprema_soft_bank,a.hz)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
