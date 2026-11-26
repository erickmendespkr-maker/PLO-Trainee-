"""Dense PLO5 balance triage and explicit, conditional review of settled anchors.
A displayed decline is not a loss. Neither OCR nor reviewer declarations certify a hand.
"""
from decimal import Decimal
import hashlib
import json
import re


def need(ok, message):
    if not ok: raise ValueError(message)


def money(v):
    need(type(v) is str and re.fullmatch(r'\d{1,9}(?:\.\d{1,6})?',v), 'Invalid BB amount')
    return Decimal(v)


def fmt(v): return format(v.normalize(),'f') if v else '0'


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def roster(review):
    need(review.get('variant')==5 and review.get('status')=='CROSS_WINDOW_REVIEW_CANDIDATES' and
         all(review.get(k) is False for k in ('hands_reconstructed','financial_result_verified','video_verified')), 'Unverified PLO5 candidates required')
    out={};files=set()
    for s in review['segments']:
        sid=s['candidate_id'];frames=s['frames'];need(sid not in out and frames,'Invalid candidate segment')
        prev=-1
        for f in frames:
            need(f['file'] not in files and f['pts']>prev,'Duplicate or unordered frame')
            prev=f['pts'];files.add(f['file'])
            if f['stack_bb'] is not None:money(f['stack_bb'])
        out[sid]=s
    return out


def triage(review, threshold='30'):
    """Prioritize observed drawdowns for human review, not confirmed hand losses."""
    cutoff=money(threshold);need(cutoff>0,'Positive threshold required');rows=[]
    for sid,s in roster(review).items():
        observed=[(f,money(f['stack_bb'])) for f in s['frames'] if f['stack_bb'] is not None]
        peak=None;drop=Decimal(0);anchors=None;ups=[];last=None
        for f,v in observed:
            if peak is None or v>peak[1]:peak=(f,v)
            if peak[1]-v>drop:
                drop=peak[1]-v;anchors=[peak[0]['file'],f['file']]
            if last is not None and v>last[1]:ups.append({'before':last[0]['file'],'after':f['file'],'increase_bb':fmt(v-last[1])})
            last=(f,v)
        rows.append({'candidate_id':sid,'table_id':s['table_id'],'observed_stack_readings':len(observed),
                     'maximum_display_decline_bb':fmt(drop) if len(observed)>=2 else None,'decline_evidence':anchors,
                     'display_increases':ups,'priority_review':drop>cutoff if len(observed)>=2 else False,
                     'conditional_net_bb':None,'financial_result_verified':False})
    rows.sort(key=lambda r:(not r['priority_review'],-money(r['maximum_display_decline_bb'] or '0'),r['candidate_id']))
    return {'variant':5,'status':'DISPLAY_DECLINE_TRIAGE_ONLY','review_sha256':digest(review),'threshold_bb':threshold,
            'rows':rows,'financial_results_verified':False,'confirmed_losses':0}


def reconcile(review, declarations):
    """Require explicit settled anchors and complete transfer declarations; no inferred events."""
    segments=roster(review)
    need(type(declarations) is dict and set(declarations)=={'variant','review_sha256','reviews'} and declarations['variant']==5 and declarations['review_sha256']==digest(review),'Review identity mismatch')
    rows=declarations['reviews'];need(type(rows) is list and len(rows)<=len(segments),'Invalid review count')
    used=set();out=[]
    for r in rows:
        need(type(r) is dict and set(r)=={'candidate_id','reviewer','same_hand_and_settled','transfers_complete','before','after','transfers'},'Invalid declaration')
        sid=r['candidate_id'];need(sid in segments and sid not in used,'Unknown or duplicate candidate');used.add(sid)
        need(type(r['reviewer']) is str and bool(r['reviewer'].strip()) and len(r['reviewer'])<=100 and type(r['same_hand_and_settled']) is bool and type(r['transfers_complete']) is bool,'Explicit review required')
        frames={f['file']:f for f in segments[sid]['frames']}
        def anchor(a):
            need(type(a) is dict and set(a)=={'file','bb'} and a['file'] in frames,'Invalid anchor')
            f=frames[a['file']];v=money(a['bb']);need(f['stack_bb'] is not None and money(f['stack_bb'])==v,'Anchor disagrees with displayed candidate')
            return f,v
        before,b=anchor(r['before']);after,a=anchor(r['after']);need(before['pts']<after['pts'],'Anchor order invalid')
        adjustment=Decimal(0);seen=set();transfers=r['transfers'];need(type(transfers) is list and len(transfers)<=512,'Invalid transfers')
        for t in transfers:
            need(type(t) is dict and set(t)=={'file','kind','bb'} and t['kind'] in ('rebuy','withdrawal') and t['file'] in frames,'Invalid transfer')
            key=(t['file'],t['kind']);v=money(t['bb']);need(key not in seen and v>0 and before['pts']<frames[t['file']]['pts']<=after['pts'],'Duplicate or out-of-interval transfer');seen.add(key)
            adjustment+=v if t['kind']=='rebuy' else -v
        ok=r['same_hand_and_settled'] and r['transfers_complete'];net=a-b-adjustment if ok else None
        out.append({'candidate_id':sid,'status':'CONDITIONAL_SETTLED_BALANCE' if ok else 'UNRESOLVED',
                    'display_change_bb':fmt(a-b),'declared_external_adjustment_bb':fmt(adjustment),
                    'conditional_net_bb':fmt(net) if ok else None,'conditional_loss_over_30bb':net<Decimal(-30) if ok else None,
                    'independent_pot_ledger_verified':False,'financial_result_verified':False,'ev_loss_bb':None})
    return {'variant':5,'status':'CONDITIONAL_BALANCE_REVIEW_ONLY','review_sha256':digest(review),'reviews':out,
            'unreviewed_candidates':sorted(set(segments)-used),'financial_results_verified':False,'automatic_clip_selection_authorized':False}
