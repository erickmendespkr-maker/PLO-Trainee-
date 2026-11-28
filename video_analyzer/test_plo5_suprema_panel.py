import unittest
from PIL import Image, ImageDraw
from plo5_suprema_panel import panel
from plo5_auto_reconstruct import hero_turn, snapshot
from plo5_mixed_money import REGIONS
from plo5_seat_evidence import STACKS
from test_plo5_continuity import frame


def sample(seated=True, buttons='active',table=4):
    from plo5_mixed_money import STARTS
    x=STARTS[table-1];im=Image.new('RGB',(1504,696),(28,30,31));d=ImageDraw.Draw(im)
    if seated:d.rectangle((x+155,584,x+222,611),outline=(240,240,240))
    if buttons=='active':colors=[(188,70,29),(42,144,105),(205,153,37)]
    elif buttons=='preselect':colors=[(42,144,105)]*3
    else:colors=[]
    for a,c in zip((17,142,264),colors):d.rectangle((x+a,650,x+a+7,655),fill=c)
    return im


class PanelTests(unittest.TestCase):
    def test_positive_panel_and_turn(self):
        for t in range(1,5):
            r=panel(sample(table=t),t);self.assertTrue(r['seated_panel_candidate']);self.assertTrue(r['hero_turn_candidate']);self.assertFalse(r['identity_verified']);self.assertEqual(hero_turn(sample(table=t),t,'suprema'),'hero_bottom')
    def test_preselect_and_observer_abstain(self):
        for im in (sample(buttons='preselect'),sample(seated=False),sample(buttons='none')):self.assertIsNone(hero_turn(im,4,'suprema'))
        self.assertFalse(panel(sample(seated=False),4)['seated_panel_candidate'])
    def test_observer_blocks_snapshot(self):
        f=frame(0,15,195,190,actor='hero_bottom');c=f['cards'][0];c['platform']='suprema';c['seat_evidence']['platform']='suprema';c['opponent_evidence']['platform']='suprema'
        for o in f['observations']:o['platform']='suprema'
        c['panel_evidence']=panel(sample(seated=False),4)
        with self.assertRaisesRegex(ValueError,'seated panel'):snapshot(f,1,10)
        c['panel_evidence']=panel(sample(),4);self.assertEqual(snapshot(f,1,10)['remaining']['hero_bottom'],195)
    def test_roi_expands_without_changing_ppp(self):
        self.assertEqual(REGIONS['suprema']['stack'],(160,598,220,611));self.assertEqual(STACKS['suprema'][3],(158,598,222,615));self.assertEqual(REGIONS['pppoker']['stack'],(159,627,218,640))

if __name__=='__main__':unittest.main()
