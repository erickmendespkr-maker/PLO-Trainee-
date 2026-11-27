"""Offline PLO5 decision selection, separate from frame decoding and solver training.
Declared upstream certificates are inputs, not independently authenticated proofs.
Experimental solver outputs NEVER acquire a certification flag automatically.
"""
import argparse
import hashlib
import json
import re
from fractions import Fraction
from math import isfinite
from pathlib import Path
from plo5_error_selection import select_errors
from plo5_pre_gto_context import need, cards

VERSION = 'plo5-selective-decisions-v1'
STREETS = ('preflop', 'flop', 'turn', 'river')
BY_BOARD = {3:'flop',4:'turn',5:'river'}
ACTIONS = {'fold','check','call','bet','raise'}
SHA = re.compile(r'[0-9a-f]{64}')
MAX_ROWS = 10000


def street_filter(value):
    need(type(value) in (tuple,list) and value and len(value)<=4,'Select at least one street')
    need(all(type(s) is str and s in STREETS for s in value) and len(set(value))==len(value),'Invalid street filter')
    return tuple(s for s in STREETS if s in value)


def action_key(a):
    need(type(a) in (tuple,list) and len(a)==2 and type(a[0]) is str and a[0] in ACTIONS and type(a[1]) is int and 0<=a[1]<=10**12,'Invalid action')
    need((a[1]==0)==(a[0] in ('fold','check')),'Invalid action payment')
    return f'{a[0]}:{a[1]}'


def action_token(s):
    need(type(s) is str and re.fullmatch(r'(fold|check|call|bet|raise):(0|[1-9][0-9]{0,12})',s) is not None,'Invalid action key')
    a,n=s.split(':');return action_key([a,int(n)])


def hash_ok(s):return type(s) is str and SHA.fullmatch(s) is not None


def identity(d):
    k=(d.get('hand_id'),d.get('decision_id'))
    need(all(type(x) is str and 0<len(x)<=128 for x in k),'Invalid decision identity')
    need(type(d.get('street')) is str and d['street'] in STREETS,'Invalid street')
    return k


def evidence_request(d):
    e=d.get('evidence')
    if e is None:return None
    need(type(e) is dict and set(e)=={'source_sha256','rgb_sha256','pts','table_id','phase','hand_id','decision_id','street'},'Invalid evidence reference')
    need(hash_ok(e['source_sha256']) and hash_ok(e['rgb_sha256']),'Invalid evidence digest')
    need((e['hand_id'],e['decision_id'])==identity(d) and e['street']==d['street'],'Evidence identity mismatch')
    need(type(e['table_id']) is int and 1<=e['table_id']<=4 and e['phase'] in ('before','after'),'Invalid evidence location')
    need(type(e['pts']) is str and len(e['pts'])<=64 and re.fullmatch(r'[0-9]+(?:/[1-9][0-9]*)?',e['pts']) is not None,'Use exact rational PTS')
    pts=Fraction(e['pts']);need(0<=pts<=10**8,'Invalid timestamp')
    return dict(e,pts=str(pts),status='EXTRACTION_REQUEST_ONLY')


def select(records,streets=STREETS):
    selected=street_filter(streets)
    need(type(records) is list and len(records)<=MAX_ROWS,'Decision budget exceeded')
    seen=set();rows=[];pending=[];by_street={s:dict(errors=0,adequate=0,unresolved=0,excluded=0) for s in STREETS}
    for d in records:
        need(type(d) is dict,'Invalid decision');k=identity(d)
        need(k not in seen,'Duplicate decision');seen.add(k)
        street=d['street'];actual=action_token(d.get('action'))
        if street not in selected:by_street[street]['excluded']+=1;continue
        ev=d.get('action_ev_bounds',{});need(type(ev) is dict and len(ev)<=64,'Invalid action bounds')
        for a,b in ev.items():
            action_token(a);need(type(b) in (list,tuple) and len(b)==2 and all(type(x) in (int,float) and isfinite(x) and abs(x)<=10**12 for x in b) and b[0]<=b[1],'Invalid EV interval')
        odds=d.get('pot_odds');need(odds is None or type(odds) in (int,float) and isfinite(odds) and 0<=odds<=1,'Invalid pot odds')
        # Require explicit comparable basis and complete modeled action set from upstream.
        certified=(d.get('reconstruction_verified') is True and d.get('strategy_verified') is True and d.get('action_set_complete') is True and d.get('ev_basis')=='incremental_bb' and hash_ok(d.get('certificate_sha256')))
        ref=evidence_request(d)
        row=dict(hand_id=k[0],decision_id=k[1],street=street,action=actual,action_ev_bounds=ev,pot_odds=odds,evidence=ref,reconstruction_verified=certified,strategy_verified=certified)
        rows.append(row)
    r=select_errors(rows);index={(d['hand_id'],d['decision_id']):d for d in rows}
    requests=[];errors=[]
    for e in r['errors']:
        k=(e['hand_id'],e['decision_id']);by_street[e['street']]['errors']+=1
        lower=e['ev_loss_lower_bb'];severity='grave' if lower>=5 else 'relevante' if lower>=1 else 'marginal'
        errors.append(dict(e,severity=severity,evidence_status='REQUESTED' if e['evidence'] else 'MISSING_REFERENCE',classification_basis='DECLARED_UPSTREAM_CERTIFICATE'))
        if e['evidence']:requests.append(e['evidence'])
    for k in r['adequate']:by_street[index[k]['street']]['adequate']+=1
    for k in r['unresolved']:
        d=index[k];by_street[d['street']]['unresolved']+=1
        pending.append(dict(hand_id=k[0],decision_id=k[1],street=d['street'],reason='NO_CERTIFICATE_OR_INCOMPLETE_ACTION_SET' if not d['strategy_verified'] else 'OVERLAPPING_OR_MISSING_EV_BOUNDS'))
    errors.sort(key=lambda e:(-e['ev_loss_lower_bb'],e['hand_id'],e['decision_id']))
    return dict(version=VERSION,streets=list(selected),total=len(records),evaluated=len(rows),by_street=by_street,errors=errors,unresolved=pending,adequate_count=len(r['adequate']),print_requests=requests,certificates_independently_verified=False,prints_extracted=False)


