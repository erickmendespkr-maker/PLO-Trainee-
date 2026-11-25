import unittest
from unittest.mock import patch
from types import ModuleType
import sys
from plo5_river_accelerated import solve, render
from plo5_restricted_cache import connect

H=[(('3c','5d','8h','Ad','As'),1),(('3s','5h','8d','Qd','Qs'),2)]
V=[(('3d','5c','8s','Kd','Ks'),1)]
P=[(0,0,1/3,1.,2.),(1,0,2/3,0.,-1.)]
GAME={'variant':5,'bet_chips':100}
PREPARED=(H,V,P,3,3,100,10)

class AcceleratedTests(unittest.TestCase):
    def setUp(self):
        self.core=ModuleType('plo5_river_solver');self.core.prepare=lambda game,it:PREPARED
        self.patcher=patch.dict(sys.modules,{'plo5_river_solver':self.core});self.patcher.start();self.addCleanup(self.patcher.stop)
    def test_report(self):
        r=solve(GAME);self.assertTrue(r['target_reached']);self.assertLessEqual(r['nash_gap_bb'],.1)
        self.assertAlmostEqual(r['hero_value_bb'],5.,delta=.1);self.assertEqual(r['hero_strategy'][0]['actions'][1]['extra_chips'],100)
        self.assertFalse(r['gto_solution']);self.assertFalse(r['video_verified']);self.assertFalse(r['production_strategy_authorized'])
    def test_cache(self):
        db=connect(':memory:');self.addCleanup(db.close);a=solve(GAME,cache=db);b=solve(GAME,cache=db)
        self.assertFalse(a.pop('cache_hit'));self.assertTrue(b.pop('cache_hit'));self.assertEqual(a,b)
    def test_unreached(self):
        r=solve(GAME,iterations=1,target=0);self.assertFalse(r['target_reached']);self.assertFalse(r['within_one_percent_pot_gap'])
    def test_marginals(self):
        r=solve(GAME);self.assertAlmostEqual(sum(x['joint_marginal'] for x in r['hero_strategy']),1.)
        self.assertAlmostEqual(sum(x['joint_marginal'] for x in r['opponent_strategy']),1.)
        self.assertAlmostEqual(r['best_response_upper_bb']-r['best_response_lower_bb'],r['nash_gap_bb'])
    def test_invalid_policy(self):
        with self.assertRaises(ValueError):render(GAME,PREPARED,{'hero_bet_probabilities':[2.,0.],'opponent_call_probabilities':[0.]})
    def test_prepare_error(self):
        def fail(*args):raise ValueError('invalid game')
        self.core.prepare=fail
        with self.assertRaisesRegex(ValueError,'invalid game'):solve(GAME)

if __name__=='__main__':unittest.main()
