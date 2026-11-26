import unittest
from unittest.mock import patch
from PIL import Image
import base64,zlib
from plo5_hero_actions import BOXES,TEMPLATES,observe,episodes
from plo5_mixed_money import STARTS

class HeroActionsTests(unittest.TestCase):
    def test_all_templates(self):
        for p,models in TEMPLATES.items():
            a,b,c,d=BOXES[p]
            for label,code in models.items():
                im=Image.new('RGB',(1504,696));im.paste(Image.frombytes('L',(c-a,d-b),zlib.decompress(base64.b64decode(code))).convert('RGB'),(STARTS[2]+a,b))
                with patch('plo5_hero_actions.detect',return_value=p):r=observe(im,3)
                self.assertEqual(r['hero_action_candidate'],label);self.assertFalse(r['action_verified'])
    def test_blank(self):
        with patch('plo5_hero_actions.detect',return_value='pppoker'):self.assertIsNone(observe(Image.new('RGB',(1504,696)),1)['hero_action_candidate'])
    def test_unknown_platform(self):
        with patch('plo5_hero_actions.detect',return_value=None):self.assertIsNone(observe(None,1)['hero_action_candidate'])
    def sample(self,t,label='fold',platform='pppoker'):
        return {'pts':str(t),'file':str(t)+'.png','hero_actions':[{'table_id':i,'platform':platform,'hero_action_candidate':label if i==1 else None} for i in range(1,5)]}
    def test_persistent_labels(self):
        r=episodes([self.sample(1),self.sample(2),self.sample(3)]);self.assertEqual(len(r),1);self.assertEqual(r[0]['samples'],3);self.assertFalse(r[0]['action_verified'])
    def test_gap_and_unknown(self):
        r=episodes([self.sample(1),self.sample(3),self.sample(4,None),self.sample(5)]);self.assertEqual(len(r),3)
    def test_platform_or_label_change(self):
        self.assertEqual(len(episodes([self.sample(1),self.sample(2,'bet'),self.sample(3,'fold','suprema')])),3)
    def test_duplicate(self):
        with self.assertRaises(ValueError):episodes([self.sample(1),self.sample(1)])
if __name__=='__main__':unittest.main()
