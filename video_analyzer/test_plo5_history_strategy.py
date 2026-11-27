import os
import tempfile
import unittest
from pathlib import Path
from plo5_history_strategy import prepare,review
from test_plo5_history_replay import HEADER,run
from plo5_pre_gto_context import cards

H=cards('As Ks Qh Jd Tc'.split());V=cards('Ah Kh Qs Jc Td'.split());ALT=cards('7c 8d 9h Ts Js'.split())
R={'SB':[dict(cards=H,weight=1)],'BB':[dict(cards=V,weight=1),dict(cards=ALT,weight=1)]}
RAW=HEADER.replace('$200 in chips','$4 in chips')+'''Hero: calls $1
Villain: checks
*** FLOP *** [2c 3d 4h]
Villain: checks
Hero: checks
*** TURN *** [2c 3d 4h] [5s]
Villain: checks
Hero: checks
*** RIVER *** [2c 3d 4h 5s] [6s]
Villain: bets $2 and is all-in
Hero: calls $2 and is all-in
*** SHOW DOWN ***
Hero: shows [As Ks Qh Jd Tc]
Villain: shows [Ah Kh Qs Jc Td]
Hero collected $4 from pot
Villain collected $4 from pot
*** SUMMARY ***
Total pot $8 | Rake $0
'''

def record(raw=RAW):return dict(id='1',hero='Hero',holding=H,raw=raw)
KW=dict(rake_bps=0,rake_cap=0,rake_on_fold=False)
class HistoryStrategyTests(unittest.TestCase):
    def test_river_root(self):
        r=prepare(record(),10,R,**KW);c=r['context']
        self.assertEqual(c['board'],['2c','3d','4h','5s','6s']);self.assertEqual(c['pot'],400)
        self.assertEqual(c['stacks'],{'BB':200,'SB':200});self.assertEqual(r['history'],[['BB','bet',200]]);self.assertEqual(r['action'],['call',200])
    def test_no_future_board_or_showdown_range(self):
        a=prepare(record(),4,R,**KW)
        raw=RAW.replace('[6s]','[6c]').replace('[2c 3d 4h 5s 6s]','[2c 3d 4h 5s 6c]')
        b=prepare(record(raw),4,R,**KW)
        self.assertEqual(a,b);self.assertEqual(len(a['context']['board']),3);self.assertEqual(a['context']['ranges'],R)
    def test_invalid(self):
        for i in (0,2,3,99):
            with self.assertRaises(ValueError):prepare(record(),i,R,**KW)
        with self.assertRaises(ValueError):prepare(record(),10,{'SB':[dict(cards=ALT,weight=1)],'BB':R['BB']},**KW)
    def test_native_review(self):
        with tempfile.TemporaryDirectory() as t:
            r=review(Path(t)/'cache.sqlite',record(),10,R,iterations=100,cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'),**KW)
            self.assertAlmostEqual(r['pot_odds_gross'],.25);self.assertIsNotNone(r['ev_bb']);self.assertFalse(r['strategy_authorized'])
            self.assertFalse(r['range_provenance_verified']);self.assertEqual(r['action'],['call',200])
if __name__=='__main__':unittest.main()
