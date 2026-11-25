import copy
import random
import unittest
from fractions import Fraction
from itertools import combinations, product
from math import comb
from plo5_multiway_implied import multiway, analyze, DECK
from plo5_equity import known_equity
from test_plo5_evaluator import oracle_omaha

H=['As','Ks','2c','3d','4h']
V=['Ac','Ad','Kh','Kd','7c']
B=['Qs','Js','Ts','9d','8c']
W=['2s','3c','4d','5h','6c']
T=['2c','3d','4h','9s','Tc']
TIE=[['As','5s','Kc','Qd','Jh'],['Ad','5d','Ks','Qc','Jc'],['Ah','5h','Kd','Qs','Jd']]


def e(cards,weight=1): return {'cards':cards,'weight':weight}


def scenario():
    return {'variant':5,'hero':H,'board':B[:4],'ranges':[[e(V)],[e(W)]],
            'pot_chips':100,'call_chips':50,'hero_stack_chips':200,'opponent_stacks_chips':[150,120],
            'bb_chips':10,'rake_bps':500,'rake_cap_chips':20,'scenarios':{'base':[0]*4,'future':[30,40,20,10]}}


class MultiwayTests(unittest.TestCase):
    def test_three_way_split(self):
        r=multiway(TIE[0],T,[[e(h)] for h in TIE[1:]])
        self.assertEqual(r['equity_fraction'],{'numerator':1,'denominator':3})
        self.assertEqual(r['share_mass'],[0,0,0,1]);self.assertEqual(r['split_probability'],1)

    def test_all_player_counts_against_oracle(self):
        rng=random.Random(31)
        for n in range(2,7):
            deal=rng.sample(DECK,n*5+5);hands=[deal[i*5:i*5+5] for i in range(n)];b=deal[-5:]
            rr=[oracle_omaha(h,b) for h in hands];share=Fraction(1,rr.count(max(rr))) if rr[0]==max(rr) else 0
            r=multiway(hands[0],b,[[e(h)] for h in hands[1:]])
            self.assertEqual(Fraction(**r['equity_fraction']),share)
            self.assertEqual(r['players'],n)

    def test_joint_blockers_weighted_oracle(self):
        block=['Ac','2d','3h','4c','5d']
        a=[[e(V,3),e(block,2),e(H,4)],[e(W,5),e(['Ad','6d','7d','8d','Th'],7)]]
        b=B[:4];r=multiway(H,b,a);expected=[0]*4;total=0
        for x,y in product(*a):
            cards=x['cards']+y['cards']+H+b
            if len(set(cards))!=len(cards):continue
            weight=x['weight']*y['weight'];total+=weight
            for c in DECK:
                if c in cards:continue
                ranks=[oracle_omaha(h,b+[c]) for h in (H,x['cards'],y['cards'])]
                j=ranks.count(max(ranks)) if ranks[0]==max(ranks) else 0
                expected[j]+=weight
        self.assertEqual(r['legal_joint_weight'],total);self.assertEqual(r['input_joint_weight'],108)
        self.assertEqual(r['share_mass'],expected);self.assertEqual(r['runouts_per_joint_holding'],33)
        self.assertEqual(r['mass_denominator'],33*total)
        self.assertEqual(r['equity'],1)

    def test_turn_hu_matches_legacy(self):
        b=['Qs','Js','9d','8c'];a=multiway(H,b,[[e(V)]])
        old=known_equity(H,b,V)
        self.assertEqual(a['equity_fraction'],old['equity_fraction'])
        self.assertEqual(a['share_mass'],[old['outcome_mass'][k] for k in ('loss','win','tie')])

    def test_flop_multiway_exact_oracle(self):
        h=TIE[0];v=TIE[1:];b=T[:3];r=multiway(h,b,[[e(x)] for x in v])
        expected=[0]*4
        for run in combinations([c for c in DECK if c not in h+b+v[0]+v[1]],2):
            ranks=[oracle_omaha(x,b+list(run)) for x in [h]+v];best=max(ranks)
            expected[ranks.count(best) if ranks[0]==best else 0]+=1
        self.assertEqual(r['possible_states'],comb(34,2));self.assertEqual(r['share_mass'],expected)

    def test_monte_carlo_reproducible_and_budget(self):
        args=(H,[],[[e(V)],[e(W)]])
        r=multiway(*args,trials=60,seed=31)
        self.assertEqual(r,multiway(*args,trials=60,seed=31))
        self.assertEqual(r['possible_states'],comb(37,5));self.assertEqual(r['mass_denominator'],60)
        self.assertLessEqual(r['sampling_ci95'][0],r['equity']);self.assertGreaterEqual(r['sampling_ci95'][1],r['equity'])
        with self.assertRaises(ValueError):multiway(*args,method='exact')

    def test_implied_gain_with_rake_cap(self):
        r=analyze(scenario());f=r['scenarios']['future']
        self.assertEqual(r['base_call_ev_fraction_bb'],{'numerator':93,'denominator':10})
        self.assertEqual(f['expected_implied_gain_bb'],7.4);self.assertEqual(f['expected_reverse_implied_loss_bb'],0)
        self.assertEqual(f['ev_call_fraction_bb'],{'numerator':167,'denominator':10})
        self.assertEqual(r['max_future_matched_payment_per_player_chips'],120)
        self.assertFalse(r['gto_solution']);self.assertIsNone(r['ev_loss_bb'])

    def test_reverse_implied_loss(self):
        s=scenario();s['hero']=V;s['ranges']=[[e(H)],[e(W)]];r=analyze(s)
        self.assertEqual(r['base_call_ev_bb'],-5);self.assertEqual(r['required_additional_net_future_gain_bb'],5)
        self.assertEqual(r['scenarios']['future']['expected_reverse_implied_loss_bb'],3)
        self.assertEqual(r['scenarios']['future']['ev_call_bb'],-8)

    def test_outcome_correlated_payoff_and_sensitivity(self):
        s=scenario();s['board']=['Qs','Js','9d','8c'];s['scenarios']['optimistic']=[0,40,20,10]
        r=analyze(s);m=r['equity_model']['share_mass'];d=r['equity_model']['mass_denominator']
        self.assertEqual(m,[22,8,3,0]);self.assertEqual(r['base_call_ev_fraction_bb'],{'numerator':-53,'denominator':60})
        self.assertLess(r['scenarios']['future']['ev_call_bb'],0);self.assertGreater(r['scenarios']['optimistic']['ev_call_bb'],0)
        # Independent settlement per outcome with final pot rake, not separate equity multiplication.
        xs=s['scenarios']['future'];ev=Fraction(0)
        for j,(count,x) in enumerate(zip(m,xs)):
            pool=150+3*x;net=pool-min(20,pool*5//100)
            ev+=Fraction(count,d)*(Fraction(net,j) if j else 0)-Fraction(count,d)*(50+x)
        self.assertEqual(Fraction(**r['scenarios']['future']['ev_call_fraction_bb']),ev/10)
        self.assertFalse(r['span_is_confidence_interval'])
        mc=analyze(s,method='monte_carlo',trials=40,seed=31)
        self.assertAlmostEqual(mc['sampling_joint_coverage_lower_bound'],.85)
        for f in mc['scenarios'].values():
            self.assertLessEqual(f['sampling_ci95_bb'][0],f['ev_call_bb']+1e-12)
            self.assertGreaterEqual(f['sampling_ci95_bb'][1],f['ev_call_bb']-1e-12)

    def test_river_and_all_in_no_future(self):
        for mode in ('river','allin'):
            s=scenario()
            if mode=='river':s['board']=B
            else:s['opponent_stacks_chips'][1]=0
            with self.assertRaises(ValueError):analyze(s)
            s['scenarios']={'base':[0]*4};r=analyze(s)
            self.assertEqual(r['max_future_matched_payment_per_player_chips'],0)
            self.assertEqual(r['base_call_ev_bb'],r['scenarios']['base']['ev_call_bb'])

    def test_joint_candidate_budget(self):
        remaining=[c for c in DECK if c not in H+B]
        from itertools import islice
        entries=[e(list(x)) for x in islice(combinations(remaining,5),142)]
        with self.assertRaisesRegex(ValueError,'candidate budget'):multiway(H,B,[entries,entries])

    def test_invalid_joint_and_scenario(self):
        for ranges in ([],[[e(V)]]*6,[[e(V)],[e(V)]],[[e(H)]],[[e(V,True)]],[[e(V),e(V[::-1])]]):
            with self.assertRaises(ValueError):multiway(H,B,ranges)
        for k,v in [('variant',6),('call_chips',101),('opponent_stacks_chips',[120]),('scenarios',{'bad':[0,121,0,0]}),('scenarios',{'bad':[0,0,0]}),('rake_bps',10001)]:
            s=copy.deepcopy(scenario());s[k]=v
            with self.assertRaises(ValueError):analyze(s)


if __name__=='__main__':unittest.main()
