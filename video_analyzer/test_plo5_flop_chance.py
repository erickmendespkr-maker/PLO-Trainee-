import unittest
from collections import defaultdict
from fractions import Fraction
from test_plo5_post_gto_river import context, polar, NUT, CATCH, BLUFF, BOARD
from plo5_post_gto_flop_chance import ordered_runouts
from plo5_post_gto_turn_chance import distribution


class FlopChanceTests(unittest.TestCase):
    def test_order_and_mass(self):
        c=context([(NUT,1)],[(CATCH,1)],board=BOARD[:3]);rows=list(ordered_runouts(c))
        self.assertEqual(len(rows),1482);self.assertEqual(sum(r[4] for r in rows),1)
        paths={(r[2],r[3]) for r in rows};self.assertEqual(len(paths),1482)
        for h,k,t,r,p in rows:
            self.assertNotIn(t,set(h)|set(k)|set(c['board']));self.assertNotIn(r,set(h)|set(k)|set(c['board'])|{t})
            self.assertIn((r,t),paths);self.assertEqual(p,Fraction(1,1482))
    def test_consistency_with_turn(self):
        c=dict(polar(),board=BOARD[:3]);m=defaultdict(Fraction);prior=defaultdict(Fraction)
        for h,k,t,r,p in ordered_runouts(c):
            prior[h]+=p
            if t==BOARD[3]:m[r]+=p
        self.assertEqual(prior,{tuple(sorted(NUT)):Fraction(1,3),tuple(sorted(BLUFF)):Fraction(2,3)})
        mass=sum(m.values());self.assertEqual(mass,Fraction(1,39))
        turn=distribution(dict(c,board=BOARD[:4]))
        self.assertEqual({r:p/mass for r,p in m.items()},{b['card']:Fraction(*b['probability']) for b in turn['branches']})
    def test_budgets(self):
        c=dict(polar(),board=BOARD[:3])
        with self.assertRaises(ValueError):list(ordered_runouts(c,max_outcomes=2963))
        with self.assertRaises(ValueError):list(ordered_runouts(polar()))


if __name__=='__main__':unittest.main(verbosity=2)
