import copy
import unittest
from plo5_financial_settlement import settle
from plo5_financial_observations import amount, deltas, gold_mask
from PIL import Image


def seat(i,before,after,committed,returned=0,rebuy=0,withdrawal=0,folded=False,cards=None):
    return dict(seat=i,before=before,after=after,committed=committed,returned=returned,rebuy=rebuy,withdrawal=withdrawal,folded=folded,cards=cards)


def pot(id,rake,awards):
    return dict(pot_id=id,rake=rake,awards=[dict(seat=i,chips=v) for i,v in awards])


def fixture():
    # A wins main; B wins side; C's unmatched 50 returns. D folded 100.
    return dict(variant=5,reviewer='fixture',complete=True,hero_seat=3,bb_chips=10,board=[],seats=[seat(1,100,390,100),seat(2,200,190,200),seat(3,250,150,250,returned=50,rebuy=100),seat(4,500,400,100,folded=True)],pots=[pot('main',10,[(1,390)]),pot('side_1',10,[(2,190)])])


class SettlementTests(unittest.TestCase):
    def test_side_pot_return_rake_rebuy(self):
        r=settle(fixture());self.assertEqual(r['status'],'CONDITIONAL_SETTLEMENT');self.assertEqual(r['hero_net_chips'],-200);self.assertEqual(r['hero_net_bb_fraction'],{'numerator':-20,'denominator':1});self.assertFalse(r['hero_loss_over_30bb']);self.assertFalse(r['financial_result_verified']);self.assertEqual([p['gross_chips'] for p in r['pots']],[400,200]);self.assertEqual(sum(x['net_chips'] for x in r['balances']),-20)
    def test_inconsistent_balance(self):
        r=fixture();r['seats'][2]['after']+=1;result=settle(r);self.assertEqual(result['status'],'UNRESOLVED_BALANCE');self.assertIsNone(result['hero_net_chips']);self.assertIsNone(result['hero_loss_over_30bb'])
    def test_illegal_pots(self):
        for fn in [lambda r:r['seats'][2].update(returned=49),lambda r:r['pots'][0]['awards'][0].update(seat=4),lambda r:r['pots'][0]['awards'][0].update(chips=391),lambda r:r['seats'][0].update(before=101),lambda r:r.update(variant=6),lambda r:r.update(complete=False),lambda r:r.update(bb_chips=True),lambda r:r['seats'][1].update(cards=['As']*5)]:
            r=fixture();fn(r)
            with self.assertRaises(ValueError):settle(r)
    def test_showdown_and_wrong_winner(self):
        r=dict(variant=5,reviewer='fixture',complete=True,hero_seat=1,bb_chips=10,board=['As','Ks','Qs','2h','3d'],seats=[seat(1,300,600,300,cards=['Js','Ts','4d','5h','6c']),seat(2,300,0,300,cards=['Ac','Ad','7c','8d','9h'])],pots=[pot('main',0,[(1,600)])]);result=settle(r);self.assertEqual(result['pots'][0]['eligible_winners_from_declared_cards_or_fold'],[1]);r['pots'][0]['awards']=[dict(seat=2,chips=600)]
        with self.assertRaises(ValueError):settle(r)
    def test_strict_threshold(self):
        for n in [300,301]:
            r=dict(variant=5,reviewer='fixture',complete=True,hero_seat=1,bb_chips=10,board=[],seats=[seat(1,n,0,n,folded=True),seat(2,n,2*n,n)],pots=[pot('main',0,[(2,2*n)])]);self.assertEqual(settle(r)['hero_loss_over_30bb'],n>300)
    def test_tied_showdown_odd_chip(self):
        r=dict(variant=5,reviewer='fixture',complete=True,hero_seat=1,bb_chips=10,board=['As','Kd','Qc','2h','3d'],seats=[seat(1,100,100,100,cards=['Js','Ts','4d','5h','6c']),seat(2,100,99,100,cards=['Jc','Tc','4s','5d','6h'])],pots=[pot('main',1,[(1,100),(2,99)])]);self.assertEqual(settle(r)['pots'][0]['eligible_winners_from_declared_cards_or_fold'],[1,2]);r['pots'][0]['awards']=[dict(seat=1,chips=101),dict(seat=2,chips=98)]
        with self.assertRaises(ValueError):settle(r)
    def test_observations_never_promoted(self):
        s={'frames':[{'file':str(i)} for i in range(4)]};rows={str(i):dict(file=str(i),pts=i,pot_bb=p,stack_bb=v) for i,(p,v) in enumerate([('20','100'),('40','90'),(None,None),('0','200')])};d=deltas(s,rows);self.assertEqual(len(d),1);self.assertEqual(d[0]['stack_delta_bb'],'-10');self.assertFalse(d[0]['financial_event_verified']);self.assertIsNone(amount({'candidate':{'unit':'chips','value':'100'}}));self.assertIsNone(amount(None))
    def test_gold_mask_geometry(self):
        im=Image.new('RGB',(402,748),'black');im.putpixel((170,645),(220,210,90));im.putpixel((180,645),(255,255,255));r,m=gold_mask(im);self.assertEqual(r.size,(71,14));self.assertEqual(m.size,(474,132));self.assertLess(m.getpixel((24+4*6+3,24+3*6+3)),m.getpixel((24+14*6+3,24+3*6+3)))
        with self.assertRaises(ValueError):gold_mask(Image.new('RGB',(432,800)))


if __name__=='__main__':unittest.main()
