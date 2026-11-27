"""Explicit, evidence-bound PLO5 model routing. No verified strategy promotion."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from contextlib import closing, ExitStack
from functools import partial

import plo5_decision_analysis as bridge
from plo5_preflop_context import analyze as preflop
from plo5_stackoff import analyze as stackoff
from plo5_multiway_implied import analyze as multiway
from plo5_river_solver import solve as river
from plo5_ev_comparison import action_key
from plo5_session_export import load, write
from plo5_ingest_job import read_bound_evidence
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest
from offline_video_ingest_probe import sha256
from plo5_leak_review import need


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def amount(value, bb, target):
    return type(value) is int and Fraction(value,bb)==Fraction(target)


def integrate(binding,manifest,drafts,review,dh,edb,sdb,extension,*,trials=2000,seed=0,iterations=10000,river_solver=None,pre_gto_db=None):
    need(type(extension) is dict and set(extension)=={'variant','review_digest','kind','scenario','seat_map'} and type(extension['variant']) is int and extension['variant']==5 and extension['review_digest']==digest(review),'Extension review mismatch')
    kind=extension['kind'];s=extension['scenario'];mapping=extension['seat_map']
    need(kind in ('none','preflop','stackoff','multiway','river','pre_gto') and type(mapping) is dict,'Unknown model extension')
    need(kind=='none' or not review['hypotheses'],'Do not combine distinct model families')
    base=bridge.analyze_review(binding,manifest,drafts,review,dh,edb,sdb,trials=trials,seed=seed)
    result={'variant':5,'review_digest':digest(review),'extension_digest':digest(extension),'base_decision':base,'model_kind':kind,'model_status':'NOT_REQUESTED','extension_result':None,'chosen_conditional_model':None,'frequency':None,'ev_loss_bb':None,'financial_result_bb':None,'gto_solution':False,'video_verified':False,'strategic_error_established':False,'automatic_clip_selection_authorized':False}
    if kind=='none':
        need(s is None and not mapping,'Unexpected extension payload');return result
    if base['status']=='INSUFFICIENT_DATA':
        result['model_status']='INSUFFICIENT_DATA';return result
    need(type(s) is dict and type(s.get('variant')) is int and s['variant']==5,'PLO5 scenario required')
    c=base['context'];a,_=bridge.find_frames(binding,manifest,drafts,review);hero_seat=a['hero_seat_declared'];seats={x['seat'] for x in a['actions']};stacks=a['context']['remaining_stacks_bb'];chosen=action_key(review['chosen_action'])
    def observed(seat):
        value=stacks.get(str(seat),stacks.get(seat));need(value is not None,'Missing observed stack');return value
    need(review['context']['amount_unit']=='chips','Extensions require explicit integer chip unit')
    bb=s.get('bb',s.get('bb_chips'));need(type(bb) is int and bb>0 and Fraction(bb)==Fraction(review['context']['bb_size']),'Chip unit mismatch')
    def common(pot,stack,call,rate,cap):
        need(all(amount(v,bb,c[k]) for v,k in ((pot,'pot'),(stack,'stack'),(call,'to_call'),(cap,'rake_cap'))) and type(rate) is int and Fraction(rate,100)==Fraction(c['rake_percent']),'Monetary context mismatch')
    def cards(h,b):
        need(sorted(h)==c['hero'] and sorted(b[:3])+b[3:]==c['board'],'Card context mismatch')
    if kind=='pre_gto':
        from plo5_pre_gto_review import review_policy
        from plo5_pre_gto_tree import replay,bounds,step
        need(pre_gto_db is not None,'Explicit preflop model database required')
        need(set(s)=={'variant','bb','context','history','hero','chosen','model'},'Invalid preflop policy scenario')
        root=s['context']
        need(type(root) is dict and root.get('variant')==5 and root.get('bb')==bb and root.get('history')==[],'Invalid root context')
        need(c['street']=='preflop' and len(root['stacks'])==c['players'],'Preflop context mismatch')
        cards(s['hero'],[])
        need(set(mapping)==set(root['stacks']) and all(type(x) is int for x in mapping.values()) and len(set(mapping.values()))==len(mapping) and set(mapping.values())==seats and mapping[c['position']]==hero_seat,'Seat map mismatch')
        state=replay(root['stacks'],root['sb'],bb,s['history']);b=bounds(state)
        need(state.actor==c['position'],'Actor mismatch')
        common(state.pot,b['stack'],b['to_call'],root['rake_bps'],root['rake_cap'])
        need(all(amount(v,bb,observed(mapping[p])) for p,v in zip(state.order,state.remaining)),'Replay stack mismatch')
        ch=s['chosen']
        need(type(ch) is dict and set(ch)=={'action','amount'},'Invalid chosen action')
        step(state,state.actor,ch['action'],ch['amount'])
        need((ch['action'],ch['amount']-b['to_call'] if ch['action']=='raise' else 0)==chosen,'Chosen action/sizing mismatch')
        report=review_policy(pre_gto_db,s['model'],root,s['history'],s['hero'],ch,position=state.actor,pot=state.pot,stack=b['stack'],to_call=b['to_call'])
        result['model_status']=report['status']
        if report['status']=='RESTRICTED_POLICY_MATCH':
            result['chosen_conditional_model']={'action':ch['action'],'frequency':report['chosen_frequency'],'ev_bb':report['chosen_ev_bb'],'conditional_ev_loss_bb':report['conditional_ev_loss_bb'],'scope':report['scope']}
    elif kind in ('preflop','stackoff'):
        need(c['street']=='preflop' and s['position']==c['position'] and len(s['stacks'])==c['players'],'Preflop context mismatch');cards(s['hero'],[])
        need(set(mapping)==set(s['stacks']) and all(type(x) is int for x in mapping.values()) and set(mapping.values())==seats and mapping[c['position']]==hero_seat,'Declared seat map mismatch')
        # Calculate descriptive replay first; conditional models remain separate.
        report=(preflop if kind=='preflop' else stackoff)(s,trials=trials,seed=seed)
        remaining=report['remaining_stacks_chips'];common(report['pot_chips'],remaining[c['position']],report['to_call_chips'],s['rake_bps'],s['rake_cap'])
        need(all(amount(remaining[p],bb,observed(seat)) for p,seat in mapping.items()),'Replay stack mismatch')
        ch=s['chosen'];need((ch['action'],ch['amount']-report['to_call_chips'] if ch['action']=='raise' else 0)==chosen,'Chosen action/sizing mismatch')
        result['model_status']=report.get('model_status',report.get('comparison',{}).get('status','NO_MATCH'))
    elif kind=='multiway':
        need(c['street']!='preflop' and c['players']>=3 and chosen[0] in ('fold','call'),'Multiway call/fold context required');cards(s['hero'],s['board'])
        common(s['pot_chips'],s['hero_stack_chips'],s['call_chips'],s['rake_bps'],s['rake_cap_chips'])
        # Index -> seat declaration. Existing common-pot model requires every dealt seat eligible.
        need(set(mapping)=={str(i) for i in range(c['players']-1)} and all(type(x) is int for x in mapping.values()) and set(mapping.values())==seats-{hero_seat} and len(s['ranges'])==len(mapping) and len(s['opponent_stacks_chips'])==len(mapping),'Opponent roster mismatch')
        need(all(amount(v,bb,observed(mapping[str(i)])) for i,v in enumerate(s['opponent_stacks_chips'])),'Opponent stack mismatch')
        report=multiway(s,trials=trials,seed=seed);result['model_status']='CONDITIONAL_MODEL_ONLY'
        result['chosen_conditional_model']={name:{'action':chosen[0],'ev_bb':r['ev_call_bb'] if chosen[0]=='call' else 0,'call_vs_fold':r['conditional_call_vs_fold']} for name,r in report['scenarios'].items()}
    else:
        need(c['street']=='river' and c['players']==2 and chosen[0] in ('check','bet') and Fraction(c['to_call'])==0,'Restricted river context required')
        need(Fraction(c['rake_percent'])==0,'Restricted river solver excludes rake')
        need(set(mapping)=={'opponent'} and type(mapping['opponent']) is int and {mapping['opponent']}==seats-{hero_seat},'Opponent seat mismatch')
        need(sorted(s['board'][:3])+s['board'][3:]==c['board'] and amount(s['pot_chips'],bb,c['pot']) and amount(s['hero_stack_chips'],bb,c['stack']) and amount(s['opponent_stack_chips'],bb,observed(mapping['opponent'])),'River context mismatch')
        need(chosen[0]=='check' or chosen[1]==s['bet_chips'],'Unmodeled bet sizing')
        report=(river if river_solver is None else river_solver)(s,iterations=iterations);rows=[x for x in report['hero_strategy'] if sorted(x['cards'])==c['hero']];need(len(rows)==1,'Hero holding absent from legal range')
        result['model_status']='RESTRICTED_RIVER_GAME_APPROXIMATION';result['chosen_conditional_model']=rows[0]
    result['extension_result']=report
    return result


def run(database,job_id,drafts,review,equity_db,strategy_db,extension,*,river_engine='vanilla',river_cache_path=None,pre_gto_path=None,**options):
    need(river_engine in ('vanilla','cfr-plus') and (river_cache_path is None or river_engine=='cfr-plus'),'Invalid river backend options')
    b=read_bound_evidence(database,job_id);j=OfflineJobStore(database).get(job_id);m=read_manifest(Path(j['result_path']).parent/'evidence/ingest/manifest.json')
    d,dh=load(drafts);r,rh=load(review);e,eh=load(extension)
    need(sha256(equity_db)==bridge.EQUITY_DB_SHA256,'Unreviewed equity snapshot')
    with ExitStack() as stack:
        edb=stack.enter_context(closing(bridge.open_readonly(equity_db,immutable=True)))
        sdb=stack.enter_context(closing(bridge.open_readonly(strategy_db)))
        if river_engine=='cfr-plus' and e['kind']=='river':
            from plo5_river_accelerated import solve as accelerated
            cache=None
            if river_cache_path is not None:
                from plo5_river_cache_open import open_cache
                cache=stack.enter_context(closing(open_cache(river_cache_path,protected=(database,drafts,review,equity_db,strategy_db,extension,j['source_path'],j['result_path']))))
            options['river_solver']=partial(accelerated,cache=cache)
        if e['kind']=='pre_gto':
            need(pre_gto_path is not None,'Preflop database required')
            pdb=stack.enter_context(closing(bridge.open_readonly(pre_gto_path)))
            pdb.execute('BEGIN');options['pre_gto_db']=pdb
        sdb.execute('BEGIN');out=integrate(b,m,d,r,dh,edb,sdb,e,**options)
    need(read_bound_evidence(database,job_id)==b and all(sha256(p)==h for p,h in ((drafts,dh),(review,rh),(extension,eh),(equity_db,bridge.EQUITY_DB_SHA256))),'Inputs changed')
    return {**out,'review_sha256':rh,'extension_sha256':eh,'equity_database_sha256':bridge.EQUITY_DB_SHA256}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('database','job_id','drafts','review','equity_db','strategy_db','extension','output'):p.add_argument(k)
    p.add_argument('--river-engine',choices=('vanilla','cfr-plus'),default='vanilla');p.add_argument('--river-cache');p.add_argument('--pre-gto-db')
    a=p.parse_args(argv);out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    need(a.river_cache is None or Path(a.river_cache).resolve()!=out.resolve(),'Cache and output must be distinct')
    write(out,run(a.database,a.job_id,a.drafts,a.review,a.equity_db,a.strategy_db,a.extension,river_engine=a.river_engine,river_cache_path=a.river_cache,pre_gto_path=a.pre_gto_db));return 0


if __name__=='__main__':raise SystemExit(main())
