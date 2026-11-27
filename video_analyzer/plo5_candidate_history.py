"""Assemble offline visual PLO5 histories without inventing actions or settlement."""
import argparse, hashlib, io, json
from fractions import Fraction
from pathlib import Path
from PIL import Image
from plo5_hand_boundaries import analyze
from plo5_preflop_roster import candidates as roster_candidates
from plo5_opponent_labels import load_bank, observe as opponents, need
from plo5_hero_actions import observe as hero
from plo5_blind_evidence import Reader


def plan(frames):
    transitions=analyze(frames)
    groups=[];by_run={};by_sample={}
    incoming={e['after_run']:e for e in transitions['transitions']
              if e['transition_candidate']=='street_advance' and e['repeated_both_sides']}
    for r in transitions['runs']:
        t=r['table_id'];i=r['run_id'];edge=incoming.get(i)
        g=by_run.get(edge['before_run']) if edge else None
        if g is None:
            g={'history_id':len(groups)+1,'table_id':t,'platform':r['state']['platform'],
               'hero_cards_candidate':r['state']['hero_cards'],'dealer_candidate':r['state']['dealer'],
               'runs':[],'observations':[],'hand_verified':False,'complete_hand':False,
               'financial_result_verified':False,'strategy_authorized':False}
            groups.append(g)
        g['runs'].append(r);by_run[i]=g
        first,last=map(Fraction,(r['first']['pts'],r['last']['pts']))
        for f in frames:
            if first<=Fraction(f['pts'])<=last:
                key=(t,f['file']);need(key not in by_sample,'Overlapping states');by_sample[key]=(g,r)
    return transitions,groups,by_sample


def run(root,bank_path):
    root=Path(root);p=root/'manifest.json';need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32*2**20,'Invalid manifest')
    raw=p.read_bytes();m=json.loads(raw);need(m['variant']==5 and m['status']=='MIXED_LAYOUT_DISPLAY_REVIEW_ONLY','Wrong manifest')
    frames=m['frames'];need(0<len(frames)<=120,'Invalid frame count')
    bh=hashlib.sha256(Path(bank_path).read_bytes()).hexdigest();bank=load_bank(bank_path)
    transitions,groups,index=plan(frames);reader=Reader();unknown=[]
    rosters=roster_candidates(frames)
    for f in frames:
        name=f['file'];q=root/'prints'/name;need(Path(name).name==name and q.is_file() and not q.is_symlink() and not q.parent.is_symlink() and q.stat().st_size<=8*2**20,'Invalid print')
        data=q.read_bytes();need(hashlib.sha256(data).hexdigest()==f['sha256'],'Print hash mismatch')
        with Image.open(io.BytesIO(data)) as im:
            need(im.size==(1504,696),'Wrong geometry');im=im.convert('RGB')
        for t in range(1,5):
            item=index.get((t,name));ref={'file':name,'pts':f['pts'],'sha256':f['sha256']}
            if item is None:
                unknown.append({'table_id':t,**ref,'reason':'NO_COMPLETE_VISUAL_STATE'});continue
            g,r=item;state=r['state'];k=state['platform'];h=hero(im,t);o=opponents(im,t,bank)
            need(h['platform']==o['platform']==k and h['table_id']==o['table_id']==t,'Platform mismatch')
            # Stakes reader calibrated primarily on preflop; abstain elsewhere.
            s=reader.scan(im,t) if state['street']=='preflop' else None
            if s is not None:need(s['platform']==k and s['table_id']==t,'Stake mismatch')
            values={q['seat']:q['value_bb'] for q in s['stakes']} if s else {}
            labels=[{'seat':'hero_bottom','visible_label_candidate':h['hero_action_candidate'],'label_kind':'action' if h['hero_action_candidate'] is not None else None}]+o['opponents']
            for l in labels:
                l.update(displayed_stake_bb_candidate=values.get(l['seat']),action_amount_bb=None,action_street=None,action_verified=False)
            matching=[q for q in rosters if q['table_id']==t and q['platform']==k and q['hero_cards']==state['hero_cards'] and q['dealer']==state['dealer'] and state['street']=='preflop' and Fraction(q['first']['pts'])<=Fraction(f['pts'])<=Fraction(q['last']['pts'])]
            need(len(matching)<=1,'Ambiguous roster')
            position=matching[0]['positions_if_standard_blinds_and_full_roster'] if matching else None
            money=[q for q in f['observations'] if q['table_id']==t and q['platform']==k and q['field'] in ('stack','pot')]
            need(len(money)==2 and {q['field'] for q in money}=={'stack','pot'},'Financial observation mismatch')
            g['observations'].append({**ref,'run_id':r['run_id'],'observed_street_candidate':state['street'],'board_candidate':state['board'],'labels':labels,'displayed_money_candidates':{q['field']:q['value_bb'] for q in money},'stakes_scanned':s is not None,'conditional_positions':position,'positions_verified':False})
    need(p.read_bytes()==raw and hashlib.sha256(Path(bank_path).read_bytes()).hexdigest()==bh,'Input changed')
    return {'variant':5,'status':'PARTIAL_VISUAL_HISTORIES_ONLY','source_sha256':m['source_sha256'],'manifest_sha256':hashlib.sha256(raw).hexdigest(),'opponent_bank_sha256':bh,'histories':groups,'unassigned_observations':unknown,'boundary_evidence':transitions,'stake_cache':reader.cache.stats(),'actions_verified':False,'hands_reconstructed':False,'financial_result_verified':False,'strategy_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('bank');p.add_argument('output');a=p.parse_args(argv);r=run(a.report,a.bank)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
