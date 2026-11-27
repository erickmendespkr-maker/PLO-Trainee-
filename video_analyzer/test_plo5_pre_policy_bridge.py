import copy
import os
import unittest
from fractions import Fraction
from test_plo5_pre_post_bridge import fixture
from test_plo5_post_gto_river import NUT, BLUFF, CATCH, BOARD
from plo5_pre_gto_tree import start,step,actions,bounds
from plo5_pre_gto_context import normalize
from plo5_pre_policy_bridge import extract,prepare,solve_from_policy,classify_history
from plo5_pre_gto_cfr_native import train


def export_fixture(c,indexed=True,native=None):
    root=start(c['stacks'],c['sb'],c['bb']);rr=normalize(c)['ranges'];nodes=[]
    def build(s):
        n=len(nodes);nodes.append(None);aa=actions(s) if s.pending else None
        ch=tuple(build(step(s,s.actor,a,b)) for a,b in aa) if aa else ()
        nodes[n]=(s,aa,ch);return n
    build(root);keys={(n,h) for n,(s,aa,ch) in enumerate(nodes) if aa for h in range(len(rr[s.actor]))}
    policies={k:[1/len(nodes[k[0]][1])]*len(nodes[k[0]][1]) for k in keys}
    if native:
        coefficients={}
        for n,(s,aa,ch) in enumerate(nodes):
            if aa is None:
                a,b=s.paid;bb=s.bb
                coefficients[n]=(-a/bb,0.) if s.folded[0] else (b/bb,0.) if s.folded[1] else (-min(a,b)/bb,2*min(a,b)/bb)
        # Explicit synthetic matrix, not actual PLO5 equity.
        policies=train(native,nodes,[(0,0,2/3,.25),(1,0,1/3,.75)],coefficients,keys,5)
    return dict(version='pre-gto-hu-cfr-v4' if indexed else 'pre-gto-multiway-v4',positions=list(root.order),nodes=len(nodes),
                rake=dict(bps=c['rake_bps'],cap=c['rake_cap'],on_fold=c['rake_on_fold']),
                tree=[dict(node=n,position=s.actor,children=list(ch),paid=list(s.paid),status=s.status) for n,(s,aa,ch) in enumerate(nodes)],
                policy=[dict(node=n,position=nodes[n][0].actor,holding=h if indexed else rr[nodes[n][0].actor][h]['cards'],actions=[dict(action=a,amount=b,frequency=f) for (a,b),f in zip(nodes[n][1],v)]) for (n,h),v in sorted(policies.items())])


class PolicyBridgeTests(unittest.TestCase):
    def test_indexed_and_physical_exports(self):
        c,_=fixture();a=prepare(c,BOARD[:3],export_fixture(c));b=prepare(c,BOARD[:3],export_fixture(c,False))
        self.assertEqual(a['bridge'],b['bridge']);self.assertFalse(a['evidence']['training_context_verified'])
        self.assertAlmostEqual(float(Fraction(*a['bridge']['history_probability'])),1/6,places=15)
    def test_reject_mismatches(self):
        c,_=fixture();r=export_fixture(c)
        for modify in (lambda x:x['tree'][0]['paid'].__setitem__(0,0),lambda x:x['policy'][0]['actions'][0].__setitem__('frequency',2),lambda x:x['policy'][0].__setitem__('holding',100)):
            d=copy.deepcopy(r);modify(d)
            with self.assertRaises(ValueError):extract(c,d)
        d=export_fixture(c,False);d['rake']['bps']=500
        with self.assertRaises(ValueError):extract(c,d)
    def test_raises_and_defense(self):
        c,_=fixture();c['stacks']={'SB':200,'BB':200};s=start(c['stacks'],1,2);history=[]
        for _ in range(3):
            a=bounds(s)['raise_max'];history.append(dict(position=s.actor,action='raise',amount=a));s=step(s,s.actor,'raise',a)
        a=bounds(s)['call_payment'];history.append(dict(position=s.actor,action='call',amount=a))
        c['history']=history;r=classify_history(c)
        self.assertEqual([e['classification'] for e in r['events']],['RFI','3BET','4BET','BLIND_DEFENSE'])
        self.assertEqual(r['status'],'flop_transition')
    def test_stackoff(self):
        c,_=fixture();c['stacks']={'SB':4,'BB':4};c['history']=[dict(position='SB',action='raise',amount=3),dict(position='BB',action='call',amount=2)]
        r=classify_history(c);self.assertEqual(r['status'],'all_in_showdown');self.assertTrue(all(e['all_in'] for e in r['events']))
        with self.assertRaises(ValueError):prepare(c,BOARD[:3],export_fixture(c))
    @unittest.skipUnless(os.environ.get('PLO5_CFR_EXE') and os.environ.get('PLO5_MULTIWAY_EXE'),'native binaries absent')
    def test_native_to_native(self):
        c,_=fixture();r=export_fixture(c,native=os.environ['PLO5_CFR_EXE'])
        with self.assertRaisesRegex(ValueError,'EXACT_WEIGHT_BUDGET'):prepare(c,BOARD[:3],r)
        b=prepare(c,BOARD[:3],r,approximate_joint=True)['bridge']
        self.assertFalse(b['joint_weights_exact'])
        self.assertLessEqual(Fraction(*b['joint_weight_tv']),Fraction(1,10**6))
        self.assertTrue(all(x['weight']>0 for x in b['joint']))
        result=solve_from_policy(c,BOARD[:3],r,iterations=1,approximate_joint=True,cfr_executable=os.environ['PLO5_MULTIWAY_EXE'])
        self.assertAlmostEqual(sum(result['solution']['net_from_hand_start_bb']),0,places=9)
        self.assertFalse(result['solution']['preflop_continuation_certified'])

if __name__=='__main__':unittest.main()
