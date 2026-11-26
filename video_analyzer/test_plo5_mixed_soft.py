import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
from plo5_card_review import CardReader,segments
from plo5_mixed_review import run
from plo5_suprema_soft import PROFILE
from test_plo5_mixed_money import fixture
from test_plo5_card_review import frame

class MixedSoftTests(unittest.TestCase):
    def test_conflicting_profiles(self):
        with self.assertRaisesRegex(ValueError,'Conflicting'):CardReader(None,suprema_bank={},suprema_soft_bank={})
        with self.assertRaisesRegex(ValueError,'Conflicting'):run('missing','out',suprema_card_bank='a',suprema_soft_bank='b')
    def test_exact_cache_and_highlight(self):
        im=fixture();r=CardReader(None,suprema_soft_bank={});
        with patch('plo5_suprema_soft.classify',return_value={'card':None,'status':'uncertain'}) as mock:
            a=r.scan(im);n=mock.call_count;self.assertGreater(n,0);self.assertEqual(a,r.scan(im));self.assertEqual(mock.call_count,n)
            self.assertEqual(a[1]['rank_profile'],PROFILE)
            # Outside glyph ROIs, but inside the wider showdown guard.
            from plo5_mixed_money import STARTS
            x=STARTS[1];ImageDraw.Draw(im).rectangle((x+65,248,x+70,290),fill=(220,180,10));r.scan(im)
            self.assertGreater(mock.call_count,n)
    def test_profile_break(self):
        a=frame(1,platform='suprema');b=frame(2,platform='suprema');c=frame(3,platform='suprema')
        a['cards'][0]['rank_profile']=b['cards'][0]['rank_profile']=PROFILE;c['cards'][0]['rank_profile']='suprema-1504x696-v1'
        g=segments([a,b,c]);self.assertEqual([len(x['observations']) for x in g],[2,1]);self.assertEqual(g[0]['rank_profile'],PROFILE);self.assertFalse(g[0]['hand_verified'])
    def test_unknown_profile(self):
        a=frame(1,platform='suprema');a['cards'][0]['rank_profile']='unknown';self.assertEqual(segments([a]),[])

if __name__=='__main__':unittest.main()
