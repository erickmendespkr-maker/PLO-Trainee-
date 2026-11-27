import unittest
from plo5_reconstruction_candidates import collect

H=['As','Ks','Qh','Jd','Tc'];B=['2c','3d','4h']
def frame(t,stack='100',pot='2',h=H,b=None,platform='pppoker'):
    obs=[];cr=[]
    for i in range(1,5):
        p=platform if i==1 else None
        for k,v in [('stack',stack),('pot',pot)]:obs.append(dict(table_id=i,field=k,platform=p,layout_candidate_active=p is not None,value_bb=v if p else None))
        cr.append(dict(table_id=i,platform=p,hero_cards=h if p else None,board_cards=([] if b is None else b) if p else None))
    return dict(file=f'{t}.png',pts=str(t),observations=obs,cards=cr)

class CandidateTests(unittest.TestCase):
    def test_street_and_display_only(self):
        r=collect([frame(0),frame(1,'90','12',b=B),frame(2,'100','0',b=B)])
        self.assertEqual(len(r['card_segments']),1);self.assertEqual(r['card_segments'][0]['observations'][1]['transition'],'street_advance_candidate')
        self.assertEqual(len(r['display_changes']),2);self.assertEqual(r['display_changes'][0]['stack_delta_bb'],'-10');self.assertIsNone(r['display_changes'][1]['net_bb'])
    def test_unknown_and_reset_split(self):
        r=collect([frame(0),frame(1,h=None),frame(2),frame(3,h=['Ah','Kh','Qs','Jc','Td'])]);self.assertEqual(len(r['card_segments']),3)
        self.assertFalse(r['hands_reconstructed']);self.assertEqual(r['card_segments'][-1]['observations'][0]['transition'],'possible_new_hand')
    def test_source_gap_and_profile(self):
        r=collect([frame(0),frame(2,'50'),frame(3,'20',platform='suprema')]);self.assertEqual(len(r['display_changes']),0);self.assertEqual(len(r['card_segments']),3)
    def test_money_only_and_invalid(self):
        a,b=frame(0),frame(1,'80');a.pop('cards');b.pop('cards');r=collect([a,b]);self.assertEqual(len(r['display_changes']),1);self.assertEqual(r['card_segments'],[])
        with self.assertRaises(ValueError):collect([frame(0),frame(0)])
        with self.assertRaises(ValueError):collect([frame(0,'NaN')])
        with self.assertRaises(ValueError):collect([frame(0,b=['As','2c','3d'])])

if __name__=='__main__':unittest.main()
