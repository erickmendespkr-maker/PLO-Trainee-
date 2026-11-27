import itertools
import os
import unittest
from collections import defaultdict
from fractions import Fraction
from plo5_post_gto_context import DECK
from plo5_post_gto_multiway import prior, solve
from plo5_post_gto_tree import start, step
from offline_omaha_showdown import omaha_rank
from test_plo5_post_gto_river import polar, BOARD


def fixture(n, variants=1, street=5):
    c=polar();c['seats']=['SB','BB','UTG','MP','CO','BTN'][:n];c['actor']='SB'
    c['stacks']=dict.fromkeys(c['seats'],1);c['pot']=2;c['board']=BOARD[:street]
    deck=sorted(DECK-set(BOARD));c['ranges']={}
    for i,p in enumerate(c['seats']):
        h=deck[5*i:5*i+5];rows=[dict(cards=h,weight=1)]
        if variants==2:rows.append(dict(cards=h[:4]+[deck[5*n+i]],weight=2))
        c['ranges'][p]=rows
    return c


def oracle(c,result):
    # Enumerate pure response plans in a 3-seat river game. Replay public
    # paths, calculate payoff separately via unit-chip layers, no CFR/BR code.
    n=len(c['seats']);ranks={};ds=prior(c);mass=sum(w for _,w in ds)
    rows={(r['node'],tuple(r['holding'])):r['actions'] for r in result['policy']}
    states=[start(c)]*len(result['tree'])
    for node in result['tree']:
        for k in node['children']:
            p,a,b=result['tree'][k]['history'][-1];states[k]=step(states[node['node']],p,a,b)
    def payoff(s,h):
        if h not in ranks:ranks[h]=[omaha_rank(k,c['board']) for k in h]
        p=s.total_paid;active=s.active;out=[Fraction(-x) for x in p]
        def award(amount,eligible):
            best=max(ranks[h][i] for i in eligible);w=[i for i in eligible if ranks[h][i]==best]
            for i in w:out[i]+=Fraction(amount,len(w))
        award(c['pot'],active)
        for level in range(1,max(p)+1):
            payers=[i for i,x in enumerate(p) if x>=level]
            if len(payers)==1:out[payers[0]]+=1
            else:award(len(payers),[i for i in payers if i in active])
        return out
    def value(player,plan):
        def visit(i,h):
            s=states[i];ch=result['tree'][i]['children']
            if not ch:return float(payoff(s,h)[player])
            key=(i,h[s.pending[0]])
            if key in plan:return visit(ch[plan[key]],h)
            return sum(a['frequency']*visit(k,h) for a,k in zip(rows[key],ch))
        return sum(w/mass*visit(0,h) for h,w in ds)
    values=[];best=[]
    for p in range(n):
        keys=[k for k in rows if states[k[0]].pending[0]==p]
        values.append(value(p,{}));best.append(max(value(p,dict(zip(keys,aa))) for aa in itertools.product(*(range(len(rows[k])) for k in keys))))
    return values,best


class MultiwayTests(unittest.TestCase):
    def test_seat_counts(self):
        for n in range(2,7):
            c=fixture(n);r=solve(c,100,rake_on_fold=False)
            self.assertEqual(len(r['values_bb']),n);self.assertAlmostEqual(sum(r['values_bb']),2)
            self.assertLess(r['nashconv_bb'],.01)
    def test_correlated_prior_and_blockers(self):
        c=fixture(3,2);ds=prior(c);self.assertEqual(len(ds),8)
        joint=[dict(holdings=[list(x) for x in h],weight=w) for h,w in (ds[0],ds[-1])]
        r=solve(c,5,rake_on_fold=False,joint=joint);self.assertEqual(r['legal_deals'],2)
        self.assertNotEqual(r['model_key'],solve(c,5,rake_on_fold=False)['model_key'])
        with self.assertRaises(ValueError):prior(c,joint+joint)
        c['ranges']['BB'][0]=c['ranges']['SB'][0].copy();self.assertLess(len(prior(c)),8)
    def test_independent_oracle(self):
        c=fixture(3);r=solve(c,20,rake_on_fold=False);v,b=oracle(c,r)
        for a,z in zip(r['values_bb']+r['best_responses_bb'],v+b):self.assertAlmostEqual(a,z,places=9)
    def test_turn_and_rake(self):
        c=fixture(3,street=4);c['rake_bps']=5000;c['rake_cap']=2
        r=solve(c,2,rake_on_fold=True);self.assertEqual(r['chance_outcomes'],33)
        self.assertGreater(r['expected_rake_bb'],0);self.assertAlmostEqual(sum(r['values_bb'])+r['expected_rake_bb'],2)
        for p in r['policy']:
            node=r['tree'][p['node']];self.assertFalse(set(p['holding'])&set(node['board']))
            self.assertEqual([e[1] for e in node['history'] if e[0]=='chance'],node['board'][4:])
    def test_budgets(self):
        c=fixture(3,2)
        for kw in (dict(max_deals=1),dict(max_outcomes=1),dict(node_limit=1),dict(max_work=1)):
            with self.assertRaises(ValueError):solve(c,2,rake_on_fold=False,**kw)
    @unittest.skipUnless(os.environ.get('PLO5_MULTIWAY_EXE'),'native absent')
    def test_native(self):
        exe=os.environ['PLO5_MULTIWAY_EXE']
        for n,variants,street in ((2,2,5),(3,2,5),(4,1,5),(5,1,5),(6,1,5),(3,1,4)):
            c=fixture(n,variants,street);c['rake_bps']=5000;c['rake_cap']=2
            a=solve(c,10,rake_on_fold=True);b=solve(c,10,rake_on_fold=True,cfr_executable=exe)
            self.assertEqual(a['tree'],b['tree']);self.assertEqual(len(a['policy']),len(b['policy']))
            for x,y in zip(a['values_bb']+a['best_responses_bb'],b['values_bb']+b['best_responses_bb']):self.assertAlmostEqual(x,y,delta=1e-8)
            for x,y in zip(a['policy'],b['policy']):
                self.assertEqual((x['node'],x['holding']),(y['node'],y['holding']))
                for u,v in zip(x['actions'],y['actions']):
                    self.assertAlmostEqual(u['frequency'],v['frequency'],delta=1e-8)
                    if u['ev_bb'] is None:self.assertIsNone(v['ev_bb'])
                    else:self.assertAlmostEqual(u['ev_bb'],v['ev_bb'],delta=1e-8)

if __name__=='__main__':unittest.main()
