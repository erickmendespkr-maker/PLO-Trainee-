import unittest
from fractions import Fraction
from math import comb
from test_plo5_pre_post_bridge import fixture
from test_plo5_post_gto_river import BOARD, NUT, BLUFF, CATCH
from plo5_pre_flop_chance import distribution
from plo5_pre_post_bridge import prepare_flop


class PreFlopChanceTests(unittest.TestCase):
    def test_exact_mass_and_bridge(self):
        c,m=fixture();r=distribution(c,m)
        self.assertEqual(r['outcomes'],2*comb(42,3))
        self.assertEqual(sum(Fraction(*x['probability']) for x in r['branches']),1)
        self.assertEqual(r['history_probability'],[1,3])
        boards={tuple(x['flop']):x['probability'] for x in r['branches']}
        for flop in (BOARD[:3],['As','Js','Ts']):
            self.assertEqual(boards[tuple(sorted(flop))],prepare_flop(c,flop,m)['flop_given_history_probability'])
        self.assertTrue(all(not set(f)&set(CATCH) for f in boards))
    def test_single_pair_and_budget(self):
        c,m=fixture();c['ranges']['SB']=c['ranges']['SB'][:1];m[0]=m[0][:1]
        r=distribution(c,m)
        self.assertEqual(r['public_boards'],comb(42,3))
        self.assertTrue(all(x['probability']==[1,comb(42,3)] for x in r['branches']))
        with self.assertRaisesRegex(ValueError,'chance budget'):distribution(c,m,max_outcomes=100)
    def test_zero_action_rejected(self):
        c,m=fixture();m[0]=[dict(x,frequency=0) for x in m[0]]
        with self.assertRaisesRegex(ValueError,'ZERO_ACTION'):distribution(c,m)

if __name__=='__main__':unittest.main()
