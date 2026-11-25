"""Offline PLO5 Suprema layout candidates; local labeled crops, no verified actions."""
import hashlib
import io
import json
import subprocess
from pathlib import Path
from statistics import median
from PIL import Image, ImageOps
from plo5_card_candidates import glyph, summarize, RANKS, SUITS
from plo5_ingest_job import read_bound_evidence
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest
from plo5_session_export import load, write
from plo5_leak_review import need

# Pixel coordinates in the two calibrated table crops, not general layout discovery.
LAYOUTS = {
    (402,748): {'hero_x':(241,259,277,294,312),'hero_y':585,'board_x':(70,125,179,233,287),'board_y':270,'hero_w':16,'hero_rank_h':17,'hero_suit_h':12,'board_w':20,'board_rank_h':24,'board_suit_h':14,'pot':(168,249,235,267),'stack':(165,640,239,657),'action':(181,611,224,627)},
    (432,800): {'hero_x':(257,277,296,315,334),'hero_y':625,'board_x':(74,132,190,248,306),'board_y':287,'hero_w':17,'hero_rank_h':19,'hero_suit_h':13,'board_w':21,'board_rank_h':25,'board_suit_h':15,'pot':(177,265,253,283),'stack':(175,685,255,702),'action':(192,653,236,670)},
}

def pixels(image):
    return image.get_flattened_data() if hasattr(image,'get_flattened_data') else image.getdata()


def present(image):
    w,h=image.size
    # Felt color at fixed interior patches, not a recognition of active/dealt seats.
    hits=0
    for x,y in ((.25,.43),(.75,.43),(.30,.52),(.70,.52),(.30,.66),(.70,.66)):
        x,y=round(x*w),round(y*h)
        p=list(pixels(image.crop((x-3,y-3,x+4,y+4)).convert('RGB')))
        r,g,b=(median(c[i] for c in p) for i in range(3))
        hits+=b>=g+7 and g>=r+5 and 25<=b<=145
    return True if hits>=4 else False if hits==0 else None


def signature(im):
    g=im.convert('L');hist=g.histogram();total=sum(hist)
    def quantile(q):
        s=0
        for i,n in enumerate(hist):
            s+=n
            if s>=q*total:return i
        return 255
    lo,hi=quantile(.12),quantile(.85)
    if hi-lo<19:return None
    norm=g.point(lambda v:max(0,min(255,round((v-lo)*255/(hi-lo)))))
    return glyph(norm)


