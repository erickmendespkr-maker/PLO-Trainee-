import unittest
from plo5_hand_boundaries import analyze,transition
from test_plo5_preflop_roster import sample

class BoundaryTests(unittest.TestCase):
    def frames(self,boards,dealer='top'):
        out=[]
        for i,b in enumerate(boards,1):
            f=sample(i);f['cards'][0]['board_cards']=b;f['seats'][0]['dealer_seat_candidate']=dealer;out.append(f)
        return out
    def test_progression(self):
        b=['2c','3d','4h'];f=self.frames([[],[],b,b,b+['5s'],b+['5s']]);r=analyze(f);self.assertEqual([x['transition_candidate'] for x in r['transitions']],['street_advance']*2);self.assertTrue(all(x['repeated_both_sides'] for x in r['transitions']));self.assertFalse(r['boundaries_verified'])
    def test_new_hand(self):
        f=self.frames([[],[],[],[]]);
        for x in f[2:]:x['cards'][0]['hero_cards']=['2c','3d','4h','5s','6c'];x['seats'][0]['dealer_seat_candidate']='upper_right'
        r=analyze(f)['transitions'][0];self.assertEqual(r['transition_candidate'],'new_hand_boundary');self.assertFalse(r['financial_result_verified'])
    def test_no_dealer_change(self):
        f=self.frames([[],[],[],[]]);
        for x in f[2:]:x['cards'][0]['hero_cards']=['2c','3d','4h','5s','6c']
        self.assertEqual(analyze(f)['transitions'][0]['transition_candidate'],'unresolved_state_change')
    def test_uncertainty(self):
        f=self.frames([[],None,['2c','3d','4h']]);r=analyze(f);self.assertEqual(r['transitions'],[]);self.assertEqual(r['continuity_breaks'][0]['reason'],'uncertain_observation')
    def test_gap(self):
        f=self.frames([[],['2c','3d','4h']]);f[1]['pts']='3';r=analyze(f);self.assertEqual(r['transitions'],[]);self.assertEqual(r['continuity_breaks'][0]['reason'],'source_gap')
    def test_skipped_street(self):
        b=['2c','3d','4h','5s'];r=analyze(self.frames([[],[],b,b]))['transitions'][0];self.assertEqual(r['transition_candidate'],'street_skip');self.assertEqual(r['status'],'UNRESOLVED_TRANSITION')
    def test_single_observation(self):
        r=analyze(self.frames([[],['2c','3d','4h']]))['transitions'][0];self.assertFalse(r['repeated_both_sides']);self.assertEqual(r['status'],'UNRESOLVED_TRANSITION')
    def test_board_rewrite(self):
        r=analyze(self.frames([['2c','3d','4h'],['2c','3d','4h'],['2c','3d','6h','5s'],['2c','3d','6h','5s']]))['transitions'][0];self.assertEqual(r['transition_candidate'],'unresolved_state_change')
    def test_bounded_uncertain_interval(self):
        f=self.frames([[],[],None,[],[]]);
        for x in f[3:]:x['cards'][0]['hero_cards']=['2c','3d','4h','5s','6c'];x['seats'][0]['dealer_seat_candidate']='upper_right'
        r=analyze(f);self.assertEqual(r['transitions'],[]);self.assertEqual(len(r['possible_new_hand_intervals']),1);self.assertFalse(r['possible_new_hand_intervals'][0]['boundary_verified'])
        f[2]['cards'][0]['platform']=None;self.assertEqual(analyze(f)['possible_new_hand_intervals'],[])
    def test_no_interval_across_source_gap(self):
        f=self.frames([[],[],None,[],[]]);
        for x in f[3:]:x['cards'][0]['hero_cards']=['2c','3d','4h','5s','6c'];x['seats'][0]['dealer_seat_candidate']='upper_right';x['pts']=str(int(x['pts'])+1)
        self.assertEqual(analyze(f)['possible_new_hand_intervals'],[])
    def test_duplicate_and_bad_roster(self):
        f=self.frames([[]]);
        with self.assertRaises(ValueError):analyze(f+f)
        f[0]['seats'].pop()
        with self.assertRaises(ValueError):analyze(f)
if __name__=='__main__':unittest.main()
