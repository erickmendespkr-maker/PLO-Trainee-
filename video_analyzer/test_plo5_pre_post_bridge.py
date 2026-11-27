import os
import unittest
from fractions import Fraction
from math import comb
from test_plo5_post_gto_river import NUT, BLUFF, CATCH, BOARD
from plo5_pre_post_bridge import prepare_flop, solve_observed_flop


def fixture():
    c=dict(variant=5,stacks={'SB':4,'BB':4},sb=1,bb=2,rake_bps=0,rake_cap=0,rake_on_fold=False,
           history=[dict(position='SB',action='call',amount=1),dict(position='BB',action='check',amount=0)],
           ranges={'SB':[dict(cards=NUT,weight=1),dict(cards=BLUFF,weight=2)],'BB':[dict(cards=CATCH,weight=1)]},
           tree_version='test',continuation_version='test')
    maps=[[dict(cards=NUT,frequency=.5),dict(cards=BLUFF,frequency=.25)],[dict(cards=CATCH,frequency=1)]]
    return c,maps


class BridgeTests(unittest.TestCase):
    def test_replay_and_exact_weights(self):
        c,m=fixture();b=prepare_flop(c,BOARD[:3],m);p=b['post_context']
        self.assertEqual((p['seats'],p['actor'],p['pot'],p['stacks']),(['BB','SB'],'BB',4,{'BB':2,'SB':2}))
        self.assertEqual(b['history_probability'],[1,3]);self.assertEqual(Fraction(*b['flop_given_history_probability']),Fraction(1,comb(42,3)))
        self.assertEqual([x['weight'] for x in b['joint']],[1,1]);self.assertTrue(all(x['holdings'][0]==sorted(CATCH) for x in b['joint']))
    def test_public_blocker_after_action(self):
        c,m=fixture();b=prepare_flop(c,['As','Js','Ts'],m)
        self.assertEqual(len(b['joint']),1);self.assertEqual(b['joint'][0]['holdings'][1],sorted(BLUFF))
        self.assertEqual(Fraction(*b['flop_given_history_probability']),Fraction(1,2*comb(42,3)))
        self.assertEqual(b['history_probability'],[1,3])
    def test_fail_closed(self):
        c,m=fixture()
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_POLICY'):prepare_flop(c,BOARD[:3],[m[0][:1],m[1]])
        with self.assertRaisesRegex(ValueError,'ZERO_ACTION'):prepare_flop(c,BOARD[:3],[[dict(x,frequency=0) for x in m[0]],m[1]])
        with self.assertRaisesRegex(ValueError,'ZERO_FLOP'):prepare_flop(c,[CATCH[0],'Js','Ts'],m)
        with self.assertRaises(ValueError):prepare_flop(dict(c,history=c['history'][:1]),BOARD[:3],m[:1])
    def test_identity(self):
        c,m=fixture();a=prepare_flop(c,BOARD[:3],m)
        self.assertEqual(a['bridge_key'],prepare_flop(c,BOARD[:3][::-1],[m[0][::-1],m[1]])['bridge_key'])
        self.assertNotEqual(a['bridge_key'],prepare_flop(c,BOARD[:3],[[dict(x,frequency=.5) for x in m[0]],m[1]])['bridge_key'])
    def test_end_to_end(self):
        c,m=fixture();r=solve_observed_flop(c,BOARD[:3],m,iterations=1,cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
        self.assertEqual(r['seats'],['BB','SB']);self.assertAlmostEqual(sum(r['net_from_hand_start_bb']),0,places=9)
        for p in range(2):
            v=sum(float(Fraction(*x['probability']))*x['net_from_hand_start_bb'][p] for x in r['conditional_net_rows'])
            self.assertAlmostEqual(v,r['net_from_hand_start_bb'][p],places=9)
        self.assertFalse(r['preflop_continuation_certified'])

if __name__=='__main__':unittest.main()
