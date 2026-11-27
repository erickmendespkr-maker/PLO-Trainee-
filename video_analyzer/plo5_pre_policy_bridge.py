"""Map existing preflop policy exports to observed histories, offline only.
Structural checks are not proof that an export was trained for the input prior.
"""
from math import isfinite, fsum
from hashlib import sha256
import json
from plo5_pre_gto_context import normalize, cards, need
from plo5_pre_gto_tree import start, step, bounds
from plo5_pre_post_bridge import prepare_flop, solve_observed_flop

VERSION = 'pre-policy-bridge-v1'


def classify_history(context):
    c=normalize(context); s=start(c['stacks'],c['sb'],c['bb'])
    raises=0; voluntary=False; out=[]
    for e in c['history']:
        b=bounds(s); p=s.pending[0]; actor=s.actor
        a=e['action']; amount=e['amount']; nxt=step(s,e['position'],a,amount)
        if a=='raise':
            label=('RFI' if not voluntary else 'ISO_RAISE') if raises==0 else f'{raises+2}BET'
            raises+=1
        elif raises and actor in ('SB','BB') and a in ('call','fold'):
            label='BLIND_DEFENSE'
        elif a=='call':label='CALL' if raises else ('COMPLETE' if actor=='SB' else 'LIMP')
        else:label=a.upper()
        out.append(dict(e,classification=label,raise_count=raises,
                        facing_to_call_chips=b['to_call'],all_in=nxt.remaining[p]==0,
                        terminal_status=nxt.status))
        voluntary=voluntary or a in ('call','raise');s=nxt
    return dict(events=out,status=s.status,paid=dict(zip(s.order,s.paid)),
                remaining=dict(zip(s.order,s.remaining)),pot=s.pot)


def extract(context, result):
    c=normalize(context);s=start(c['stacks'],c['sb'],c['bb'])
    version=result.get('version')
    need(version in ('pre-gto-hu-cfr-v4','pre-gto-multiway-v4'),'Unsupported preflop export')
    indexed=version=='pre-gto-hu-cfr-v4'
    need(not indexed or (len(s.order)==2 and c['rake_bps']==0),'HU export requires zero rake')
    if not indexed:
        need(result.get('positions')==list(s.order),'Position mismatch')
        need(result.get('rake')==dict(bps=c['rake_bps'],cap=c['rake_cap'],on_fold=c['rake_on_fold']),'Rake configuration mismatch')
    tree=result['tree'];policy=result['policy']
    need(type(tree) is list and 0<len(tree)<=100000 and result.get('nodes')==len(tree),'Invalid tree')
    need(type(policy) is list and len(policy)<=1000000,'Invalid policy')
    need(all(type(row) is dict and row.get('node')==i for i,row in enumerate(tree)),'Invalid node identity')
    by={}
    for row in policy:
        n=row['node'];need(type(n) is int and 0<=n<len(tree),'Invalid policy node')
        by.setdefault(n,[]).append(row)
    node=0;maps=[]
    def check_node(n,state):
        row=tree[n];need(row['position']==state.actor and row['paid']==list(state.paid) and row['status']==state.status,'Tree replay mismatch')
        return row
    for e in c['history']:
        t=check_node(node,s); actor=s.actor;children=t['children']
        need(type(children) is list and len(children)==len(set(children)) and all(type(k) is int and node<k<len(tree) for k in children),'Invalid children')
        rows=by.get(node,[]);need(bool(rows),'INCOMPLETE_POLICY')
        allowed=[tuple(x['cards']) for x in c['ranges'][actor]]
        seen=set();entries=[];reference=None;selected=None
        for row in rows:
            need(row['position']==actor,'Policy actor mismatch')
            h=row['holding']
            if indexed:
                need(type(h) is int and 0<=h<len(allowed),'Holding index mismatch');h=allowed[h]
            else:h=tuple(cards(h))
            need(h in allowed and h not in seen,'Unexpected or duplicate holding');seen.add(h)
            aa=row['actions'];need(type(aa) is list and len(aa)==len(children),'Action shape mismatch')
            actions=[(x['action'],x['amount']) for x in aa];freq=[x['frequency'] for x in aa]
            need(len(actions)==len(set(actions)) and all(type(x) in (int,float) and isfinite(x) and 0<=x<=1 for x in freq) and abs(fsum(freq)-1)<=1e-8,'Invalid action probabilities')
            if reference is None:
                reference=actions
                for k,(a,b) in zip(children,actions):check_node(k,step(s,actor,a,b))
                key=(e['action'],e['amount']);need(key in actions,'UNMODELED_ACTION');selected=actions.index(key)
            else:need(actions==reference,'Inconsistent action order')
            entries.append(dict(cards=list(h),frequency=freq[selected]))
        maps.append(sorted(entries,key=lambda x:x['cards']))
        s=step(s,e['position'],e['action'],e['amount']);node=children[selected]
    check_node(node,s)
    digest=sha256(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return dict(version=VERSION,source_version=version,source_sha256=digest,node=node,likelihoods=maps,
                history=classify_history(context),training_context_verified=False)


def prepare(context,flop,result,*,approximate_joint=False):
    evidence=extract(context,result)
    return dict(evidence=evidence,bridge=prepare_flop(context,flop,evidence['likelihoods'],approximate_joint=approximate_joint))


def solve_from_policy(context,flop,result,**kwargs):
    evidence=extract(context,result)
    return dict(evidence=evidence,solution=solve_observed_flop(context,flop,evidence['likelihoods'],**kwargs))
