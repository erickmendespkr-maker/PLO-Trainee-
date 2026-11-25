"""Offline PLO5 monetary and positional candidates bound to audited job crops."""
import argparse
import hashlib
import io
import json
import math
from decimal import Decimal, localcontext
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageOps
from ocr_probe import parse_tesseract_tsv
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest, unique_pairs
from offline_video_ingest_probe import sha256, require
from plo5_ingest_job import read_bound_evidence
from plo5_card_candidates import box, overlap

NUMBER = r'\d{1,9}(?:[.,]\d{1,2})?'
UNIT = r'BB|chips|fichas'
POSITIONS = {2: ('BTN/SB','BB'), 3: ('BTN','SB','BB'),
             4: ('BTN','SB','BB','CO'), 5: ('BTN','SB','BB','EP','CO'),
             6: ('BTN','SB','BB','EP','MP','CO')}


def decimal_text(value):
    return format(value.normalize(), 'f') if value else '0'


def parse_amount(text):
    """Explicit units only; reject ambiguous separators, signs and guessed zero."""
    match = re.fullmatch(rf'({NUMBER})\s*({UNIT})', text.strip(), re.I)
    if not match:
        return None
    return {'value':decimal_text(Decimal(match[1].replace(',','.'))),
            'unit':'BB' if match[2].upper()=='BB' else 'chips'}


def parse_blinds(text):
    match = re.fullmatch(rf'({NUMBER})\s*/\s*({NUMBER})\s*({UNIT})', text.strip(), re.I)
    if not match:
        return None
    sb, bb = (Decimal(match[i].replace(',','.')) for i in (1,2))
    unit = 'BB' if match[3].upper()=='BB' else 'chips'
    if not 0 < sb < bb or (unit=='BB' and bb != 1):
        return None
    return {'sb':decimal_text(sb),'bb':decimal_text(bb),'unit':unit}


def as_bb(amount, blinds):
    if amount is None:
        return None
    value = Decimal(amount['value'])
    if amount['unit']=='BB':
        return decimal_text(value)
    if not blinds or blinds['unit']!='chips':
        return None
    with localcontext() as ctx:
        ctx.prec=28
        return decimal_text((value/Decimal(blinds['bb'])).quantize(Decimal('0.000001')))


def position_map(seats, dealer):
    """Conditional on declared dealt-in clockwise seats and a valid dealer marker."""
    require(type(seats) is list and 2 <= len(seats) <= 6 and len(set(seats))==len(seats), 'Invalid seat order')
    if dealer not in seats:
        return None
    i=seats.index(dealer)
    return dict(zip(seats[i:]+seats[:i],POSITIONS[len(seats)]))


def validate_profile(profile, regions):
    require(type(profile) is dict and set(profile)=={'variant','tables'} and type(profile['variant']) is int and profile['variant']==5,'PLO5 profile required')
    known={r['table_id']:r for r in regions}
    require(type(profile['tables']) is list and len(profile['tables'])==len(known),'One profile per region required')
    result={}
    for t in profile['tables']:
        require(type(t) is dict and set(t)=={'table_id','hero_seat','seats','pot','blinds'},'Invalid table profile')
        tid=t['table_id']
        require(type(tid) is int and tid in known and tid not in result,'Invalid table ID')
        require(type(t['seats']) is list and 2<=len(t['seats'])<=6,'Expected 2–6 declared dealt-in seats')
        r=known[tid]; size=(r['width'],r['height']); rects=[]; ids=[]
        for s in t['seats']:
            require(type(s) is dict and set(s)=={'seat','stack','bet','dealer'},'Invalid seat profile')
            require(type(s['seat']) is int and 1<=s['seat']<=6 and s['seat'] not in ids,'Invalid or repeated seat')
            ids.append(s['seat'])
            rects.extend(box(s[k],*size) for k in ('stack','bet','dealer'))
        require(type(t['hero_seat']) is int and t['hero_seat'] in ids,'Invalid hero seat')
        rects.extend(box(t[k],*size) for k in ('pot','blinds'))
        require(not any(overlap(a,b) for i,a in enumerate(rects) for b in rects[:i]),'Overlapping OCR regions')
        result[tid]=t
    return result


def read_roi(image, rect, field, threshold):
    roi=image.crop(box(rect,*image.size))
    digest=hashlib.sha256(roi.tobytes()).hexdigest()
    gray=roi.convert('L')
    lo,hi=gray.getextrema()
    if field=='dealer' and hi-lo<=12:
        return {'raw':'','word_count':0,'engine_confidence':None,'candidate':None,
                'roi':rect,'roi_rgb_sha256':digest,'uniform_blank_candidate':True,'human_confirmed':False}
    gray=ImageOps.autocontrast(gray)
    gray=gray.resize((gray.width*2,gray.height*2),Image.Resampling.LANCZOS)
    stream=io.BytesIO(); gray.save(stream,format='PNG')
    p=subprocess.run(['tesseract','stdin','stdout','--psm','7','tsv'],input=stream.getvalue(),capture_output=True,timeout=15,check=True)
    require(len(p.stdout)<=65536,'OCR output exceeds limit')
    raw,count,confidence=parse_tesseract_tsv(p.stdout.decode('utf-8'))
    value=None
    if confidence is not None and confidence>=threshold:
        if field=='dealer':
            value='dealer_marker' if raw.strip().upper() in ('D','BTN') else None
        elif field=='blinds':
            value=parse_blinds(raw)
        else:
            value=parse_amount(raw)
    return {'raw':raw,'word_count':count,'engine_confidence':confidence,'candidate':value,
            'roi':rect,'roi_rgb_sha256':digest,'uniform_blank_candidate':False,'human_confirmed':False}


