"""Independent uniform-policy cash-flow oracles and full-street regression."""
import os
import unittest
from collections import defaultdict
from fractions import Fraction
from itertools import permutations
from test_plo5_post_gto_river import polar, NUT, BLUFF, CATCH, BOARD
from offline_omaha_showdown import omaha_rank
from plo5_post_gto_context import DECK
from plo5_post_gto_turn_solver import solve_flop, solve_multistreet, solve
from plo5_post_gto_turn_reach import condition_path
from plo5_post_gto_rake_solver import solve as river


def uniform_oracle(c):
    # Pot/stacks 2 BB, one all-in size, no rake. Independent cash flows.
    # In each public branch group by own holding, not hidden runout.
    samples=[]
    for h,w in ((NUT,Fraction(1,3)),(BLUFF,Fraction(2,3))):
        for t,r in permutations(sorted(DECK-set(h)-set(CATCH)-set(c['board'])),2):
            b=c['board']+[t,r];a,z=omaha_rank(h,b),omaha_rank(CATCH,b)
            q=Fraction(1) if a>z else Fraction(1,2) if a==z else Fraction(0)
            samples.append((tuple(h),t,r,q,w/1482))
    def evaluate(rows,p,depth,br):
        mass=sum(x[4] for x in rows)
        q=sum(x[4]*(x[3] if p==0 else 1-x[3]) for x in rows)/mass
        sd=6*q-2; bet=(2+sd)/2
        if depth==2:cont=2*q
        else:
            groups=defaultdict(list)
            for x in rows:groups[x[depth+1]].append(x)
            cont=sum(sum(x[4] for x in g)*evaluate(g,p,depth+1,br) for g in groups.values())/mass
        if not br:return ((cont+sd/2)/2+bet)/2 if p==0 else ((cont+bet)/2+sd/2)/2
        return max((cont+max(0,sd))/2,bet) if p==0 else (max(cont,bet)+max(0,sd))/2
    # Uniform seat1 formula: root seat0 bet half, seat1 fold/call uniform;
    # seat0 checks half, seat1 check/bet uniform, seat0 fold/call uniform.
    # For p1 root seat0 bet branch gives sd/2, check branch gives (cont+bet)/2.
    groups=defaultdict(list)
    for x in samples:groups[x[0]].append(x)
    v0=sum(sum(x[4] for x in g)*evaluate(g,0,0,False) for g in groups.values())
    br0=sum(sum(x[4] for x in g)*evaluate(g,0,0,True) for g in groups.values())
    return v0,br0,evaluate(samples,1,0,True)


class FullPostflopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=dict(polar(),board=BOARD[:3]);cls.r=solve_flop(cls.c,1,rake_on_fold=False)
    def test_independent_oracle(self):
        v,b0,b1=uniform_oracle(self.c)
        for a,b in zip([self.r['values_bb'][0],*self.r['best_responses_bb']],[v,b0,b1]):self.assertAlmostEqual(a,float(b),places=8)
    def test_public_infosets(self):
        r=self.r;self.assertEqual(r['chance_outcomes'],2964);self.assertEqual(r['runouts_per_pair'],1482)
        self.assertEqual(len([p for p in r['policy'] if p['node']==0]),2)
        for p in r['policy']:
            s=r['tree'][p['node']];self.assertFalse(set(p['holding'])&set(s['board']))
            self.assertEqual([x[1] for x in s['history'] if x[0]=='chance'],s['board'][3:])
            self.assertAlmostEqual(sum(a['frequency'] for a in p['actions']),1)
    def test_joint_reach(self):
        h=[['BB','check',0],['BTN','check',0]];t=h+[['chance','2d',0]];u=t+h+[['chance','As',0]]
        self.assertEqual(condition_path(self.c,self.r,h)['path_probability'],[1,4])
        self.assertEqual(condition_path(self.c,self.r,t)['path_probability'],[1,156])
        r=condition_path(self.c,self.r,u)
        self.assertEqual(r['path_probability'],[1,35568]);self.assertEqual(len(r['deals']),1)
        self.assertEqual(r['deals'][0]['holdings'][0],sorted(BLUFF))
    def test_budgets(self):
        for kw in (dict(max_outcomes=2963),dict(node_limit=100),dict(max_work=100)):
            with self.assertRaises(ValueError):solve_flop(self.c,1,rake_on_fold=False,**kw)
        with self.assertRaises(ValueError):solve(self.c,1,rake_on_fold=False)
    @unittest.skipUnless(os.environ.get('PLO5_MULTISTREET_EXE'),'native executable absent')
    def test_native_and_river(self):
        exe=os.environ['PLO5_MULTISTREET_EXE']
        for bps,cap,fold in ((0,0,False),(5000,3,True)):
            c=dict(self.c,rake_bps=bps,rake_cap=cap)
            a=solve_flop(c,3,rake_on_fold=fold);b=solve_flop(c,3,rake_on_fold=fold,cfr_executable=exe)
            self.assertEqual(a['tree'],b['tree']);self.assertEqual(len(a['policy']),len(b['policy']))
            for x,y in zip(a['values_bb']+a['best_responses_bb'],b['values_bb']+b['best_responses_bb']):self.assertAlmostEqual(x,y,delta=1e-8)
            for x,y in zip(a['policy'],b['policy']):
                self.assertEqual((x['node'],x['holding']),(y['node'],y['holding']))
                for u,v in zip(x['actions'],y['actions']):
                    self.assertAlmostEqual(u['frequency'],v['frequency'],delta=1e-8)
                    if u['ev_bb'] is None:self.assertIsNone(v['ev_bb'])
                    else:self.assertAlmostEqual(u['ev_bb'],v['ev_bb'],delta=1e-8)
            c=dict(polar(),rake_bps=bps,rake_cap=cap)
            a=river(c,100,(),rake_on_fold=fold);b=solve_multistreet(c,100,rake_on_fold=fold,cfr_executable=exe)
            for x,y in zip(a['values_bb']+a['best_responses_bb'],b['values_bb']+b['best_responses_bb']):self.assertAlmostEqual(x,y,delta=1e-8)

if __name__=='__main__':unittest.main()
