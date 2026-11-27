"""Offline display increases: review candidates, never inferred cash transfers."""
import argparse, hashlib, io, json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from PIL import Image
from plo5_balance_review import money, fmt, need
from plo5_mixed_money import read, detect, REGIONS
from plo5_card_review import valid
from plo5_seat_candidates import SEATS


def adjacent(a,b):
    return int(b//1)-int(a//1)==1 and 0<b-a<=Fraction(3,2)


def observation(f,t):
    rows=[r for r in f['observations'] if r['table_id']==t]
    need(len(rows)==2 and {r['field'] for r in rows}=={'stack','pot'},'Invalid money roster')
    s,p=sorted(rows,key=lambda r:r['field'],reverse=True)
    c=f['cards'][t-1];q=f['seats'][t-1];k=s['platform']
    need(c['table_id']==q['table_id']==t,'Invalid table binding')
    if k not in REGIONS or not k==p['platform']==c['platform']==q['platform'] or s['value_bb'] is None or s.get('layout_candidate_active') is not True or s.get('financial_result_verified') is not False:return None
    stack=money(s['value_bb']);pot=None if p['value_bb'] is None else money(p['value_bb'])
    b=c['board_cards'];d=q['dealer_seat_candidate']
    return {'file':f['file'],'pts':f['pts'],'sha256':f['sha256'],'platform':k,'stack':fmt(stack),'pot':None if pot is None else fmt(pot),'board':b if valid(b,(0,3,4,5)) else None,'dealer':d if d in SEATS else None}


def analyze(frames,target=None):
    if target is not None:need(money(target)>0,'Invalid target')
    seen=set();previous=None;active={};pairs=[]
    for f in frames:
        pts=Fraction(f['pts']);name=f['file'];need(name not in seen and (previous is None or pts>previous),'Unordered samples');seen.add(name)
        if previous is None or not adjacent(previous,pts):active.clear()
        previous=pts
        for t in range(1,5):
            o=observation(f,t);old=active.pop(t,None)
            if o is None:continue
            if old is not None and old['last']['platform']==o['platform']:
                if old['last']['stack']==o['stack']:
                    old['previous']=old['last'];old['last']=o;old['count']+=1;active[t]=old;continue
                if money(o['stack'])>money(old['last']['stack']):
                    pair={'table_id':t,'before':old['last'],'before_peer':old['previous'],'after':o,'after_peer':None,'before_count':old['count'],'target_bb':target}
                    pairs.append(pair)
            active[t]={'last':o,'previous':None,'count':1}
            # Pair confirmation is filled in a second pass only on consecutive frames.
    byfile={f['file']:i for i,f in enumerate(frames)}
    for r in pairs:
        i=byfile[r['after']['file']];a,b=r['before'],r['after'];t=r['table_id']
        if i+1<len(frames):
            peer=observation(frames[i+1],t)
            if peer and adjacent(Fraction(b['pts']),Fraction(peer['pts'])) and (peer['platform'],peer['stack'])==(b['platform'],b['stack']):r['after_peer']=peer
        stable=r['before_count']>=2 and r['after_peer'] is not None
        reset=bool(a['board'] and b['board']==[] and a['dealer'] and b['dealer'] and a['dealer']!=b['dealer'])
        hit=target is not None and money(b['stack'])==money(target)
        r.update(repeated_both_sides=stable,board_reset_and_dealer_change_candidate=reset,target_match=hit,display_increase_bb=fmt(money(b['stack'])-money(a['stack'])),status='REVIEW_TOP_UP_COMPATIBLE' if stable and reset and hit else 'UNRESOLVED_DISPLAY_INCREASE',rebuy_verified=False,return_verified=False,payout_verified=False,external_transfer_bb=None,conditional_net_bb=None,financial_result_verified=False)
    return pairs


def run(root,target=None):
    root=Path(root);p=root/'manifest.json';need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32*2**20,'Invalid manifest');raw=p.read_bytes();m=json.loads(raw)
    need(m['variant']==5 and m['status']=='MIXED_LAYOUT_DISPLAY_REVIEW_ONLY' and 0<len(m['frames'])<=120,'Wrong manifest')
    rows=analyze(m['frames'],target);checked=0
    for r in rows:
        t=r['table_id'];ok=True
        for key in ('before_peer','before','after','after_peer'):
            o=r[key]
            if o is None:ok=False;continue
            name=o['file'];q=root/'prints'/name;need(Path(name).name==name and q.is_file() and not q.is_symlink() and not q.parent.is_symlink() and q.stat().st_size<=8*2**20,'Invalid print');data=q.read_bytes();need(hashlib.sha256(data).hexdigest()==o['sha256'],'Print hash mismatch')
            with Image.open(io.BytesIO(data)) as im:
                k=detect(im,t);v=read(im,t,k,'stack')['value_bb'] if k==o['platform'] else None
            checked+=1;ok=ok and v is not None and money(v)==money(o['stack'])
        r['stack_reread_agrees']=ok
        if not ok:r['status']='UNRESOLVED_DISPLAY_INCREASE'
    need(p.read_bytes()==raw,'Manifest changed')
    return {'variant':5,'status':'STACK_INCREASE_REVIEW_ONLY','source_sha256':m['source_sha256'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),'target_bb':target,'rows':rows,'stack_rereads':checked,'financial_results_verified':False,'confirmed_rebuys':0,'confirmed_returns':0}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('output');p.add_argument('--target-bb');a=p.parse_args(argv);r=run(a.report,a.target_bb)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
