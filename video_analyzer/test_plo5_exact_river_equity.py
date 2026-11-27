import random,unittest
from itertools import combinations
from fractions import Fraction
from math import comb
from plo5_exact_river_equity import equity,DECK
from plo5_rank_audit import oracle


def rank(h,b):return max(oracle(x+y) for x in combinations(h,2) for y in combinations(b,3))

class ExactRiverTests(unittest.TestCase):
    def test_royal_unbeatable(self):
        r=equity('As Ks 2c 3d 4h'.split(),'Qs Js Ts 8d 9c'.split())
        self.assertEqual(r['wins'],comb(42,5));self.assertEqual(r['equity'],1);self.assertFalse(r['gto_solution'])
    def test_quads_board_not_playable(self):
        r=equity('2c 3c 4c 5c 6c'.split(),'As Ah Ad Ac Ks'.split())
        self.assertLess(r['equity'],1);self.assertEqual(r['opponent_holdings'],850668)
    def test_independent_oracle(self):
        rng=random.Random(81421)
        for _ in range(24):
            cards=rng.sample(DECK,18);h,b,pool=tuple(cards[:5]),tuple(cards[5:10]),tuple(cards[10:]);dead=[c for c in DECK if c not in cards];hr=rank(h,b);counts=[0,0,0]
            for o in combinations(pool,5):
                v=rank(o,b);counts[0 if hr>v else 1 if hr==v else 2]+=1
            r=equity(h,b,dead);self.assertEqual([r[k] for k in ('wins','ties','losses')],counts)
            self.assertEqual(Fraction(**r['equity_fraction']),Fraction(2*counts[0]+counts[1],2*sum(counts)))
    def test_only_five_remaining(self):
        h=DECK[:5];b=DECK[5:10];r=equity(h,b,DECK[15:]);self.assertEqual(r['opponent_holdings'],1)
    def test_invalid_input(self):
        for h,b,d in [(DECK[:6],DECK[6:11],[]),(DECK[:5],DECK[5:9],[]),(DECK[:5],DECK[4:9],[]),(DECK[:5],DECK[5:10],[DECK[0]]),(DECK[:5],DECK[5:10],DECK[10:48])]:
            with self.assertRaises(ValueError):equity(h,b,d)
    def test_permutation(self):
        h=DECK[:5];b=DECK[5:10];d=DECK[20:];a=equity(h,b,d);z=equity(h[::-1],b[::-1],d[::-1]);self.assertEqual(a['equity_fraction'],z['equity_fraction'])
if __name__=='__main__':unittest.main()
