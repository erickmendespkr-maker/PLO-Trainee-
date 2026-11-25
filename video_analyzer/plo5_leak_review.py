"""Aggregate PLO5 reviewed decision candidates, never certify strategic leaks."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re

from plo5_ev_comparison import action_key
from strategic_normalize import normalize_scenario


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def identifier(v):
    return type(v) is str and 0<len(v)<=256 and bool(v.strip())


def sha(v, n=64):
    return type(v) is str and re.fullmatch('[0-9a-f]{'+str(n)+'}',v) is not None


def number(v):
    need(type(v) in (int,float) and abs(v)<=10**12 and math.isfinite(v),'Invalid report number')
    return v


def span(v):
    need(type(v) is list and len(v)==2,'Expected bounds')
    a,b=map(number,v);need(0<=a<=b,'Invalid loss bounds')
    return a,b


def fraction(v):
    need(type(v) is dict and set(v)=={'numerator','denominator'} and type(v['numerator']) is int and type(v['denominator']) is int and v['denominator']>0,'Invalid fraction')
    return Fraction(v['numerator'],v['denominator'])


def same(a,b):
    return math.isclose(number(a),number(b),rel_tol=1e-10,abs_tol=1e-10)


def bucket(stack):
    s=Fraction(stack)
    return '0_to_under_20' if s<20 else '20_to_under_50' if s<50 else '50_to_under_100' if s<100 else '100_to_under_200' if s<200 else '200_plus'


def model_result(m,chosen):
    need(type(m) is dict and m.get('variant')==5 and m.get('status')=='CONDITIONAL_MODEL_ONLY' and m.get('baseline')=='fold_zero_incremental' and action_key(m['chosen_action_declared'])==chosen,'Incompatible conditional model')
    need(all(m.get(k) is False for k in ('gto_solution','action_observed_verified','strategic_error_established','automatic_clip_selection_authorized','range_or_response_uncertainty_included','span_is_calibrated_confidence_interval')) and all(k in m and m[k] is None for k in ('financial_result_bb','variance_attribution','ev_loss_bb')),'Verified claims not supported')
    scenarios=m['scenarios'];need(type(scenarios) is dict and 1<=len(scenarios)<=5,'Invalid hypothesis count')
    statuses=Counter(); bounds=[]; points=[]; stochastic=0
    for name,s in scenarios.items():
        need(identifier(name) and sha(s['scenario_sha256']) and s.get('full_action_space_covered') is False,'Invalid hypothesis provenance')
        rows=s['alternatives'];need(type(rows) is list and 1<=len(rows)<=7 and s['modeled_actions']==len(rows),'Invalid alternatives')
        ev={}
        for row in rows:
            key=action_key(row['action']);q=fraction(row['ev_fraction_bb']);lo,hi=map(number,row['sampling_interval_bb'])
            need(key not in ev and same(float(q),row['ev_bb']) and lo<=hi and lo-1e-10<=float(q)<=hi+1e-10,'Invalid alternative EV')
            ev[key]=(q,lo,hi)
        n=s['stochastic_action_intervals'];need(type(n) is int and 0<=n<=len(rows),'Invalid interval count');stochastic+=n
        status=s['status']; statuses[status]+=1
        if chosen not in ev or len(ev)==1:
            expected='NO_MATCH' if chosen not in ev else 'INSUFFICIENT_DATA'
            need(status==expected and all(s[k] is None for k in ('conditional_ev_loss_bb','conditional_ev_loss_fraction_bb','loss_bounds_bb')),'Missing action incorrectly scored')
            continue
        point=max(x[0] for x in ev.values())-ev[chosen][0]
        need(fraction(s['conditional_ev_loss_fraction_bb'])==point and same(float(point),s['conditional_ev_loss_bb']),'Loss fraction mismatch')
        lo,hi=span(s['loss_bounds_bb']);own=ev[chosen];rivals=[x for k,x in ev.items() if k!=chosen]
        need(same(lo,max(0,max(x[1]-own[2] for x in rivals))) and same(hi,max(0,max(x[2]-own[1] for x in rivals))) and lo-1e-10<=float(point)<=hi+1e-10,'Loss bounds mismatch')
        if n==0: need(lo==hi==float(point),'Exact loss bounds mismatch')
        expected='INFERIOR_UNDER_BOUNDS' if lo>0 else 'BEST_OR_TIED_UNDER_BOUNDS' if hi==0 else 'UNCERTAIN_UNDER_BOUNDS'
        need(status==expected,'Conditional classification mismatch')
        bounds.append((lo,hi));points.append(float(point))
    cov=m['coverage'];need(cov=={'hypotheses_submitted':len(scenarios),'hypotheses_comparable':len(bounds),'no_match':statuses['NO_MATCH'],'insufficient_data':statuses['INSUFFICIENT_DATA'],'full_action_space_covered':False},'Coverage mismatch')
    need(m['stochastic_action_intervals']==stochastic and same(m['sampling_interval_joint_coverage_lower_bound'],max(0,1-.05*stochastic)),'Sampling coverage mismatch')
    if len(bounds)!=len(scenarios):
        need(m['conditional_loss_point_span_bb'] is None and m['conditional_loss_bounds_span_bb'] is None,'Partial hypotheses cannot produce complete span')
        return {'classification':('PARTIAL_HYPOTHESES' if bounds else 'NO_MATCH' if statuses['NO_MATCH'] else 'INSUFFICIENT_DATA'),'comparable_hypotheses':len(bounds),'hypotheses':len(scenarios),'stochastic_intervals':stochastic,'loss_bounds_bb':None}
    lo=min(a for a,b in bounds);hi=max(b for a,b in bounds)
    need(all(same(x,y) for x,y in zip(span(m['conditional_loss_bounds_span_bb']),(lo,hi))) and all(same(x,y) for x,y in zip(span(m['conditional_loss_point_span_bb']),(min(points),max(points)))),'Model span mismatch')
    classification=('INFERIOR_IN_ALL_DECLARED_HYPOTHESES' if lo>(1e-10 if stochastic else 0) else 'BEST_OR_TIED_IN_ALL_DECLARED_HYPOTHESES' if hi==0 else 'SENSITIVE_OR_UNCERTAIN')
    return {'classification':classification,'comparable_hypotheses':len(bounds),'hypotheses':len(scenarios),'stochastic_intervals':stochastic,'loss_bounds_bb':[lo,hi]}


def identity(r,b):
    need(type(r) is dict and type(r.get('variant')) is int and r['variant']==5 and all(r.get(k)==b[k] for k in ('job_id','source_sha256','manifest_sha256','draft_sha256')),'Mixed job or evidence identity')


def financial(r,b,drafts):
    if r is None:
        return {'drafts_declared':len(drafts),'reconciled_drafts':0,'unresolved_drafts':0,'unreviewed_drafts':len(drafts),'conditional_net_bb':None,'conditional_net_fraction_bb':None,'net_covers_all_declared_drafts':False,'financial_results_verified':False}
    identity(r,b)
    need(r.get('status')=='conditional_financial_review_not_video_verified' and all(r.get(k) is False for k in ('financial_results_verified','equity_ev_authorized','automatic_clip_selection_authorized')),'Unsupported financial report')
    seen=set();net=Fraction(0);ok=bad=0
    for row in r['reviews']:
        d=row['draft_id'];need(d in drafts and d not in seen and row.get('financial_result_verified') is False and row.get('ev_loss_bb') is None,'Invalid financial draft')
        seen.add(d)
        if row['status']=='conditional_reconciled':
            need(row['review_flags']==[] and row['residual_bb']=='0','Unreconciled balance')
            amounts=row['submitted_totals_bb'];need(set(amounts)=={'contribution','return','payout','rebuy','withdrawal'},'Invalid totals')
            def money(v):
                need(type(v) is str and re.fullmatch(r'\d{1,13}(?:\.\d{1,6})?',v) is not None,'Invalid ledger amount')
                return Fraction(v)
            a={k:money(v) for k,v in amounts.items()};q=a['payout']+a['return']-a['contribution']
            need(a['return']<=a['contribution'] and Fraction(row['conditional_net_bb'])==q and Fraction(row['external_adjustment_bb'])==a['rebuy']-a['withdrawal'],'Ledger totals mismatch')
            net+=q;ok+=1
        else:
            need(row['status']=='unresolved' and row['conditional_net_bb'] is None,'Unresolved ledger has result');bad+=1
    unreviewed=r['unreviewed_draft_ids'];need(type(unreviewed) is list and len(set(unreviewed))==len(unreviewed) and set(unreviewed)==drafts-seen,'Financial coverage mismatch')
    return {'drafts_declared':len(drafts),'reconciled_drafts':ok,'unresolved_drafts':bad,'unreviewed_drafts':len(unreviewed),'conditional_net_bb':float(net) if ok else None,'conditional_net_fraction_bb':{'numerator':net.numerator,'denominator':net.denominator} if ok else None,'financial_results_verified':False,'net_covers_all_declared_drafts':ok==len(drafts),'source_report_sha256':digest(r)}


def aggregate(b):
    """One declared job roster; no proof of completeness or action authenticity."""
    fields={'variant','job_id','source_sha256','manifest_sha256','draft_sha256','draft_ids','expected_decisions','reports','financial_report'}
    need(type(b) is dict and set(b)==fields and type(b['variant']) is int and b['variant']==5 and sha(b['job_id'],32) and all(sha(b[k]) for k in ('source_sha256','manifest_sha256','draft_sha256')),'Strict PLO5 bundle required')
    ids=b['draft_ids'];need(type(ids) is list and 1<=len(ids)<=10000 and all(identifier(d) for d in ids) and len(set(ids))==len(ids),'Invalid declared drafts')
    drafts=set(ids);expected=b['expected_decisions'];need(type(expected) is list and len(expected)<=10000,'Invalid declared decision roster')
    roster={}
    for e in expected:
        need(type(e) is dict and set(e)=={'draft_id','action_file'} and e['draft_id'] in drafts and identifier(e['action_file']) and e['action_file'] not in roster,'Duplicate or invalid expected decision')
        roster[e['action_file']]=e['draft_id']
    reports=b['reports'];need(type(reports) is list and len(reports)<=len(roster),'Invalid report list');rows={}
    for r in reports:
        identity(r,b);f=r['action_file'];need(f in roster and f not in rows and r['draft_id']==roster[f] and identifier(r['context_file']) and r['context_file']!=f,'Duplicate or unrostered report')
        need(0<number(r['action_pts'])-number(r['context_pts'])<=10 and number(r['context_pts'])>=0,'Invalid evidence order')
        need(all(r.get(k) is False for k in ('video_verified','gto_solution','strategic_error_established','automatic_clip_selection_authorized')) and all(k in r and r[k] is None for k in ('financial_result_bb','ev_loss_bb')),'Unsupported verified claim')
        c=normalize_scenario(5,r['context']);need(c==r['context'],'Noncanonical context')
        chosen=action_key(r['chosen_action_declared']);status=r['status'];m=r.get('conditional_model')
        if m is None:
            need(status in ('NO_MATCH','INSUFFICIENT_DATA'),'Missing model')
            result={'classification':status,'comparable_hypotheses':0,'hypotheses':0,'stochastic_intervals':0,'loss_bounds_bb':None}
        else:
            result=model_result(m,chosen)
            cov=m['coverage'];expected_status='CONDITIONAL_MODEL_ONLY' if cov['hypotheses_comparable'] else 'NO_MATCH' if cov['no_match'] else 'INSUFFICIENT_DATA'
            need(status==expected_status,'Decision status mismatch')
        rows[f]={'draft_id':roster[f],'action_file':f,'position':c['position'],'street':c['street'],'action':chosen[0],'hero_remaining_stack_bucket_bb':bucket(c['stack']),'players_dealt':c['players'],'report_sha256':digest(r),**result}
    missing=[{'draft_id':d,'action_file':f,'classification':'MISSING_REPORT','position':None,'street':None,'action':None,'hero_remaining_stack_bucket_bb':None,'players_dealt':None,'comparable_hypotheses':0,'hypotheses':0,'stochastic_intervals':0,'loss_bounds_bb':None} for f,d in roster.items() if f not in rows]
    all_rows=sorted(list(rows.values())+missing,key=lambda r:r['action_file'])
    def summarize(items):
        counts=Counter(r['classification'] for r in items);n=len(items)
        comparable=[r for r in items if r['loss_bounds_bb'] is not None];inferior=[r for r in comparable if r['classification']=='INFERIOR_IN_ALL_DECLARED_HYPOTHESES']
        distinct=len({r['draft_id'] for r in inferior});intervals=sum(r['stochastic_intervals'] for r in comparable)
        return {'declared_decisions':n,'reports_received':n-counts['MISSING_REPORT'],'fully_comparable_decisions':len(comparable),'coverage_fraction':len(comparable)/n if n else None,'classification_counts':dict(sorted(counts.items())),'conditional_inferior_decisions':len(inferior),'conditional_inferior_fraction_of_comparable':len(inferior)/len(comparable) if comparable else None,'conditional_inferior_fraction_of_declared':len(inferior)/n if n else None,'distinct_inferior_draft_segments':distinct,'repeated_conditional_pattern':distinct>=2,'sampling_joint_coverage_lower_bound':max(0,1-.05*intervals) if comparable else None,'conditional_loss_total_bb':None,'verified_leak_count':None,'action_files':[r['action_file'] for r in items]}
    dimensions=('position','street','action','hero_remaining_stack_bucket_bb');groups={}
    for name,keys in [(k,('players_dealt',k)) for k in dimensions]+[('combined',('players_dealt',)+dimensions)]:
        g=defaultdict(list)
        for r in all_rows:g[tuple(r[k] for k in keys)].append(r)
        groups[name]=[{**dict(zip(keys,key)),**summarize(items)} for key,items in sorted(g.items(),key=lambda x:str(x[0]))]
    return {'variant':5,'status':'CONDITIONAL_PATTERN_REVIEW_ONLY','job_id':b['job_id'],'source_sha256':b['source_sha256'],'manifest_sha256':b['manifest_sha256'],'draft_sha256':b['draft_sha256'],'bundle_sha256':digest(b),'overall':summarize(all_rows),'groups':groups,'decisions':all_rows,'financial':financial(b['financial_report'],b,drafts),'denominator_scope':'declared_roster_only_not_all_session_decisions','stack_scope':'hero_remaining_not_effective_stack','recurrence_scope':'two_or_more_distinct_declared_draft_segments_not_verified_hands','full_session_coverage_verified':False,'report_authenticity_verified':False,'strategic_error_established':False,'gto_solution':False,'video_verified':False,'ev_loss_bb':None,'variance_attribution':None,'automatic_clip_selection_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle');p.add_argument('output');a=p.parse_args(argv)
    source=Path(a.bundle);out=Path(a.output)
    need(source.is_file() and not source.is_symlink() and 0<source.stat().st_size<=32*1024*1024,'Unsafe input')
    need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    def unique(pairs):
        obj={}
        for k,v in pairs:need(k not in obj,'Duplicate JSON key');obj[k]=v
        return obj
    raw=source.read_bytes();need(len(raw)<=32*1024*1024,'Oversized input')
    r=aggregate(json.loads(raw,object_pairs_hook=unique));r['input_sha256']=hashlib.sha256(raw).hexdigest()
    with out.open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__':raise SystemExit(main())
