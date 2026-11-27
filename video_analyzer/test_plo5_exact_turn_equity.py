import random,unittest
from itertools import combinations
from fractions import Fraction
from math import comb
from plo5_exact_turn_equity import equity,cliques5
from plo5_exact_river_equity import DECK,equity as river_equity
from plo5_rank_audit import oracle


def rank(h,b):return max(oracle(x+y) for x in combinations(h,2) for y in combinations(b,3))

class ExactTurnTests(unittest.TestCase):
    def test_cliques(self):
        rng=random.Random(210)
        for n in range(5,12):
            for chance in (0,.3,.8,1):
                e=[sum(1<<j for j in range(i+1,n) if rng.random()<chance) for i in range(n)]
                expected=sum(all(e[i]&(1<<j) for i,j in combinations(v,2)) for v in combinations(range(n),5))
                self.assertEqual(cliques5(e),expected)
    def test_oracle(self):
        rng=random.Random(619)
        for _ in range(12):
            cards=rng.sample(DECK,17);h,b,pool=tuple(cards[:5]),tuple(cards[5:9]),tuple(cards[9:]);dead=[c for c in DECK if c not in cards]
            counts=[0,0,0];r=equity(h,b,dead)
            for river in pool:
                board=b+(river,);hr=rank(h,board);local=[0,0,0]
                for o in combinations([c for c in pool if c!=river],5):
                    v=rank(o,board);local[0 if hr>v else 1 if hr==v else 2]+=1
                counts=[a+b for a,b in zip(counts,local)];row=next(q for q in r['by_river'] if q['river']==river);self.assertEqual([row[k] for k in ('wins','ties','losses')],local)
            self.assertEqual([r[k] for k in ('wins','ties','losses')],counts);self.assertEqual(Fraction(**r['equity_fraction']),Fraction(2*counts[0]+counts[1],2*sum(counts)))
    def test_unbeatable(self):
        r=equity('As Ks 2c 3d 4h'.split(),'Qs Js Ts 8d'.split());self.assertEqual(r['joint_outcomes'],43*comb(42,5));self.assertEqual(r['wins'],r['joint_outcomes']);self.assertEqual(r['equity'],1)
    def test_river_agreement(self):
        h='Ks Js 8s 6c 5c'.split();b='7d Ac 3d 6d'.split();r=equity(h,b)
        for c in ('2h','Ad','9s'):
            a=next(q for q in r['by_river'] if q['river']==c);z=river_equity(h,b+[c]);self.assertEqual([a[k] for k in ('wins','ties','losses')],[z[k] for k in ('wins','ties','losses')])
    def test_invalid(self):
        for h,b,d in ((DECK[:6],DECK[6:10],[]),(DECK[:5],DECK[5:10],[]),(DECK[:5],DECK[4:8],[]),(DECK[:5],DECK[5:9],[DECK[0]]),(DECK[:5],DECK[5:9],DECK[9:47])):
            with self.assertRaises(ValueError):equity(h,b,d)
    def test_minimum_pool(self):
        r=equity(DECK[:5],DECK[5:9],DECK[15:]);self.assertEqual(r['joint_outcomes'],6);self.assertFalse(r['gto_solution'])
if __name__=='__main__':unittest.main()