def color(im):
    # Four-color deck: corroborate hue using the darkest ink pixels, relative to local brightness.
    rgb=list(pixels(im.convert('RGB')));levels=sorted(max(p) for p in rgb)
    cutoff=levels[len(levels)//2];votes={s:0 for s in SUITS}
    for r,g,b in rgb:
        if max(r,g,b)>cutoff:continue
        m=max(r,g,b);n=min(r,g,b)
        if m-n<=max(8,.17*m):
            if m<=cutoff*.75:votes['s']+=1
        elif r>=g+7 and r>=b+7:votes['h']+=1
        elif g>=r+5 and g>=b+5:votes['c']+=1
        elif b>=r+7 and b>=g+7:votes['d']+=1
    ranked=sorted(votes,key=votes.get,reverse=True)
    return ranked[0] if votes[ranked[0]]>=3 and votes[ranked[0]]>=2*votes[ranked[1]] else None


def slot(image,field,i):
    p=LAYOUTS[image.size];x=p[field+'_x'][i];y=p[field+'_y'];w=p[field+'_w'];rh=p[field+'_rank_h'];sh=p[field+'_suit_h']
    rank=image.crop((x+2,y+2,x+w,y+rh))
    suit=image.crop((x+2,y+rh,x+w,y+rh+sh))
    # Background strip near the right edge, below the small symbol, above any large pip.
    bg=image.crop((x+2,y+2,x+w,y+rh+sh)).convert('RGB')
    neutral=sum(max(c)-min(c)<=18 and min(c)>=47 for c in pixels(bg))/(bg.width*bg.height)
    blue=sum(c[2]>=c[1]+7 and c[1]>=c[0]+5 and c[2]<145 for c in pixels(bg))/(bg.width*bg.height)
    state='face' if neutral>=.39 else 'empty' if blue>=.75 else 'uncertain'
    return state,signature(rank),signature(suit),color(suit)


def distance(a,b):return sum(x!=y for x,y in zip(a,b))/max(1,sum(x or y for x,y in zip(a,b)))


def nearest(g,examples,threshold=.34,margin=.045):
    if g is None or len(examples)<2:return None
    scores=sorted((min(distance(g,v) for v in masks),k) for k,masks in examples.items())
    return scores[0][1] if scores[0][0]<=threshold and scores[1][0]-scores[0][0]>=margin else None


def train(images):
    """Manually labeled training crops only. No labels inferred from predictions."""
    bank={'rank':{},'suit':{}}
    for im,truth in images:
        need(im.size in LAYOUTS,'Unsupported layout')
        for field in ('hero','board'):
            if field not in truth:continue
            cards=truth[field];need(type(cards) is list and len(cards) in ((5,) if field=='hero' else (0,3,4,5)) and all(type(c) is str and len(c)==2 and c[0] in RANKS and c[1] in SUITS for c in cards),'Invalid manual cards')
            need(len(set(cards))==len(cards),'Duplicate manual cards')
            for i,c in enumerate(cards):
                state,r,s,col=slot(im,field,i)
                if state!='face' or r is None or s is None:continue
                for key,label,g in [('rank',c[0],r),('suit',c[1],s)]:
                    bucket=bank[key].setdefault(label,[])
                    if g not in bucket and len(bucket)<128:bucket.append(g)
    return bank


def observe(image,bank,*,slot_reader=None):
    if slot_reader is None:slot_reader=slot
    need(image.size in LAYOUTS,'Unsupported layout')
    visible=present(image);out={'visible':visible,'hero_cards':None,'board_cards':None,'hero_slots':[],'board_slots':[],'cards_verified':False}
    if visible is not True:return out
    for field in ('hero','board'):
        for i in range(5):
            state,r,s,col=slot_reader(image,field,i);rank=nearest(r,bank['rank']) if state=='face' else None;suit=nearest(s,bank['suit']) if state=='face' else None
            token=rank+suit if rank and suit and col==suit else None
            out[field+'_slots'].append({'card':token,'status':'candidate_unverified' if token else 'no_face_candidate' if state=='empty' else 'uncertain_face','rank':rank,'suit':suit,'color_suit':col})
    out.update(summarize(out['hero_slots'],out['board_slots']));return out


def read_money(image,field):
    from plo5_context_candidates import read_roi
    need(field in ('pot','stack'),'Unknown amount field')
    x,y,x2,y2=LAYOUTS[image.size][field]
    if field=='pot':return read_roi(image,[x,y,x2-x,y2-y],field,.75)
    # Remove nameplate borders; select a high-contrast bright-text mask from training only.
    from plo5_context_candidates import parse_amount
    from ocr_probe import parse_tesseract_tsv
    roi=image.crop((x+4,y+2,x2-4,y2-2));gray=ImageOps.autocontrast(roi.convert('L'))
    gray=gray.resize((gray.width*4,gray.height*4),Image.Resampling.LANCZOS).point(lambda v:255 if v>=145 else 0)
    stream=io.BytesIO();gray.save(stream,format='PNG')
    p=subprocess.run(['tesseract','stdin','stdout','--psm','7','tsv'],input=stream.getvalue(),capture_output=True,timeout=15,check=True)
    need(len(p.stdout)<=65536,'OCR output exceeds limit')
    raw,n,conf=parse_tesseract_tsv(p.stdout.decode('utf-8'));value=parse_amount(raw) if conf is not None and conf>=.85 else None
    if value is not None and value['unit']!='BB':value=None
    return {'raw':raw,'word_count':n,'engine_confidence':conf,'candidate':value,'roi':[x+4,y+2,x2-x-8,y2-y-4],'roi_rgb_sha256':hashlib.sha256(roi.tobytes()).hexdigest(),'human_confirmed':False,'method':'narrow_binary_text_4x'}


def load_job(database,job_id):
    binding=read_bound_evidence(database,job_id);job=OfflineJobStore(database).get(job_id);folder=Path(job['result_path']).parent/'evidence/ingest';manifest=read_manifest(folder/'manifest.json')
    return binding,folder,manifest


def checked_image(folder,s):
    p=folder/s['file'];raw=p.read_bytes();need(hashlib.sha256(raw).hexdigest()==s['sha256'],'Crop changed')
    with Image.open(io.BytesIO(raw)) as im:return im.convert('RGB')


def evaluate_jobs(jobs, output):
    """Bind training/holdout labels to audited crops; keep all data local."""
    from plo5_ground_truth import score, UNKNOWN
    from plo5_context_candidates import as_bb
    from plo5_action_candidates import read_action
    from collections import defaultdict, Counter
    from fractions import Fraction
    need(type(jobs) is list and 1<=len(jobs)<=8,'Expected 1–8 job specifications')
    out=Path(output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    train_rows=[];evaluations=[];inputs=[];seen_ids=set();partitions={};snapshots=[]
    for job in jobs:
        need(type(job) is dict and set(job)=={'database','job_id','annotations'},'Invalid job specification')
        b,folder,m=load_job(job['database'],job['job_id']);need(b['job_id'] not in seen_ids,'Repeated job');seen_ids.add(b['job_id'])
        ann,ah=load(job['annotations']);need(type(ann) is dict and set(ann)=={'variant','job_id','source_sha256','manifest_sha256','reference_kind','rows'} and type(ann['variant']) is int and ann['variant']==5 and ann['job_id']==b['job_id'] and ann['source_sha256']==b['source_sha256'] and ann['manifest_sha256']==b['reports']['evidence/ingest/manifest.json'] and ann['reference_kind'] in ('assistant_visual_transcription','synthetic_fixture','human_declared'),'Invalid annotation identity')
        ss={s['file']:s for s in m['samples']};seen=set();labeled={};need(type(ann['rows']) is list and 0<len(ann['rows'])<=len(ss),'Invalid annotation roster')
        for row in ann['rows']:
            need(type(row) is dict and set(row)=={'file','sha256','partition','truth'} and row['file'] in ss and row['file'] not in seen and row['sha256']==ss[row['file']]['sha256'] and row['partition'] in ('train','holdout'),'Invalid label binding')
            s=ss[row['file']];seen.add(row['file']);truth=row['truth'];need(type(truth) is dict and set(truth)<={'visible','hero','board','pot','stack','action'} and type(truth.get('visible')) is bool,'Invalid truth')
            need(truth['visible'] or set(truth)=={'visible'},'Do not label hidden table cards')
            cards=[]
            for f in ('hero','board'):
                if f in truth:
                    v=truth[f];need(type(v) is list and len(v) in ((5,) if f=='hero' else (0,3,4,5)) and all(type(c) is str and len(c)==2 and c[0] in RANKS and c[1] in SUITS for c in v),'Invalid cards');cards+=v
            need(len(cards)==len(set(cards)),'Conflicting reference cards')
            for f in ('pot','stack'):
                if f in truth:
                    from plo5_context_candidates import parse_amount
                    need(type(truth[f]) is str and parse_amount(truth[f]+' BB') is not None,'Invalid money truth')
            if 'action' in truth:need(truth['action'] in ('fold','check','call','bet','raise','all_in',None),'Invalid action truth')
            # Reject exact crop leakage; also reserve later timestamps for holdout per job.
            key=s['sha256'];need(key not in partitions or partitions[key]==row['partition'],'Training/holdout crop overlap');partitions[key]=row['partition']
            labeled[row['file']]=row
            if row['partition']=='train':train_rows.append((checked_image(folder,s),truth))
        train_pts=[ss[k]['actual_frame_timestamp_seconds'] for k,r in labeled.items() if r['partition']=='train'];hold_pts=[ss[k]['actual_frame_timestamp_seconds'] for k,r in labeled.items() if r['partition']=='holdout']
        need(train_pts and hold_pts and max(train_pts)<min(hold_pts),'Use a chronological holdout after calibration')
        evaluations.append((b,folder,m,labeled));snapshots.append((job,ah,b));inputs.append({'job_id':b['job_id'],'source_sha256':b['source_sha256'],'annotation_sha256':ah,'reference_kind':ann['reference_kind'],'training_frames':len(train_pts),'holdout_frames':len(hold_pts)})
    bank=train(train_rows);need(set(bank['rank'])==set(RANKS) and set(bank['suit'])==set(SUITS),'Training examples missing rank/suit classes')
    reports=[]
    for b,folder,m,labeled in evaluations:
        metrics=defaultdict(list);errors=[];money=defaultdict(list);observations=[];coverage=Counter()
        for s in m['samples']:
            im=checked_image(folder,s);p=observe(im,bank);row=labeled.get(s['file']);pred={'visible':p['visible'],'hero':p['hero_cards'],'board':p['board_cards']}
            for field in pred:coverage[field]+=pred[field] is not None
            obs={'file':s['file'],'sha256':s['sha256'],'table_id':s['table_id'],'pts':s['actual_frame_timestamp_seconds'],**p}
            if row and row['partition']=='holdout':
                for field,v in row['truth'].items():
                    if field in ('pot','stack'):
                        reading=read_money(im,field) if p['visible'] is True else None;obs[field+'_reading']=reading
                        pred[field]=as_bb(reading['candidate'],None) if reading else None
                    elif field=='action':
                        x,y,x2,y2=LAYOUTS[im.size]['action'];reading=read_action(im,[x,y,x2-x,y2-y],.75) if p['visible'] is True else None;obs['action_reading']=reading
                        pred[field]=reading['candidate']['action'] if reading and reading['candidate'] else UNKNOWN
                        if reading and reading['status']=='uniform_blank_candidate':pred[field]=None
                    guess=pred.get(field,UNKNOWN)
                    if field!='action' and guess is None:guess=UNKNOWN
                    if field=='hero':v=tuple(sorted(v));guess=tuple(sorted(guess)) if guess is not UNKNOWN else UNKNOWN
                    if field=='board':v=tuple(v);guess=tuple(guess) if guess is not UNKNOWN else UNKNOWN
                    if field in ('pot','stack'):
                        v=Fraction(v);guess=Fraction(guess) if guess is not UNKNOWN else UNKNOWN
                        if guess is not UNKNOWN:money[field].append(abs(v-guess))
                    metrics[field].append((v,guess))
                    if guess is UNKNOWN or v!=guess:errors.append({'file':s['file'],'field':field,'type':'abstention' if guess is UNKNOWN else 'mismatch'})
                # Per-slot measurements include only explicitly labeled cards, not guessed blanks.
                for field in ('hero','board'):
                    if field in row['truth']:
                        for i,v in enumerate(row['truth'][field]):
                            slots=p[field+'_slots'];guess=slots[i]['card'] if len(slots)>i else None
                            metrics[field+'_card'].append((v,guess if guess is not None else UNKNOWN))
            observations.append(obs)
        reports.append({'job_id':b['job_id'],'source_sha256':b['source_sha256'],'manifest_sha256':b['reports']['evidence/ingest/manifest.json'],'samples_processed':len(observations),'candidate_coverage':dict(coverage),'holdout_metrics':{f:score(metrics[f]) for f in sorted(metrics)},'money_errors_bb':{f:{'compared':len(vals),'mae':float(sum(vals)/len(vals)),'max':float(max(vals))} for f,vals in money.items() if vals},'errors':errors,'observations':observations})
    for job,ah,b in snapshots:need(load(job['annotations'])[1]==ah and read_bound_evidence(job['database'],job['job_id'])==b,'Inputs changed during calibration')
    result={'variant':5,'status':'PROTOTYPE_VISUAL_CANDIDATES','inputs':inputs,'template_counts':{f:{k:len(v) for k,v in g.items()} for f,g in bank.items()},'reports':reports,'independent_human_reference_verified':False,'real_session_validated':False,'cards_verified':False,'hands_reconstructed':False,'equity_ev_authorized':False,'automatic_clip_selection_authorized':False}
    write(out,result);return result


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('jobs_json');p.add_argument('output');a=p.parse_args(argv)
    jobs,_=load(a.jobs_json);evaluate_jobs(jobs,a.output);return 0


if __name__=='__main__':raise SystemExit(main())
