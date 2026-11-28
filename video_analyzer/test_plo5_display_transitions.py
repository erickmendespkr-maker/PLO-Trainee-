import unittest
from plo5_display_transitions import DisplayTransitions
from test_plo5_continuity import frame,manifest

class TransitionTests(unittest.TestCase):
    def test_increase_and_pot_drop_cross_window(self):
        a=frame(0,20,190,190);b=frame(1,0,210,190);d=DisplayTransitions();self.assertEqual(d.feed(manifest([a])),[]);r=d.feed(manifest([b]));self.assertEqual(len(r),1);self.assertEqual(r[0]['stack_display_increases_bb'],{'hero_bottom':'2.0'});self.assertEqual(r[0]['pot_after_bb'],'0.0');self.assertFalse(r[0]['payout_verified']);self.assertFalse(r[0]['rebuy_verified']);self.assertFalse(r[0]['showdown_verified']);self.assertEqual(r,DisplayTransitions().feed(manifest([a,b])))
    def test_gap_and_uncorroborated_stack_abstain(self):
        a=frame(0,20,190,190);b=frame(3,0,210,190);self.assertEqual(DisplayTransitions().feed(manifest([a,b])),[])
        b=frame(1,0,210,190);b['observations'][0]['value_bb']='21.5';self.assertEqual(DisplayTransitions().feed(manifest([a,b])),[])
    def test_source_and_order(self):
        a=frame(0,20,190,190);d=DisplayTransitions();d.feed(manifest([a]));
        with self.assertRaises(ValueError):d.feed(manifest([a]))
        with self.assertRaises(ValueError):d.feed(manifest([frame(1,20,190,190)],'c'*64))

if __name__=='__main__':unittest.main()
