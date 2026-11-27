import unittest
from plo5_stack_changes import analyze,run
from pathlib import Path
import tempfile,json


def frame(t,stack,board=None,dealer='top',platform='pppoker'):
    return {'pts':str(t),'file':str(t)+'.png','sha256':'a'*64,
            'cards':[{'table_id':i,'platform':platform,'board_cards':board} for i in range(1,5)],
            'seats':[{'table_id':i,'platform':platform,'dealer_seat_candidate':dealer} for i in range(1,5)],
            'observations':[{'table_id':i,'platform':platform,'field':f,'value_bb':stack if i==1 and f=='stack' else None,'layout_candidate_active':True,'financial_result_verified':False} for i in range(1,5) for f in ('stack','pot')]}


def reset(target='100'):
    return [frame(1,'83.5',['2c','3d','4h']),frame(2,'83.5',['2c','3d','4h']),frame(3,target,[],'upper_right'),frame(4,target,[],'upper_right')]


class StackTests(unittest.TestCase):
    def test_top_up_compatible_not_verified(self):
        r=analyze(reset(),'100')[0];self.assertEqual(r['status'],'REVIEW_TOP_UP_COMPATIBLE');self.assertEqual(r['display_increase_bb'],'16.5');self.assertIsNone(r['external_transfer_bb']);self.assertIsNone(r['conditional_net_bb']);self.assertFalse(r['rebuy_verified'])
    def test_target_not_assumed(self):
        self.assertEqual(analyze(reset())[0]['status'],'UNRESOLVED_DISPLAY_INCREASE')
        self.assertEqual(analyze(reset('150'),'150')[0]['status'],'REVIEW_TOP_UP_COMPATIBLE')
    def test_same_board_or_dealer(self):
        f=reset();f[2]['cards'][0]['board_cards']=['2c','3d','4h'];self.assertEqual(analyze(f,'100')[0]['status'],'UNRESOLVED_DISPLAY_INCREASE')
        f=reset();f[2]['seats'][0]['dealer_seat_candidate']='top';self.assertEqual(analyze(f,'100')[0]['status'],'UNRESOLVED_DISPLAY_INCREASE')
    def test_missing_peers(self):
        self.assertFalse(analyze(reset()[1:],'100')[0]['repeated_both_sides']);self.assertFalse(analyze(reset()[:3],'100')[0]['repeated_both_sides'])
    def test_gaps_and_missing_stack(self):
        f=reset();f[2]['pts']='5';f[3]['pts']='6';self.assertEqual(analyze(f,'100'),[])
        f=reset();f[1]['observations'][0]['value_bb']=None;self.assertEqual(analyze(f,'100'),[])
    def test_platform_change(self):
        f=reset();f[2]=frame(3,'100',[],'upper_right','suprema');f[3]=frame(4,'100',[],'upper_right','suprema');self.assertEqual(analyze(f,'100'),[])
    def test_no_automatic_return(self):
        f=[frame(1,'50'),frame(2,'50'),frame(3,'70'),frame(4,'70')];r=analyze(f)[0];self.assertFalse(r['return_verified']);self.assertFalse(r['payout_verified']);self.assertIsNone(r['conditional_net_bb'])
    def test_wrong_variant(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'manifest.json').write_text(json.dumps({'variant':6}));
            with self.assertRaises(ValueError):run(d,'100')
if __name__=='__main__':unittest.main()
