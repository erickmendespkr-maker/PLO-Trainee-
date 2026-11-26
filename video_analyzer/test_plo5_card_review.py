import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from plo5_card_review import CardReader, segments
from test_plo5_mixed_money import fixture

H=['Ac','Kd','Qh','Js','Tc']
B=['2c','3d','4h']
def frame(t,h=H,b=(),platform='pppoker'):
    return {'file':f'{t}.png','pts':str(t),'cards':[{'table_id':i,'variant':5,'platform':platform if i==1 else None,'hero_cards':h if i==1 else None,'board_cards':list(b) if i==1 else None,'cards_verified':False} for i in range(1,5)]}

class CardReviewTests(unittest.TestCase):
    def test_exact_slot_cache(self):
        im=fixture();r=CardReader({},1024)
        with patch('plo5_card_review.classify',return_value={'card':None,'status':'uncertain'}) as m:
            a=r.scan(im);calls=m.call_count
            self.assertGreater(calls,0);self.assertEqual(a,r.scan(im));self.assertEqual(m.call_count,calls)
            ImageDraw.Draw(im).point((215,565),fill='white');r.scan(im)
            self.assertEqual(m.call_count,calls+1)
    def test_board_growth(self):
        g=segments([frame(1),frame(2,b=B),frame(3,b=B+['5s'])]);self.assertEqual(len(g),1);self.assertEqual(len(g[0]['observations']),3);self.assertFalse(g[0]['hand_verified']);self.assertFalse(g[0]['strategy_authorized'])
    def test_uncertainty_gap_reset(self):
        for rows in ([frame(1),frame(2,h=None),frame(3)], [frame(1),frame(3)], [frame(1,b=B),frame(2)], [frame(1),frame(2,h=['Ac','Kd','Qh','Js','9c'])], [frame(1),frame(2,platform='suprema'),frame(3)]):
            self.assertEqual(len(segments(rows)),2)
    def test_invalid_cards(self):
        self.assertEqual(segments([frame(1,b=['Ac','3d','4h']),frame(2,h=['Ac']*5)]),[])
    def test_invalid_roster(self):
        f=frame(1);f['cards'].pop()
        with self.assertRaises(ValueError):segments([f])
    def test_nonmonotonic(self):
        with self.assertRaises(ValueError):segments([frame(2),frame(1)])
    def test_preflop_absence_not_known(self):
        f=frame(1);f['cards'][0]['board_cards']=None
        self.assertEqual(segments([f]),[])
    def test_card_claim_rejected(self):
        f=frame(1);f['cards'][0]['cards_verified']=True
        with self.assertRaises(ValueError):segments([f])

if __name__=='__main__':unittest.main()
