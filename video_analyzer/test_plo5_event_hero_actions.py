import unittest
from plo5_event_hero_actions import adjacent,label_state,street,run
from pathlib import Path
import tempfile,json

class EventHeroTests(unittest.TestCase):
    def test_adjacent(self):
        a={'pts':'10','sample':4};b={'pts':'81/8','sample':5}
        self.assertTrue(adjacent(a,b,8));self.assertTrue(adjacent(b,a,8))
        self.assertFalse(adjacent(a,dict(b,sample=3),8))
        self.assertFalse(adjacent(a,dict(b,pts='41/4'),8))
    def test_persistence(self):
        self.assertEqual(label_state('fold','fold','fold'),('fold','persistent_label_candidate'))
    def test_label_change(self):
        self.assertEqual(label_state('check','bet','bet'),('bet','different_visible_label_candidate'))
        self.assertEqual(label_state(None,'bet','bet'),('bet','label_seen_after_unreadable_or_absent'))
        self.assertEqual(label_state(None,'bet','bet',before_bound=False),('bet','label_without_bound_prior'))
    def test_uncertain(self):
        self.assertEqual(label_state('fold','call','fold'),(None,'uncertain_pair'))
        self.assertEqual(label_state('fold',None,None),(None,'uncertain_pair'))
    def test_board_context(self):
        a={'hero_cards':['Ac','Kd','Qh','Js','Tc'],'board_cards':[]}
        for n,s in ((0,'preflop'),(3,'flop'),(4,'turn'),(5,'river'),(2,None)):
            self.assertEqual(street(dict(a,board_cards=['2c']*n)),s)
        self.assertIsNone(street(dict(a,hero_cards=None)));self.assertIsNone(street(None))
    def test_manifest_format(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'manifest.json').write_text(json.dumps({'variant':6,'status':'PIXEL_CHANGE_CANDIDATES_ONLY','sampling_hz':8,'start':0,'seconds':2}))
            with self.assertRaisesRegex(ValueError,'Invalid event format'):run(p,{})
    def test_route(self):
        from plo5_review_pipeline import main
        from unittest.mock import patch
        with patch('plo5_event_hero_actions.main',return_value=0) as m:
            self.assertEqual(main(['event-hero-actions','report','new.json']),0);m.assert_called_once_with(['report','new.json'])
if __name__=='__main__':unittest.main()
