"""Offline card agreement on two retained stable event frames; not verified hands."""
import argparse
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import re
from PIL import Image
from plo5_fourcolor_cards import load_bank, observe as ppp_observe, RANKS, SUITS
from plo5_suprema_cards import observe as sup_observe
from plo5_mixed_money import STARTS


def need(ok, message):
    if not ok: raise ValueError(message)


def combine(a,b):
    need(a['platform']==b['platform'] and a['platform'] in ('pppoker','suprema'),'Platform mismatch')
    out={'platform':a['platform'],'cards_verified':False,'hero_cards':None,'board_cards':None}
    for field in ('hero','board'):
        aa,bb=a[field+'_slots'],b[field+'_slots']
        need(len(aa)==len(bb)==5,'Incomplete slots')
        rows=[]
        for x,y in zip(aa,bb):
            u,v=x['card'],y['card'];c=None;status='uncertain'
            if u is not None and u==v and len(u)==2 and u[0] in RANKS and u[1] in SUITS and x['status']==y['status']=='candidate_unverified':
                c=u;status='two_frame_agreement'
            elif u is None and v is None and x['status']==y['status']=='felt_empty_candidate':status='two_frame_empty_candidate'
            rows.append({'card':c,'status':status,'first_card':u,'second_card':v})
        cards=[r['card'] for r in rows if r['card'] is not None]
        if len(set(cards))==len(cards):
            if field=='hero' and len(cards)==5:out['hero_cards']=cards
            if field=='board' and len(cards) in (0,3,4,5) and all(r['card'] for r in rows[:len(cards)]) and all(r['status']=='two_frame_empty_candidate' for r in rows[len(cards):]):out['board_cards']=cards
        out[field+'_slots']=rows
    if out['hero_cards'] is not None and out['board_cards'] is not None and set(out['hero_cards'])&set(out['board_cards']):out['hero_cards']=out['board_cards']=None
    return out


def read_crop(root,entry,event_id,label,t):
    expected=f'prints/{event_id:04}_{label}.png';need(entry['file']==expected,'Unexpected print path')
    p=root/expected;need(p.is_file() and not p.is_symlink() and not p.parent.is_symlink() and p.stat().st_size<=8*1024**2,'Unsafe print')
    raw=p.read_bytes();need(hashlib.sha256(raw).hexdigest()==entry['sha256'],'Print hash mismatch')
    with Image.open(io.BytesIO(raw)) as im:
        need(im.size==(372,696),'Invalid print dimensions');crop=im.convert('RGB')
    full=Image.new('RGB',(1504,696));full.paste(crop,(STARTS[t-1],0));return full


def run(root,banks):
    root=Path(root);p=root/'manifest.json';need(p.is_file() and not p.is_symlink() and p.stat().st_size<=16*1024**2,'Invalid event manifest')
    raw=p.read_bytes();d=json.loads(raw);hz=d['sampling_hz']
    need(d['variant']==5 and d['status']=='PIXEL_CHANGE_CANDIDATES_ONLY' and type(hz) is int and 2<=hz<=12,'Invalid event format')
    need(bool(banks) and set(banks)<={'pppoker','suprema','suprema_soft'} and not {'suprema','suprema_soft'}<=set(banks),'Invalid or conflicting bank profiles')
    models={k:load_bank(v) for k,v in banks.items() if k!='suprema_soft'}
    observers={'pppoker':ppp_observe,'suprema':sup_observe}
    if 'suprema_soft' in banks:
        from plo5_suprema_soft import load_bank as soft_load, observe as soft_observe
        models['suprema']=soft_load(banks['suprema_soft']);observers['suprema']=soft_observe
    hashes={k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in banks.items()};rows=[];seen=set()
    for e in d['events']:
        i,t,k=e['event_id'],e['table_id'],e['platform'];need(type(i) is int and i>0 and i not in seen and type(t) is int and 1<=t<=4,'Invalid event identity');seen.add(i)
        if e['status']!='stable_change_candidate' or k not in models or 'peer' not in e:continue
        a,b=e['after'],e['peer'];u,v=Fraction(a['pts']),Fraction(b['pts'])
        need(abs(a['sample']-b['sample'])==1 and abs(int(u*hz)-int(v*hz))==1 and 0<abs(u-v)<=Fraction(2,hz) and min(u,v)>=d['start'] and max(u,v)<d['start']+d['seconds'],'Noncontiguous peer')
        observer=observers[k]
        x=observer(read_crop(root,a,i,'after',t),t,models[k]);y=observer(read_crop(root,b,i,'peer',t),t,models[k]);need(x['platform']==y['platform']==k,'Detected platform mismatch')
        rows.append({'event_id':i,'table_id':t,'after_pts':str(u),'peer_pts':str(v),'after':x,'peer':y,'rank_profile':'suprema-soft-1504x696-v2' if k=='suprema' and 'suprema_soft' in banks else k+'-v1','agreement':combine(x,y)})
    need(hashlib.sha256(p.read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest(),'Manifest changed')
    need(all(hashlib.sha256(Path(v).read_bytes()).hexdigest()==hashes[k] for k,v in banks.items()),'Bank changed')
    return {'variant':5,'status':'TWO_FRAME_CARD_CANDIDATES_ONLY','source_sha256':d['source_sha256'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),'bank_sha256':hashes,'rows':rows,'cards_verified':False,'hands_reconstructed':False,'strategy_authorized':False,'independent_source_reextraction_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('event_report');p.add_argument('output');p.add_argument('--pppoker-bank');p.add_argument('--suprema-bank');p.add_argument('--suprema-soft-bank');a=p.parse_args(argv)
    banks={k:v for k,v in [('pppoker',a.pppoker_bank),('suprema',a.suprema_bank),('suprema_soft',a.suprema_soft_bank)] if v};need(banks,'At least one bank required');r=run(a.event_report,banks)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps({'pairs':len(r['rows']),'cards_verified':False}));return 0
if __name__=='__main__':raise SystemExit(main())