def model_state(model):
    from plo5_post_gto_tree import start,step,advance,bounds
    s=start(model['context']);root=s;h=cards(model['holding'])
    history=model['history'];need(type(history) is list and len(history)<=128,'Invalid prefix')
    for p,a,v in history:
        if p=='chance':
            need(v==0 and a not in h,'Invalid chance');s=advance(s,a);root=s
        else:s=step(s,p,a,v)
    need(s.actor is not None and not set(h)&set(s.board),'Invalid decision state')
    action_key(model['action']);step(s,s.actor,*model['action']);b=bounds(s);i=s.pending[0]
    # HU street-start effective SPR avoids reporting zero after an opponent shoves.
    spr=min(root.remaining)/root.pot if len(root.order)==2 and root.pot else None
    return dict(street=BY_BOARD[len(s.board)],board=list(s.board),position=s.actor,pot_bb=s.pot/s.bb,call_bb=b['call_payment']/s.bb,pot_odds_gross=b['call_payment']/(s.pot+b['call_payment']) if b['call_payment'] else None,remaining_bb=s.remaining[i]/s.bb,effective_spr_street_start=spr)


def evaluate_models(cache,records,streets=STREETS,*,cfr_executable=None):
    from plo5_review import postflop
    selected=street_filter(streets);need(type(records) is list and len(records)<=64,'Model batch budget')
    seen=set();prepared=[];out=[];estimates=[]
    # Validate every identity and street before expensive solves; skip only unselected computations.
    for d in records:
        need(type(d) is dict and set(d)=={'hand_id','decision_id','street','model'},'Invalid model record')
        k=identity(d);need(k not in seen,'Duplicate decision');seen.add(k)
        m=d['model'];need(type(m) is dict and {'context','history','holding','action','rake_on_fold'}<=set(m)<={'context','history','holding','action','rake_on_fold','iterations','pot_bps','joint'},'Invalid model fields')
        state=model_state(m);need(state['street']==d['street'],'Street does not match replay')
        prepared.append((d,m,state))
    for d,m,state in prepared:
        row=dict(hand_id=d['hand_id'],decision_id=d['decision_id'],street=d['street'],action=action_key(m['action']),reconstruction_verified=False,strategy_verified=False)
        out.append(row)
        if d['street'] not in selected:continue
        r=postflop(cache,**m,cfr_executable=cfr_executable)
        need(r['board']==state['board'] and r['action']==m['action'] and r['position']==state['position'] and r['pot_odds_gross']==state['pot_odds_gross'],'Solver decision mismatch')
        estimates.append(dict(hand_id=d['hand_id'],decision_id=d['decision_id'],state=state,model=r,certified=False))
    result=select(out,selected);result['experimental_estimates']=estimates
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('select','models'));p.add_argument('input');p.add_argument('output');p.add_argument('--streets',nargs='+',choices=STREETS,default=list(STREETS));p.add_argument('--cache');p.add_argument('--native');a=p.parse_args(argv)
    path=Path(a.input);out=Path(a.output);need(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=16*1024**2,'Invalid input');need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON required')
    raw=path.read_bytes();d=json.loads(raw);need(type(d) is dict and set(d)=={'version','decisions'} and d['version']==VERSION,'Invalid contract version')
    if a.mode=='models':need(a.cache is not None,'Cache required');r=evaluate_models(a.cache,d['decisions'],a.streets,cfr_executable=a.native)
    else:r=select(d['decisions'],a.streets)
    r['input_sha256']=hashlib.sha256(raw).hexdigest()
    with out.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,allow_nan=False,indent=2)
    return 0

if __name__=='__main__':raise SystemExit(main())
