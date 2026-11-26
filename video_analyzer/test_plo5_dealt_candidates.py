import unittest
from unittest.mock import patch
from PIL import Image
from plo5_dealt_candidates import observe,classify,template,BACK_GLYPHS,EMPTY_GLYPHS,BACK_SIZE,EMPTY_SIZE,BACK_CENTERS,EMPTY_CENTERS,SEATS
from plo5_mixed_money import STARTS
from plo5_seat_candidates import observe as observe_seats

class DealtTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(classify(.55,0),'card_backs_visible_candidate')
        self.assertEqual(classify(0,.85),'explicit_empty_marker_candidate')
        self.assertEqual(classify(.54,.84),'unknown')
        self.assertEqual(classify(1,1),'conflicting_visual_evidence')
    def test_back_all_seats(self):
        for p in BACK_CENTERS:
            for t in (1,4):
                im=Image.new('RGB',(1504,696),(20,40,70))
                for i,(x,y) in enumerate(BACK_CENTERS[p]):
                    g=Image.fromarray(template(BACK_GLYPHS[p][0 if i==0 else 1 if i<3 else 2],BACK_SIZE[p])).convert('RGB')
                    im.paste(g,(STARTS[t-1]+x-g.width//2,y-g.height//2))
                with patch('plo5_dealt_candidates.detect',return_value=p):
                    r=observe(im,t)
                self.assertEqual([q['seat'] for q in r['opponents']],list(SEATS))
                self.assertTrue(all(q['status']=='card_backs_visible_candidate' and not q['dealt_verified'] for q in r['opponents']))
                self.assertFalse(r['dealt_roster_verified'])
    def test_empty_all_seats(self):
        for p in EMPTY_CENTERS:
            im=Image.new('RGB',(1504,696),(20,40,70))
            g=Image.fromarray(template(EMPTY_GLYPHS[p],EMPTY_SIZE[p])).convert('RGB')
            for x,y in EMPTY_CENTERS[p]:im.paste(g,(x-g.width//2,y-g.height//2))
            with patch('plo5_dealt_candidates.detect',return_value=p):
                r=observe(im,1)
            self.assertTrue(all(q['status']=='explicit_empty_marker_candidate' for q in r['opponents']))
    def test_no_marker_does_not_imply_empty(self):
        with patch('plo5_dealt_candidates.detect',return_value='pppoker'):
            r=observe(Image.new('RGB',(1504,696)),1)
        self.assertTrue(all(q['status']=='unknown' for q in r['opponents']))
    def test_invalid_geometry(self):
        with self.assertRaises(ValueError):observe(Image.new('RGB',(372,696)),1)
        with self.assertRaises(ValueError):observe(Image.new('RGB',(1504,696)),5)
    def test_integration_abstains_positions(self):
        im=Image.new('RGB',(1504,696))
        with patch('plo5_seat_candidates.detect',return_value='suprema'),patch('plo5_dealt_candidates.detect',return_value='suprema'):
            r=observe_seats(im,1)
        self.assertEqual(len(r['opponents']),5);self.assertIsNone(r['dealt_seats']);self.assertIsNone(r['hero_position']);self.assertFalse(r['positions_verified'])
if __name__=='__main__':unittest.main()
