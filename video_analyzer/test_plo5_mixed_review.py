import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
from plo5_mixed_review import Reader,changes,run
from plo5_review_pipeline import main
from test_plo5_mixed_money import fixture


def frame(t,values,platform='pppoker'):
    return {'pts':str(t),'file':f'frame_{t}.png','observations':[{'field':'stack','table_id':i,'platform':platform,'value_bb':v,'layout_candidate_active':True} for i,v in enumerate(values,1)]}


class MixedReviewTests(unittest.TestCase):
    def test_exact_roi_cache(self):
        image=fixture();reader=Reader(512,1)
        with patch('plo5_mixed_review.read',return_value={'value_bb':'100','raw':'100 BB','confidence':.99}) as m:
            a=reader.scan(image);b=reader.scan(image);self.assertEqual(a,b);self.assertEqual(m.call_count,4)
            ImageDraw.Draw(image).point((160,630),fill='white');reader.scan(image);self.assertEqual(m.call_count,5)
        self.assertEqual(reader.cache.stats()['hits'],7)
    def test_disabled_cache(self):
        reader=Reader(0,1)
        with patch('plo5_mixed_review.read',return_value={'value_bb':None,'raw':'','confidence':None}) as m:
            reader.scan(fixture());reader.scan(fixture());self.assertEqual(m.call_count,8)
    def test_adjacent_drop(self):
        r=changes([frame(1,['100','100','100','100']),frame(2,['69','70','120',None])]);self.assertEqual(len(r),1);self.assertEqual(r[0]['display_decline_bb'],'31');self.assertIsNone(r[0]['conditional_net_bb'])
    def test_no_bridge_gap(self):
        self.assertEqual(changes([frame(1,['100']*4),frame(3,['1']*4)]),[])
        self.assertEqual(changes([frame('19/10',['100']*4),frame(3,['1']*4)]),[])
        self.assertEqual(changes([frame(1,['100']*4),frame(2,[None]*4),frame(3,['1']*4)]),[])
        self.assertEqual(changes([frame(1,['100']*4),frame(2,['1']*4,'suprema')]),[])
    def test_invalid_roster(self):
        f=frame(1,['100']*4);f['observations'].pop()
        with self.assertRaises(ValueError):changes([f])
    def test_atomic_publication(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'x.mp4';src.write_bytes(b'fixture');out=p/'out'
            with patch('plo5_mixed_review.extract',side_effect=ValueError('failure')):
                with self.assertRaisesRegex(ValueError,'failure'):run(src,out)
            self.assertFalse(out.exists())
    def test_existing_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'x.mp4';src.write_bytes(b'fixture');out=p/'out';out.mkdir()
            with self.assertRaisesRegex(ValueError,'New output'):run(src,out)
    def test_main_route(self):
        with patch('plo5_mixed_review.main',return_value=0) as m:
            self.assertEqual(main(['mixed-video','video.mp4','output','--seconds','20']),0)
            m.assert_called_once_with(['video.mp4','output','--seconds','20'])


if __name__=='__main__':unittest.main()