def derive(table, pot, blinds, seats):
    """Remaining-stack pairwise minimum, not initial stack or all-in amount to call."""
    b=blinds['candidate']
    markers=[s['seat'] for s in seats if s['dealer']['candidate']=='dealer_marker']
    # Any unreadable nonblank competing marker invalidates positional inference.
    clear=all(s['dealer']['candidate']=='dealer_marker' or s['dealer'].get('uniform_blank_candidate') is True for s in seats)
    positions=position_map([s['seat'] for s in seats],markers[0]) if len(markers)==1 and clear else None
    remaining={s['seat']:as_bb(s['stack']['candidate'],b) for s in seats}
    hero=remaining[table['hero_seat']]
    pairs=[{'opponent_seat':seat,'remaining_effective_bb':decimal_text(min(Decimal(hero),Decimal(value)))
            if hero is not None and value is not None else None} for seat,value in remaining.items() if seat!=table['hero_seat']]
    return {'pot_bb':as_bb(pot['candidate'],b),'positions_candidate':positions,
            'hero_position_candidate':positions[table['hero_seat']] if positions else None,
            'remaining_stacks_bb':remaining,'pairwise_remaining_effective_bb':pairs,
            'visible_bets_bb':{s['seat']:as_bb(s['bet']['candidate'],b) for s in seats},
            'initial_effective_stack_bb':None,'amount_to_call_bb':None,'rake':None,
            'position_assumption':'declared clockwise dealt-in seats, not verified active players',
            'human_confirmed':False}


def analyze_job(database, job_id, profile_path, *, threshold=.75, max_tasks=1024):
    require(type(threshold) in (int,float) and math.isfinite(threshold) and 0<=threshold<=1,'Invalid OCR threshold')
    require(type(max_tasks) is int and 1<=max_tasks<=4096,'Invalid OCR task budget')
    binding=read_bound_evidence(database,job_id)
    job=OfflineJobStore(database).get(job_id)
    folder=Path(job['result_path']).parent/'evidence/ingest'
    p=Path(profile_path)
    require(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32768,'Unsafe context profile')
    raw=p.read_bytes(); profile=json.loads(raw,object_pairs_hook=unique_pairs)
    manifest=read_manifest(folder/'manifest.json'); tables=validate_profile(profile,manifest['regions'])
    tasks=sum(2+3*len(tables[s['table_id']]['seats']) for s in manifest['samples'])
    require(tasks<=max_tasks,'OCR task budget exceeded; use bounded evidence batches')
    observations=[]
    for s in manifest['samples']:
        data=(folder/s['file']).read_bytes()
        require(hashlib.sha256(data).hexdigest()==s['sha256'],'Crop changed during OCR')
        with Image.open(io.BytesIO(data)) as im:
            image=im.convert('RGB')
        t=tables[s['table_id']]
        pot,blinds=(read_roi(image,t[k],k,threshold) for k in ('pot','blinds'))
        seats=[{'seat':seat['seat'],**{k:read_roi(image,seat[k],k,threshold) for k in ('stack','bet','dealer')}} for seat in t['seats']]
        observations.append({'table_id':s['table_id'],'pts':s['actual_frame_timestamp_seconds'],'file':s['file'],
                             'crop_sha256':s['sha256'],'hero_seat_declared':t['hero_seat'],'pot':pot,'blinds':blinds,'seats':seats,
                             'derived_candidates':derive(t,pot,blinds,seats)})
    require(sha256(p)==hashlib.sha256(raw).hexdigest() and read_bound_evidence(database,job_id)==binding,'Inputs changed')
    return {'schema_version':1,'variant':5,'job_id':job_id,'source_sha256':binding['source_sha256'],
            'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],'profile_sha256':hashlib.sha256(raw).hexdigest(),
            'status':'unverified_position_and_money_candidates','ocr_tasks':tasks,'threshold':threshold,'observations':observations,
            'hands_reconstructed':False,'equity_ev_authorized':False,'automatic_clip_selection_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','job_id','profile','output'):
        p.add_argument(name)
    p.add_argument('--threshold',type=float,default=.75)
    p.add_argument('--max-tasks',type=int,default=1024)
    a=p.parse_args(argv); target=Path(a.output)
    require(target.suffix=='.json' and not target.exists() and not target.is_symlink(),'New JSON output required')
    result=analyze_job(a.database,a.job_id,a.profile,threshold=a.threshold,max_tasks=a.max_tasks)
    with target.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
