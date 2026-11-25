"""Differential checks using actual five-card evaluator and original prepare()."""
import copy
import unittest
from plo5_river_solver import solve as original, prepare
from plo5_river_accelerated import solve
from plo5_restricted_cache import connect


def entry(cards,weight=1):return {'cards':cards.split(),'weight':weight}
def fixture():
    return dict(variant=5,board='2c 4d 7h 9s Jc'.split(),pot_chips=100,bet_chips=100,
                hero_stack_chips=200,opponent_stack_chips=200,bb_chips=10,
                hero_range=[entry('As Ad 3c 5d 8h'),entry('Qs Qd 3s 5h 8d',2)],
                opponent_range=[entry('Ks Kd 3d 5c 8s')])

class CardTests(unittest.TestCase):
    def test_polar(self):
        g=fixture();a=original(g,10000);b=solve(g)
        self.assertEqual(set(a)-set(b),set());self.assertEqual(a['game_sha256'],b['game_sha256'])
        self.assertLessEqual(b['gap_fraction_of_pot'],.01)
        self.assertAlmostEqual(a['hero_value_bb'],b['hero_value_bb'],delta=.1)
        self.assertEqual(b['legal_joint_deals'],2)
    def test_blockers(self):
        g=fixture();g['opponent_range'].append(entry('As Kh 6c Td 8c',3))
        b=solve(g,iterations=1000)
        self.assertEqual(b['legal_joint_deals'],3);self.assertEqual(b['input_joint_weight'],12);self.assertEqual(b['legal_joint_weight'],9)
    def test_single_winner(self):
        g=fixture();g['hero_range']=g['hero_range'][:1]
        b=solve(g,iterations=1000);self.assertAlmostEqual(b['hero_value_bb'],10.,delta=.1)
    def test_cache_game_identity(self):
        g=fixture();db=connect(':memory:');self.addCleanup(db.close)
        a=solve(g,cache=db);b=solve(g,cache=db)
        self.assertFalse(a.pop('cache_hit'));self.assertTrue(b.pop('cache_hit'));self.assertEqual(a,b)
        other=copy.deepcopy(g);other['bb_chips']=20
        c=solve(other,cache=db);self.assertTrue(c['cache_hit']);self.assertNotEqual(c['game_sha256'],a['game_sha256']);self.assertAlmostEqual(c['hero_value_bb'],a['hero_value_bb']/2)
    def test_invalid(self):
        for key,value in [('variant',6),('bet_chips',101),('hero_stack_chips',99),('board',['2c']*5),('bb_chips',0)]:
            g=fixture();g[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):solve(g)

if __name__=='__main__':unittest.main()
