import copy
import unittest
from plo5_river_report_audit import verify
from plo5_river_solver import solve as vanilla
from plo5_river_accelerated import solve as accelerated
from plo5_restricted_cache import connect
from test_plo5_river_accelerated_cards import fixture, entry


class ReportAuditTests(unittest.TestCase):
    def setUp(self):
        self.game=fixture();self.report=accelerated(self.game)
    def test_both_solvers(self):
        for solve in (vanilla,accelerated):
            r=verify(self.game,solve(self.game));self.assertTrue(r['policy_math_consistent']);self.assertEqual(r['solver_reruns'],0);self.assertFalse(r['gto_solution'])
    def test_ev_tampering(self):
        r=copy.deepcopy(self.report);r['hero_strategy'][0]['actions'][0]['ev_bb']+=1
        with self.assertRaisesRegex(ValueError,'Action EV'):verify(self.game,r)
    def test_coherent_fake_gap(self):
        r=copy.deepcopy(self.report);r.update(best_response_upper_bb=r['hero_value_bb'],best_response_lower_bb=r['hero_value_bb'],nash_gap_bb=0,gap_fraction_of_pot=0)
        with self.assertRaisesRegex(ValueError,'certificate'):verify(self.game,r)
    def test_opponent_policy(self):
        r=copy.deepcopy(self.report);r['opponent_strategy'][0].update(call_frequency=1.,fold_frequency=0.)
        with self.assertRaises(ValueError):verify(self.game,r)
    def test_roster_and_marginal(self):
        for change in ('duplicate','missing','weight'):
            r=copy.deepcopy(self.report)
            if change=='duplicate':r['hero_strategy'][1]=r['hero_strategy'][0]
            elif change=='missing':r['hero_strategy'].pop()
            else:r['hero_strategy'][0]['joint_marginal']=0.9
            with self.subTest(change=change),self.assertRaises(ValueError):verify(self.game,r)
    def test_blocked_holdings(self):
        self.game['opponent_range'].append(entry('As Kh 6c Td 8c',3))
        r=accelerated(self.game,iterations=1000);self.assertEqual(verify(self.game,r)['legal_joint_deals'],3)
    def test_cache_and_target(self):
        db=connect(':memory:');self.addCleanup(db.close)
        accelerated(self.game,cache=db);r=accelerated(self.game,cache=db);self.assertTrue(r['cache_hit']);verify(self.game,r)
        r=accelerated(self.game,iterations=1,target=0);self.assertFalse(r['target_reached']);verify(self.game,r)
        r['cache_hit']=True
        with self.assertRaises(ValueError):verify(self.game,r)
    def test_identity_and_flags(self):
        for k,v in [('game_sha256','0'*64),('gto_solution',True),('legal_joint_weight',0),('within_one_percent_pot_gap',False),('solver_algorithm','other')]:
            r=copy.deepcopy(self.report);r[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):verify(self.game,r)

if __name__=='__main__':unittest.main()
