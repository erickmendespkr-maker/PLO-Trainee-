import unittest
from plo5_candidate_history import plan,run
from test_plo5_preflop_roster import sample
from pathlib import Path
import tempfile,json

class HistoryTests(unittest.TestCase):
    def frames(self,boards):
        out=[]
        for i,b in enumerate(boards,1):
            f=sample(i);f['cards'][0]['board_cards']=b;out.append(f)
        return out
    def test_supported_streets_join(self):
        b=['2c','3d','4h'];f=self.frames([[],[],b,b,b+['5s'],b+['5s']]);_,g,index=plan(f)
        self.assertEqual(len(g),1);self.assertEqual(len(g[0]['runs']),3);self.assertEqual(len(index),6);self.assertFalse(g[0]['complete_hand']);self.assertFalse(g[0]['strategy_authorized'])
    def test_uncertainty_separates(self):
        _,g,index=plan(self.frames([[],[],None,[],[]]));self.assertEqual(len(g),2);self.assertEqual(len(index),4)
    def test_gap_separates(self):
        f=self.frames([[],[]]);f[1]['pts']='3';_,g,_=plan(f);self.assertEqual(len(g),2)
    def test_new_hand_separates(self):
        f=self.frames([[],[],[],[]]);
        for r in f[2:]:r['cards'][0]['hero_cards']=['2c','3d','4h','5s','6c'];r['seats'][0]['dealer_seat_candidate']='upper_right'
        _,g,_=plan(f);self.assertEqual(len(g),2)
    def test_single_sample_not_joined(self):
        _,g,_=plan(self.frames([[],['2c','3d','4h'],['2c','3d','4h']]));self.assertEqual(len(g),2)
    def test_skipped_street_not_joined(self):
        b=['2c','3d','4h','5s'];_,g,_=plan(self.frames([[],[],b,b]));self.assertEqual(len(g),2)
    def test_wrong_variant(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'manifest.json').write_text(json.dumps({'variant':6,'status':'MIXED_LAYOUT_DISPLAY_REVIEW_ONLY'}))
            with self.assertRaisesRegex(ValueError,'Wrong manifest'):run(d,'unused')
if __name__=='__main__':unittest.main()
