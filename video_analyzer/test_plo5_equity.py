import unittest
from itertools import combinations
from fractions import Fraction
from plo5_equity import equity, known_equity, sensitivity, DECK
from test_plo5_evaluator import oracle_omaha

H=['As','Ks','2c','3d','4h']
B=['Qs','Js','Ts','9d','8c']
V=['Ac','Ad','Kh','Kd','7c']
T1=['Ac','6d','Td','Jh','Qs']
T2=['Ad','6c','Th','Jd','Qh']
T3=['Kd','Qc','Ts','Jc','8h']
TB=['2c','3d','4h','5s','9c']


def entry(cards,weight=1):
    return {'cards':cards,'weight':weight}


class EquityTests(unittest.TestCase):
    def test_exact_royal_and_tie(self):
        r=known_equity(H,B,V)
        self.assertEqual((r['equity'],r['evaluated_states'],r['sampling_ci95']),(1,1,[1,1]))
        self.assertEqual(known_equity(T1,TB,T2)['equity_fraction'],{'numerator':1,'denominator':2})
        self.assertFalse(r['gto_solution'])

    def test_weighted_river_blockers_and_normalization(self):
        r=equity(T1,TB,[entry(T2,3),entry(T3,1),entry(T1,6)])
        self.assertEqual(r['equity_fraction'],{'numerator':5,'denominator':8})
        self.assertEqual(r['outcome_mass'],{'win':1,'tie':3,'loss':0})
        self.assertEqual(r['range_audit']['blocked_weight_fraction'],.6)
        self.assertEqual(r['range_audit']['legal_combos'],2)
        self.assertEqual(r['mass_denominator'],4)

    def test_turn_exact_against_independent_oracle(self):
        board=['Qs','Js','9d','8c']
        remain=[c for c in DECK if c not in H+V+board]
        counts=[0,0,0]
        for river in remain:
            a=oracle_omaha(H,board+[river]);b=oracle_omaha(V,board+[river])
            counts[0 if a>b else 1 if a==b else 2]+=1
        r=known_equity(H,board,V)
        self.assertEqual(r['evaluated_states'],38)
        self.assertEqual(list(r['outcome_mass'].values()),counts)
        q=Fraction(2*counts[0]+counts[1],76)
        self.assertEqual(r['equity_fraction'],{'numerator':q.numerator,'denominator':q.denominator})

    def test_flop_weighted_exact_oracle(self):
        board=TB[:3]; entries=[entry(T2,3),entry(T3,1)]
        counts=[0,0,0]
        for e in entries:
            for extra in combinations([c for c in DECK if c not in T1+board+e['cards']],2):
                a=oracle_omaha(T1,board+list(extra)); b=oracle_omaha(e['cards'],board+list(extra))
                counts[0 if a>b else 1 if a==b else 2]+=e['weight']
        r=equity(T1,board,entries)
        self.assertEqual(r['evaluated_states'],1482)
        self.assertEqual(list(r['outcome_mass'].values()),counts)

    def test_seeded_mc_and_ci(self):
        entries=[entry(T2,3),entry(T3,1)]
        r=equity(T1,TB,entries,method='monte_carlo',trials=600,seed=42)
        self.assertEqual(r,equity(T1,TB,list(reversed(entries)),method='monte_carlo',trials=600,seed=42))
        self.assertLessEqual(r['sampling_ci95'][0],.625)
        self.assertGreaterEqual(r['sampling_ci95'][1],.625)
        self.assertEqual(sum(r['outcome_mass'].values()),600)
        self.assertFalse(r['range_uncertainty_included_in_ci'])

    def test_preflop_budget_and_auto(self):
        r=known_equity(H,[],V,trials=40,seed=7)
        self.assertEqual(r['method'],'weighted_monte_carlo')
        self.assertEqual(r['possible_states'],850668)
        with self.assertRaises(ValueError):known_equity(H,[],V,method='exact')
        self.assertEqual(known_equity(H,B,V,method='auto')['method'],'exact_weighted_runouts')

    def test_sensitivity_not_ci(self):
        r=sensitivity(T1,TB,{'tie':[entry(T2)],'win':[entry(T3)]})
        self.assertEqual(r['estimate_span'],[.5,1.])
        self.assertFalse(r['span_is_confidence_interval'])

    def test_invalid_inputs(self):
        for h,b,e in [(H[:4],B,[entry(V)]),(H+['2d'],B,[entry(V)]),(H,B[:2],[entry(V)]),
                      (H,B,[entry(H)]),(H,B,[entry(V),entry(list(reversed(V)))]),
                      (H,B,[entry(V,True)]),(H,B,[entry(V,0)]),(H,B,[entry(V,1.5)]),
                      (H,['As']+B[1:],[entry(V)]),(H,B,[entry(V+['2d'])])]:
            with self.subTest(h=h,b=b,e=e),self.assertRaises(ValueError):equity(h,b,e)
        for opt in ({'max_exact':0},{'trials':True},{'seed':-1},{'method':'bad'}):
            with self.assertRaises(ValueError):equity(H,B,[entry(V)],**opt)


if __name__=='__main__':unittest.main()
