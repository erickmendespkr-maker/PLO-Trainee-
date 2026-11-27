import os
import unittest
from fractions import Fraction
from test_plo5_post_gto_multiway import fixture
from plo5_post_gto_multiway import solve


class ContinuationTests(unittest.TestCase):
    def test_fixed_root_conditional_values(self):
        c=fixture(3,2,4);r=solve(c,2,rake_on_fold=False,include_deal_values=True)
        rows=r['conditional_values']['rows'];self.assertEqual(len(rows),8)
        self.assertEqual(sum(Fraction(*x['probability']) for x in rows),1)
        for p in range(3):
            self.assertAlmostEqual(sum(float(Fraction(*x['probability']))*x['values_bb'][p] for x in rows),r['values_bb'][p],places=9)
        for row in rows:self.assertAlmostEqual(sum(row['values_bb']),2,places=9)
        self.assertFalse(r['conditional_values']['preflop_continuation_certified'])
        self.assertNotIn('conditional_values',solve(fixture(3),1,rake_on_fold=False))
    def test_asymmetric_and_flop(self):
        c=fixture(3);c['stacks']={'SB':1,'BB':2,'UTG':3};c['pot']=3
        a=solve(c,1,rake_on_fold=False);self.assertAlmostEqual(sum(a['values_bb']),3)
        c=fixture(3,street=3);r=solve(c,1,rake_on_fold=False,cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
        self.assertEqual(r['chance_outcomes'],1122);self.assertAlmostEqual(sum(r['values_bb']),2)
        self.assertTrue(any(len(x['board'])==5 for x in r['tree']))
        self.assertEqual(len([x for x in r['policy'] if x['node']==0]),1)

if __name__=='__main__':unittest.main()
