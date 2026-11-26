"""Bind offline Hero label candidates to adjacent event prints and card context."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from plo5_event_card_consensus import read_crop, need, combine
from plo5_hero_actions import observe as action_observe
from plo5_fourcolor_cards import load_bank, observe as ppp_observe
from plo5_suprema_soft import load_bank as soft_load, observe as soft_observe
from plo5_blind_evidence import Reader


def adjacent(a,b,hz):
    u,v=Fraction(a['pts']),Fraction(b['pts'])
    return type(a['sample']) is int and type(b['sample']) is int and abs(a['sample']-b['sample'])==1 and abs(int(u*hz)-int(v*hz))==1 and 0<abs(u-v)<=Fraction(2,hz) and (u<v)==(a['sample']<b['sample'])


def label_state(before,after,peer,*,before_bound=True):
    if after is None or after!=peer:return None,'uncertain_pair'
    if not before_bound:return after,'label_without_bound_prior'
    if before==after:return after,'persistent_label_candidate'
    if before is None:return after,'label_seen_after_unreadable_or_absent'
    return after,'different_visible_label_candidate'


def street(agreement):
    if agreement is None or agreement['hero_cards'] is None or agreement['board_cards'] is None:return None
    return {0:'preflop',3:'flop',4:'turn',5:'river'}.get(len(agreement['board_cards']))


def run(root,banks):
    root=Path(root);p=root/'manifest.json'
    need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=16*1024**2,'Invalid event manifest')
    raw=p.read_bytes();d=json.loads(raw);hz=d['sampling_hz'];start=d['start'];end=start+d['seconds']
    need(d['variant']==5 and d['status']=='PIXEL_CHANGE_CANDIDATES_ONLY' and type(hz) is int and 2<=hz<=12,'Invalid event format')
    need(bool(banks) and set(banks)<={'pppoker','suprema_soft'},'Unsupported bank profiles')
    hashes={k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in banks.items()}
    models={('suprema' if k=='suprema_soft' else k):(soft_load(v) if k=='suprema_soft' else load_bank(v)) for k,v in banks.items()}
    readers={'pppoker':ppp_observe,'suprema':soft_observe};stakes=Reader();rows=[];seen=set();skipped=0
    for e in d['events']:
        i,t,k=e['event_id'],e['table_id'],e['platform']
        need(type(i) is int and i>0 and i not in seen and type(t) is int and 1<=t<=4,'Invalid event identity');seen.add(i)
        if e['status']!='stable_change_candidate' or k not in readers or 'peer' not in e:
            skipped+=1;continue
        a,b=e['after'],e['peer'];need(adjacent(a,b,hz),'Noncontiguous stable pair')
        def read(key):
            entry=e[key];need(start<=Fraction(entry['pts'])<end,'Print outside window')
            im=read_crop(root,entry,i,key,t);obs=action_observe(im,t);need(obs['platform']==k,'Platform mismatch');return im,obs
        im,x=read('after');jm,y=read('peer');prior=None;before_bound=False
        if 'before' in e and 'first' in e:
            need(Fraction(e['before']['pts'])<Fraction(e['first']['pts'])<=min(Fraction(a['pts']),Fraction(b['pts'])),'Invalid event order')
            if adjacent(e['before'],e['first'],hz):
                read('first');_,z=read('before');prior=z['hero_action_candidate'];before_bound=True
        label,state=label_state(prior,x['hero_action_candidate'],y['hero_action_candidate'],before_bound=before_bound)
        agreement=None;st=None;amount=None
        if label is not None and k in models:
            agreement=combine(readers[k](im,t,models[k]),readers[k](jm,t,models[k]));st=street(agreement)
            if st=='preflop':
                # Same visible amount in two calibrated reads; not the increment or action size.
                u=stakes.scan(im,t);v=stakes.scan(jm,t)
                def hero(r):return next((q['value_bb'] for q in r['stakes'] if q['seat']=='hero_bottom'),None)
                if hero(u) is not None and hero(u)==hero(v):amount=hero(u)
        rows.append({'event_id':i,'table_id':t,'platform':k,'after':a,'peer':b,'before':e.get('before') if before_bound else None,'before_label':prior,'after_label':x['hero_action_candidate'],'peer_label':y['hero_action_candidate'],'label_candidate':label,'label_state':state,'card_agreement':agreement,'observed_board_street_candidate':st,'action_street':None,'action_amount_bb':None,'displayed_hero_stake_bb_candidate':amount,'action_verified':False,'hand_verified':False,'amount_verified':False,'strategy_authorized':False})
    need(p.read_bytes()==raw,'Manifest changed')
    need(all(hashlib.sha256(Path(v).read_bytes()).hexdigest()==hashes[k] for k,v in banks.items()),'Bank changed')
    return {'variant':5,'status':'EVENT_HERO_LABEL_CONTEXT_CANDIDATES_ONLY','manifest_sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':d['source_sha256'],'bank_sha256':hashes,'rows':rows,'skipped_events':skipped,'actions_verified':False,'hands_reconstructed':False,'strategy_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('output');p.add_argument('--pppoker-bank');p.add_argument('--suprema-soft-bank');a=p.parse_args(argv)
    banks={k:v for k,v in [('pppoker',a.pppoker_bank),('suprema_soft',a.suprema_soft_bank)] if v};r=run(a.report,banks)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    print(json.dumps({'stable_pairs':len(r['rows']),'labels':sum(x['label_candidate'] is not None for x in r['rows']),'actions_verified':False}));return 0
if __name__=='__main__':raise SystemExit(main())
