"""Read money candidates on bound dense windows; never turn deltas into ledger entries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
import re
import hashlib
import io
import subprocess
import tempfile
from PIL import Image, ImageOps
from offline_jobs import OfflineJobStore
from offline_video_ingest_probe import sha256
from plo5_visual_calibration import load_job, read_money
from plo5_dense_timeline import timeline, extract
from plo5_result_candidates import parse_result
from plo5_context_candidates import parse_amount
from ocr_probe import parse_tesseract_tsv
from plo5_session_export import load, write
from plo5_leak_review import need


def bound_window(job, path):
    p=Path(path);r,rh=load(p);b,_,m=load_job(job['database'],job['job_id']);ann,ah=load(job['annotations'])
    need(r['variant']==5 and r['job_id']==b['job_id'] and r['source_sha256']==b['source_sha256'] and r['sparse_manifest_sha256']==b['reports']['evidence/ingest/manifest.json'] and r['annotation_sha256']==ah,'Window identity mismatch')
    need(all(r[k] is False for k in ('hands_reconstructed','actions_verified','video_verified','equity_ev_authorized','automatic_clip_selection_authorized')),'Invalid window confidence')
    updated=timeline(r['observations']);need(all(r[k]==v for k,v in updated.items()),'Timeline differs from recomputed candidates')
    source=Path(OfflineJobStore(job['database']).get(job['job_id'])['source_path']);size=(m['media']['width'],m['media']['height'])
    # Re-extract the bounded window and compare the actual source JPEGs, not merely a supplied hash list.
    with tempfile.TemporaryDirectory(prefix='plo5-money-') as tmp:
        new=extract(source,r['start'],r['seconds'],Path(tmp),size)
        need(new==r['frames'],'Source frame audit mismatch')
    frames={f['file']:f for f in r['frames']};regions={t['table_id']:t for t in m['regions']};seen=set();paths={}
    for o in r['observations']:
        name=o['file'];sf=o['source_frame'];t=o['table_id'];key=(sf,t)
        need(re.fullmatch(r'table_\d{2}_\d{3}\.png',name) and sf in frames and t in regions and key not in seen,'Invalid crop identity')
        f=frames[sf];need(re.fullmatch(r'frame_\d{3}\.jpg',sf) and o['source_frame_sha256']==f['sha256'] and o['pts']==f['pts'],'Frame binding mismatch');seen.add(key)
        crop=p.parent/name;jpeg=p.parent/sf
        need(all(x.is_file() and not x.is_symlink() for x in (crop,jpeg)) and sha256(crop)==o['sha256'] and sha256(jpeg)==f['sha256'],'Media hash mismatch')
        reg=regions[t];x,y,w,h=(reg[k] for k in ('x','y','width','height'))
        with Image.open(jpeg) as im,Image.open(crop) as c:need(c.size==(w,h) and c.convert('RGB').tobytes()==im.crop((x,y,x+w,y+h)).convert('RGB').tobytes(),'Crop pixels mismatch')
        paths[name]=crop
    need(seen=={(f,t) for f in frames for t in regions},'Incomplete crop roster')
    return r,rh,b,paths


def gold_mask(image):
    """Experimental 402x748 Hero stack crop: suppress neutral white nameplate."""
    need(image.size==(402,748),'Unsupported gold stack layout')
    roi=image.crop((166,642,237,656)).convert('RGB');gray=Image.new('L',roi.size)
    pixels=roi.get_flattened_data() if hasattr(roi,'get_flattened_data') else roi.getdata()
    gray.putdata([max(0,min(255,min(r,g)-b+max(0,min(r,g)-50)//3)) if r-b>9 and g-b>7 else 0 for r,g,b in pixels])
    mask=ImageOps.invert(ImageOps.autocontrast(gray)).resize((roi.width*6,roi.height*6),Image.Resampling.LANCZOS)
    return roi,ImageOps.expand(mask,border=24,fill=255)


def read_gold_stack(image):
    roi,mask=gold_mask(image);stream=io.BytesIO();mask.save(stream,format='PNG')
    p=subprocess.run(['tesseract','stdin','stdout','--psm','7','tsv'],input=stream.getvalue(),capture_output=True,timeout=15,check=True)
    need(len(p.stdout)<=65536,'OCR output exceeds budget')
    raw,n,conf=parse_tesseract_tsv(p.stdout.decode('utf-8'));candidate=parse_amount(raw) if conf is not None and conf>=.85 else None
    if candidate is not None and candidate['unit']!='BB':candidate=None
    return {'raw':raw,'word_count':n,'engine_confidence':conf,'candidate':candidate,'roi':[166,642,71,14],'roi_rgb_sha256':hashlib.sha256(roi.tobytes()).hexdigest(),'human_confirmed':False,'method':'gold_text_experimental_6x'}


def amount(reading):
    c=reading.get('candidate') if reading else None
    if c is None:return None
    need(type(c) is dict and c.get('unit') in ('BB','chips'),'Invalid money candidate')
    if c['unit']!='BB':return None
    v=c['value'];need(type(v) is str and re.fullmatch(r'\d{1,9}(?:\.\d{1,2})?',v),'Invalid decimal candidate')
    return v


def deltas(segment, readings):
    out=[];last=None
    for frame in segment['frames']:
        row=readings[frame['file']]
        if last is not None:
            d={}
            for field in ('pot','stack'):
                a,b=last[field+'_bb'],row[field+'_bb']
                if a is not None and b is not None and Decimal(a)!=Decimal(b):d[field+'_delta_bb']=str(Decimal(b)-Decimal(a))
            if d:out.append({'before_file':last['file'],'after_file':row['file'],'before_pts':last['pts'],'after_pts':row['pts'],**d,'financial_event_verified':False,'kind':'unresolved_display_change'})
        last=row
    return out


def run(job,path,output,workers=2):
    need(type(workers) is int and 1<=workers<=3,'Invalid OCR worker count')
    out=Path(output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required');r,rh,b,paths=bound_window(job,path)
    def scan(o):
        p=paths[o['file']];result={'file':o['file'],'table_id':o['table_id'],'pts':o['pts'],'crop_sha256':o['sha256'],'pot_reading':None,'stack_reading':None,'result_label_candidate':None}
        if o['visible'] is True:
            with Image.open(p) as img:
                im=img.convert('RGB');result['pot_reading']=read_money(im,'pot');result['stack_reading']=read_gold_stack(im) if im.size==(402,748) else read_money(im,'stack')
            a=o.get('action_reading') or {};conf=a.get('engine_confidence');result['result_label_candidate']=parse_result(a.get('raw')) if conf is not None and conf>=.85 else None
        for f in ('pot','stack'):result[f+'_bb']=amount(result[f+'_reading'])
        return result
    with ThreadPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(scan,r['observations']))
    idx={x['file']:x for x in rows};changes=[{'segment_id':s['segment_id'],'table_id':s['table_id'],'changes':deltas(s,idx),'financial_result_bb':None} for s in r['segments']]
    need(load(path)[1]==rh and load_job(job['database'],job['job_id'])[0]==b and load(job['annotations'])[1]==r['annotation_sha256'] and all(sha256(paths[x['file']])==x['crop_sha256'] for x in rows),'Inputs changed during OCR')
    report={'variant':5,'status':'DISPLAY_CANDIDATES_ONLY','job_id':r['job_id'],'source_sha256':r['source_sha256'],'timeline_sha256':rh,'observations':rows,'segments':changes,'samples':len(rows),'pot_candidates':sum(x['pot_bb'] is not None for x in rows),'stack_candidates':sum(x['stack_bb'] is not None for x in rows),'unresolved_changes':sum(len(x['changes']) for x in changes),'result_label_candidates':sum(x['result_label_candidate'] is not None for x in rows),'financial_results_confirmed':0,'financial_result_verified':False,'ev_loss_bb':None,'automatic_clip_selection_authorized':False}
    write(out,report);return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('job_json');p.add_argument('timeline');p.add_argument('output');p.add_argument('--workers',type=int,default=2);a=p.parse_args(argv);r=run(load(a.job_json)[0],a.timeline,a.output,a.workers);print({k:v for k,v in r.items() if k not in ('observations','segments')},flush=True);return 0


if __name__=='__main__':raise SystemExit(main())
