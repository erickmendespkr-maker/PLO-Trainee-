import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import numpy as np
from plo5_opponent_labels import ANCHORS,SEATS,PROFILE,dims,load_bank,observe,combine,run
from plo5_mixed_money import STARTS

class OpponentTests(unittest.TestCase):
    def model(self,p):
        w,h=dims(p);return np.random.default_rng(11).integers(0,256,(h,w),dtype=np.uint8)
    def test_seat_geometry(self):
        for p,anchors in ANCHORS.items():
            g=self.model(p);im=Image.new('RGB',(1504,696))
            for x,y in anchors:im.paste(Image.fromarray(g).convert('RGB'),(STARTS[2]+x,y))
            with patch('plo5_opponent_labels.detect',return_value=p):r=observe(im,3,{p:{'fold':[g]}})
            self.assertEqual([q['seat'] for q in r['opponents']],list(SEATS));self.assertTrue(all(q['visible_label_candidate']=='fold' and not q['action_verified'] for q in r['opponents']))
    def test_ambiguity_and_absence(self):
        p='pppoker';g=self.model(p);im=Image.new('RGB',(1504,696));x,y=ANCHORS[p][0];im.paste(Image.fromarray(g).convert('RGB'),(x,y))
        with patch('plo5_opponent_labels.detect',return_value=p):r=observe(im,1,{p:{'fold':[g],'call':[g]}})
        self.assertTrue(all(q['visible_label_candidate'] is None for q in r['opponents']))
    def observation(self,label):
        return {'platform':'suprema','table_id':1,'opponents':[{'seat':s,'visible_label_candidate':label} for s in SEATS]}
    def test_pair_marker_is_not_action(self):
        a=self.observation('sb');r=combine(a,a);self.assertTrue(all(q['label_kind']=='marker' and not q['action_verified'] and q['action_amount_bb'] is None for q in r))
    def test_pair_conflict(self):
        self.assertTrue(all(q['label_candidate'] is None for q in combine(self.observation('fold'),self.observation('raise'))))
        with self.assertRaises(ValueError):combine(self.observation('fold'),dict(self.observation('fold'),table_id=2))
    def test_bank(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'b.json';data={'profile':PROFILE,'templates':{k:{'fold':[self.model(k).tobytes().hex()]} for k in ANCHORS}};p.write_text(json.dumps(data));self.assertEqual(set(load_bank(p)),set(ANCHORS));data['profile']='other';p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_bank(p)
    def test_invalid_geometry(self):
        with self.assertRaises(ValueError):observe(Image.new('RGB',(372,696)),1,{})
    def test_unknown_platform(self):
        with patch('plo5_opponent_labels.detect',return_value=None):self.assertEqual(observe(Image.new('RGB',(1504,696)),1,{})['opponents'],[])
if __name__=='__main__':unittest.main()
