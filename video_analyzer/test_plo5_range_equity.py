import unittest,random,math
from plo5_range_equity import estimate,make_range
from plo5_exact_river_equity import DECK,equity
from collections import Counter

H='Ks Js 8s 6c 5c'.split();B='7d Ac 3d 6d 9s'.split();U={'kind':'uniform'}

class RangeTests(unittest.TestCase):
    def test_reproducible(self):
        a=estimate(H,B[:3],U,trials=200,seed=9);self.assertEqual(a,estimate(H,B[:3],U,trials=200,seed=9));self.assertEqual(a['wins']+a['ties']+a['losses'],200)
    def test_rank_count_uniform_support(self):
        pool=tuple(c for c in DECK if c not in H+B);draw,n,_=make_range(pool,{'kind':'rank_count','rank':'A','min':2,'max':4});self.assertEqual(n,3*math.comb(39,3)+math.comb(39,2));rng=random.Random(1)
        for _ in range(100):self.assertGreaterEqual(sum(c[0]=='A' for c in draw(rng)),2)
    def test_weighted_blockers(self):
        pool=tuple(c for c in DECK if c not in H+B);spec={'kind':'weighted_holdings','holdings':[{'cards':list(pool[:5]),'weight':1},{'cards':list(pool[5:10]),'weight':3},{'cards':H,'weight':100}]};draw,n,b=make_range(pool,spec);self.assertEqual((n,b),(2,1));rng=random.Random(2);c=Counter(draw(rng) for _ in range(2000));self.assertTrue(1400<c[tuple(sorted(pool[5:10]))]<1600)
    def test_unbeatable(self):
        r=estimate('As Ks 2c 3d 4h'.split(),'Qs Js Ts 8d'.split(),U,trials=200);self.assertEqual(r['equity'],1);self.assertEqual(r['hoeffding_95_interval'][1],1)
    def test_exact_river_inside_interval(self):
        r=estimate(H,B,U,trials=4000,seed=121);a,z=r['hoeffding_95_interval'];self.assertLessEqual(a,equity(H,B)['equity']);self.assertGreaterEqual(z,equity(H,B)['equity'])
    def test_invalid(self):
        for h,b,s in [(H+['2c'],B,U),(H,B[:2],U),(H,B+[H[0]],U),(H,B,{'kind':'rank_count','rank':'A','min':4,'max':4}),(H,B,{'kind':'weighted_holdings','holdings':[{'cards':H,'weight':1}]}),(H,B,{'kind':'weighted_holdings','holdings':[{'cards':DECK[:5],'weight':0}]})]:
            with self.assertRaises(ValueError):estimate(h,b,s,trials=100)
    def test_preflop(self):
        r=estimate(H,[],{'kind':'rank_count','rank':'A','min':2,'max':2},trials=200);self.assertEqual(r['legal_range_holdings'],math.comb(4,2)*math.comb(43,3));self.assertFalse(r['gto_solution'])
if __name__=='__main__':unittest.main()
