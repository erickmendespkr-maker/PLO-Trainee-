"""Offline review of recorded 1504x696 PLO5 display amounts, not hand results."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from fractions import Fraction
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from PIL import Image
from plo5_mixed_money import STARTS, REGIONS, detect, read
from plo5_singleflight import SingleFlight


def need(ok,message):
    if not ok: raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def command(args):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=120,check=True)
    need(len(p.stdout)+len(p.stderr)<=32*1024**2,'Media log budget exceeded')
    return p


def extract(source,start,seconds,folder):
    need(type(start) is int and start>=0 and type(seconds) is int and 2<=seconds<=120,'Invalid window')
    probe=json.loads(command(['ffprobe','-v','error','-select_streams','v:0','-read_intervals',f'{start}%{start+seconds+1}','-show_entries','stream=time_base,width,height:frame=best_effort_timestamp','-of','json',str(source)]).stdout)
    stream=probe['streams'][0];need((stream['width'],stream['height'])==(1504,696),'Unsupported recording geometry')
    tb=Fraction(stream['time_base']);known={int(r['best_effort_timestamp']) for r in probe['frames'] if 'best_effort_timestamp' in r}
    expected=sorted({int((t*tb)//1) for t in known if start<=t*tb<start+seconds});need(expected,'No source frames in window')
    p=command(['ffmpeg','-nostdin','-hide_banner','-loglevel','info','-threads','1','-filter_threads','1','-ss',str(start),'-t',str(seconds+1),'-copyts','-i',str(source),'-map','0:v:0','-vf',f"select='lt(t,{start+seconds})*(isnan(prev_selected_t)+gt(floor(t),floor(prev_selected_t)))',showinfo",'-frames:v',str(len(expected)),'-fps_mode','passthrough','-c:v','png','-threads:v','1','-an','-sn','-dn','-n',str(folder/'frame_%05d.png')])
    bases=re.findall(r'config in time_base: (\d+/\d+)',p.stderr);need(bases and all(Fraction(x)==tb for x in bases),'PTS time base mismatch')
    logs=[(int(n),int(t)) for n,t in re.findall(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:',p.stderr)]
    files=sorted(folder.glob('frame_*.png'));need(len(files)==len(logs)==len(expected),'Incomplete frame extraction')
    stamps=logs;need([n for n,t in stamps]==list(range(len(expected))) and all(t in known for n,t in stamps),'Unbound frame PTS')
    need([int((t*tb)//1) for n,t in stamps]==expected,'Sample roster mismatch')
    return [(p,t*tb) for p,(_,t) in zip(files,stamps)]


class Reader:
    def __init__(self,capacity=512,workers=3):
        need(type(workers) is int and 1<=workers<=3,'Invalid workers');self.cache=SingleFlight(capacity);self.workers=workers
    def scan(self,image):
        need(image.mode=='RGB' and image.size==(1504,696),'Invalid frame')
        platforms=[detect(image,t) for t in range(1,5)]
        def task(j):
            t,p,f=j
            if p is None:result={'value_bb':None,'raw':'','confidence':None}
            else:
                x=STARTS[t-1];a,b,c,d=REGIONS[p][f];roi=image.crop((x+a,b,x+c,d)).convert('L')
                key=(p,f,roi.size,roi.tobytes())
                result=self.cache.get(key,lambda:read(image,t,p,f))
            return {'table_id':t,'platform':p,'field':f,**result,'layout_candidate_active':p is not None,'financial_result_verified':False}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(task,[(t,p,f) for t,p in enumerate(platforms,1) for f in ('stack','pot')]))


def changes(frames,threshold='30'):
    cutoff=Decimal(threshold);need(cutoff.is_finite() and cutoff>0,'Invalid threshold');last={};rows=[]
    for frame in frames:
        pts=Fraction(frame['pts']);seen=set()
        for obs in frame['observations']:
            if obs['field']!='stack':continue
            tid=obs['table_id'];need(tid not in seen,'Duplicate table');seen.add(tid)
            old=last.pop(tid,None);v=obs['value_bb'];platform=obs['platform']
            if not obs['layout_candidate_active'] or v is None:continue
            value=Decimal(v);need(value.is_finite() and value>=0,'Invalid stack')
            if old is not None and old[0]==platform and int(pts//1)-int(old[1]//1)==1 and 0<pts-old[1]<=Fraction(3,2):
                drop=old[2]-value
                if drop>cutoff:
                    rows.append({'table_id':tid,'platform':platform,'before_file':old[3],'after_file':frame['file'],'before_bb':str(old[2]),'after_bb':str(value),'display_decline_bb':str(drop),'conditional_net_bb':None,'financial_result_verified':False})
            last[tid]=(platform,pts,value,frame['file'])
        need(seen=={1,2,3,4},'Incomplete frame roster')
    return rows


def run(source,output,*,start=0,seconds=60,capacity=512,workers=3,card_bank=None,suprema_card_bank=None,suprema_soft_bank=None,seat_candidates=False):
    need(suprema_card_bank is None or suprema_soft_bank is None,"Conflicting Suprema profiles")
    if seat_candidates:
        from plo5_seat_candidates import observe as observe_seats
    source=Path(source);out=Path(output)
    need(source.suffix.lower()=='.mp4' and source.is_file() and not source.is_symlink(),'Local MP4 required')
    need(out.parent.is_dir() and not out.exists() and not out.is_symlink(),'New output directory required')
    t=time.perf_counter();h=digest(source);reader=Reader(capacity,workers)
    cards=None;bank_hash=None;suprema_hash=None;soft_hash=None
    if card_bank is not None or suprema_card_bank is not None or suprema_soft_bank is not None:
        from plo5_fourcolor_cards import load_bank
        from plo5_card_review import CardReader
        bank_hash=digest(card_bank) if card_bank is not None else None
        suprema_hash=digest(suprema_card_bank) if suprema_card_bank is not None else None
        soft=None
        if suprema_soft_bank is not None:
            from plo5_suprema_soft import load_bank as load_soft
            soft_hash=digest(suprema_soft_bank);soft=load_soft(suprema_soft_bank)
        cards=CardReader(load_bank(card_bank) if card_bank is not None else None,suprema_bank=load_bank(suprema_card_bank) if suprema_card_bank is not None else None,suprema_soft_bank=soft)
    with tempfile.TemporaryDirectory(prefix='.mixed-review-',dir=out.parent) as tmp:
        stage=Path(tmp)/'package';stage.mkdir();media=stage/'prints';media.mkdir()
        a=time.perf_counter();samples=extract(source,start,seconds,media);extract_s=time.perf_counter()-a
        frames=[];a=time.perf_counter();card_seconds=0.
        for p,pts in samples:
            with Image.open(p) as im:rgb=im.convert('RGB')
            obs=reader.scan(rgb);row={'file':p.name,'sha256':digest(p),'pts':str(pts),'observations':obs}
            if cards is not None:
                t0=time.perf_counter();row['cards']=cards.scan(rgb);card_seconds+=time.perf_counter()-t0
            if seat_candidates:
                row['seats']=[observe_seats(rgb,t,row['cards'][t-1] if cards is not None else None) for t in range(1,5)]
            frames.append(row)
        ocr_s=time.perf_counter()-a;priority=changes(frames)
        groups=[]
        if cards is not None:
            from plo5_card_review import segments
            groups=segments(frames)
            if card_bank is not None:need(digest(card_bank)==bank_hash,'Card bank changed')
            if suprema_card_bank is not None:need(digest(suprema_card_bank)==suprema_hash,'Suprema card bank changed')
            if suprema_soft_bank is not None:need(digest(suprema_soft_bank)==soft_hash,'Suprema soft bank changed')
        a=time.perf_counter();need(digest(source)==h and all(digest(media/f['file'])==f['sha256'] for f in frames),'Input or print changed');verify_s=time.perf_counter()-a
        report={'variant':5,'status':'MIXED_LAYOUT_DISPLAY_REVIEW_ONLY','source_sha256':h,'start':start,'seconds':seconds,'sampled_seconds':len(frames),'missing_source_seconds':sorted(set(range(start,start+seconds))-{int(Fraction(f['pts'])//1) for f in frames}),'frames':frames,'priority':priority,'cache':reader.cache.stats(),'stage_seconds':{'extract':extract_s,'recognition':ocr_s,'final_recheck':verify_s},'wall_seconds':time.perf_counter()-t,'hands_reconstructed':False,'financial_result_verified':False,'gto_solution':False,'independent_pixel_reextraction_verified':False}
        if cards is not None:
            report.update(card_bank_sha256=bank_hash,suprema_card_bank_sha256=suprema_hash,suprema_soft_bank_sha256=soft_hash,card_cache=cards.cache.stats(),card_segments=groups,cards_verified=False,card_recognition_seconds=card_seconds)
        if seat_candidates:report.update(positions_verified=False,seat_candidates_enabled=True)
        with (stage/'manifest.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
        page=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>PLO5 — Revisão de valores</title><style>body{font:16px system-ui;max-width:1200px;margin:auto;padding:20px}img{max-width:100%}article{border-top:1px solid #aaa;padding:12px}</style><h1>Revisão de valores PLO5</h1><p>Quedas entre amostras consecutivas, não perdas de mãos. Nenhuma mão, ação ou estratégia foi confirmada.</p>']
        for r in priority:
            page.append(f'<article><h2>Mesa {r["table_id"]}: queda exibida {html.escape(r["display_decline_bb"])} BB</h2><p>Antes: {html.escape(r["before_bb"])} BB; depois: {html.escape(r["after_bb"])} BB.</p><img loading="lazy" src="prints/{r["before_file"]}"><img loading="lazy" src="prints/{r["after_file"]}"></article>')
        if cards is not None:
            page.append('<h2>Grupos de cartas candidatos (PPPoker / Suprema experimental)</h2><p>Não são mãos confirmadas. Leituras incompletas interrompem os grupos.</p>')
            for g in groups:
                page.append(f'<article><h3>Mesa {g["table_id"]} — {html.escape(g["candidate_id"])}</h3><p>Hero: {html.escape(" ".join(g["hero_cards"]))}; board final: {html.escape(" ".join(g["last_board"]))}; amostras: {len(g["observations"])}.</p><a href="prints/{g["observations"][0]["file"]}">Primeiro print</a></article>')
        if seat_candidates:
            page.append('<h2>Dealer e Hero candidatos</h2><p>Assentos visuais, não posições confirmadas.</p><ul>')
            for f in frames:
                for r in f['seats']:
                    if r['platform'] is not None:
                        page.append(f'<li><a href="prints/{f["file"]}">{html.escape(f["pts"])} s</a> — mesa {r["table_id"]}: dealer {html.escape(r["dealer_seat_candidate"] or "incerto")}; Hero {html.escape(r["hero_seat_candidate"] or "incerto")}</li>')
            page.append('</ul>')
        page.append('<h2>Amostras disponíveis</h2><ul>')
        for f in frames:page.append(f'<li><a href="prints/{f["file"]}">{html.escape(f["pts"])} s</a></li>')
        page.append('</ul><p><a href="manifest.json">Dados e hashes</a></p></html>');(stage/'index.html').write_text(''.join(page),encoding='utf-8')
        need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('output');p.add_argument('--start',type=int,default=0);p.add_argument('--seconds',type=int,default=60);p.add_argument('--capacity',type=int,default=512);p.add_argument('--workers',type=int,default=3);p.add_argument('--card-bank');p.add_argument('--suprema-card-bank');p.add_argument('--suprema-soft-bank');p.add_argument('--seat-candidates',action='store_true');a=p.parse_args(argv)
    r=run(a.source,a.output,start=a.start,seconds=a.seconds,capacity=a.capacity,workers=a.workers,card_bank=a.card_bank,suprema_card_bank=a.suprema_card_bank,suprema_soft_bank=a.suprema_soft_bank,seat_candidates=a.seat_candidates);print(json.dumps({k:v for k,v in r.items() if k!='frames'},ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
