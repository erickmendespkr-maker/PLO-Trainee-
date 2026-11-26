import unittest
from pathlib import Path
import tempfile
from PIL import Image
from plo5_event_card_consensus import combine, read_crop
from plo5_event_capture import Tracker, ROIS
import numpy as np


def observation(hero=None,board=None):
    hero=hero or ['Ac','Kd','Qh','Js','Tc'];board=[] if board is None else board
    def slots(cards):return [{'card':c,'status':'candidate_unverified' if c else 'felt_empty_candidate'} for c in cards+[None]*(5-len(cards))]
    return {'platform':'suprema','hero_slots':slots(hero),'board_slots':slots(board)}

class TemporalTests(unittest.TestCase):
    def test_agreement(self):
        r=combine(observation(),observation());self.assertEqual(r['hero_cards'],['Ac','Kd','Qh','Js','Tc']);self.assertEqual(r['board_cards'],[]);self.assertFalse(r['cards_verified'])
    def test_disagreement(self):
        r=combine(observation(),observation(['2c','Kd','Qh','Js','Tc']));self.assertIsNone(r['hero_cards']);self.assertIsNone(r['hero_slots'][0]['card'])
    def test_missing(self):
        a=observation();a['hero_slots'][0]={'card':None,'status':'uncertain'};self.assertIsNone(combine(a,observation())['hero_cards'])
    def test_collision(self):
        a=observation(board=['Ac','2d','3h']);r=combine(a,a);self.assertIsNone(r['hero_cards']);self.assertIsNone(r['board_cards'])
    def test_board_gap(self):
        a=observation(board=['2c','3d','4h']);b=observation(board=['2c','5d','4h']);self.assertIsNone(combine(a,b)['board_cards'])
    def test_platform_mismatch(self):
        a=observation();b=observation();b['platform']='pppoker'
        with self.assertRaises(ValueError):combine(a,b)
    def test_hash_and_path(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'prints').mkdir();Image.new('RGB',(372,696)).save(p/'prints/0001_after.png')
            with self.assertRaisesRegex(ValueError,'hash'):read_crop(p,{'file':'prints/0001_after.png','sha256':'bad'},1,'after',1)
            with self.assertRaisesRegex(ValueError,'path'):read_crop(p,{'file':'../bad','sha256':'bad'},1,'after',1)
    def test_stable_peer_distinct(self):
        a=np.zeros((696,372,3),dtype=np.uint8);b=a.copy();x,y,u,v=ROIS['suprema']['board'];b[y:v,x:u]=255
        t=Tracker(8);self.assertIsNone(t.step(4,'suprema',a,0,0)[0][-1]);t.step(4,'suprema',b,1,1);e=t.step(4,'suprema',b,2,2)[0];self.assertEqual({e[4][0],e[5][0]},{1,2})
if __name__=='__main__':unittest.main()
