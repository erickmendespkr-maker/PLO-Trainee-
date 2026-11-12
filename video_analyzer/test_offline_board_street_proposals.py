"""Local fixtures only; no private recording or source images in GitHub tests."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image, ImageDraw
import offline_board_street_proposals as app


class BoardStreetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.strip={'offset_x':10,'offset_y':20,'step_x':32,'width':28,
                    'height':40,'white_min_rgb':200,'min_white_fraction':.5}
        self.slots=[{'table_id':1,'x':0,'y':0,'width':320,'height':480},
                    {'table_id':2,'x':320,'y':0,'width':320,'height':480}]
        self.cfg={'schema_version':1,'slots':self.slots,'board_strip':self.strip}
        self.config=self.root/'config.json';self.write_cfg()

    def write_cfg(self):
        self.config.write_text(json.dumps(self.cfg),'utf-8')

    def picture(self,count=0, gray=False, broken=False):
        im=Image.new('RGB',(640,480),(24,35,65))
        draw=ImageDraw.Draw(im)
        indices=([0,2,3] if broken else list(range(count)))
        for k in indices:
            x=self.strip['offset_x']+k*self.strip['step_x']
            y=self.strip['offset_y']
            draw.rectangle((x,y,x+self.strip['width']-1,y+self.strip['height']-1),
                           fill=(110,120,135) if gray else (244,245,247))
        return im

    def test_board_0_3_4_5(self):
        for n,stage in [(0,'no_faceup_board_detected'),(3,'flop_candidate'),
                        (4,'turn_candidate'),(5,'river_candidate')]:
            with self.subTest(n=n):
                v=app.sample_board(self.picture(n),self.slots[0],self.strip)
                self.assertEqual(v['street_proposal'],stage)
                self.assertEqual(v['faceup_card_count_candidate'],n)
                self.assertFalse(v['verified_by_human'])
                self.assertFalse(v['board_rank_or_suit_recognized'])

    def test_gray_back_not_faceup(self):
        v=app.sample_board(self.picture(3,gray=True),self.slots[0],self.strip)
        self.assertEqual(v['street_proposal'],'no_faceup_board_detected')

    def test_nonprefix_card_pattern_ambiguous(self):
        v=app.sample_board(self.picture(broken=True),self.slots[0],self.strip)
        self.assertEqual(v['street_proposal'],'ambiguous')
        self.assertIsNone(v['faceup_card_count_candidate'])

    def test_one_card_ambiguous(self):
        self.assertEqual(app.sample_board(self.picture(1),self.slots[0],self.strip)['street_proposal'],
                         'ambiguous')

    def test_no_cross_table_leakage(self):
        im=self.picture(5)
        a=app.sample_board(im,self.slots[0],self.strip)
        b=app.sample_board(im,self.slots[1],self.strip)
        self.assertEqual(a['street_proposal'],'river_candidate')
        self.assertEqual(b['street_proposal'],'no_faceup_board_detected')

    def test_valid_config(self):
        self.assertEqual(len(app.load_config(self.config,640,480)['slots']),2)

    def test_overlap_rejected(self):
        self.cfg['slots'][1]['x']=200;self.write_cfg()
        with self.assertRaises(ValueError):app.load_config(self.config,640,480)

    def test_duplicate_ids_rejected(self):
        self.cfg['slots'][1]['table_id']=1;self.write_cfg()
        with self.assertRaises(ValueError):app.load_config(self.config,640,480)

    def test_bad_boolean_id_rejected(self):
        self.cfg['slots'][0]['table_id']=True;self.write_cfg()
        with self.assertRaises(ValueError):app.load_config(self.config,640,480)

    def test_bad_boolean_threshold_rejected(self):
        self.cfg['board_strip']['white_min_rgb']=True;self.write_cfg()
        with self.assertRaises(ValueError):app.load_config(self.config,640,480)

    def test_nonfinite_fraction_rejected(self):
        self.cfg['board_strip']['min_white_fraction']=float('nan');self.write_cfg()
        with self.assertRaises(ValueError):app.load_config(self.config,640,480)

    def test_out_of_slot_strip_rejected(self):
        self.cfg['board_strip']['offset_x']=200;self.write_cfg()
        with self.assertRaises(ValueError):app.load_config(self.config,640,480)

    def test_duplicate_json_key_rejected(self):
        self.config.write_text('{"slots":[],"slots":[],"schema_version":1,"board_strip":{}}','utf-8')
        with self.assertRaises(ValueError):app.load_config(self.config,640,480)

    def test_strict_time_order(self):
        video=self.make_video()
        for times in ([1,0], [0,0],[0,float('nan')],[0,True],[0,4]):
            with self.subTest(times=times),self.assertRaises(ValueError):
                app.analyze(video,self.config,times)

    def make_video(self):
        images=self.root/'images';images.mkdir(exist_ok=True)
        for i,n in enumerate((0,3,4)):
            self.picture(n).save(images/f'img_{i:03}.png')
        video=self.root/'synthetic.mp4'
        cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error',
             '-framerate','1','-i',str(images/'img_%03d.png'),'-an',
             '-c:v','mpeg4','-q:v','2',str(video)]
        done=subprocess.run(cmd,capture_output=True,timeout=30)
        self.assertEqual(done.returncode,0,done.stderr)
        return video

    def test_real_ffmpeg_synthetic_video(self):
        video=self.make_video()
        report=app.analyze(video,self.config,[0,1,2])
        self.assertEqual(report['source_video_sha256'],app.sha256(video))
        self.assertEqual([r['tables'][0]['street_proposal'] for r in report['samples']],
                         ['no_faceup_board_detected','flop_candidate','turn_candidate'])
        self.assertEqual(len(report['transition_candidates']),2)
        self.assertFalse(report['hands_reconstructed'])
        self.assertFalse(report['equity_or_ev_authorized'])
        self.assertEqual([r['tables'][1]['street_proposal'] for r in report['samples']],
                         ['no_faceup_board_detected']*3)
        self.assertTrue(all(isinstance(s['source_decoded_pts_seconds'],float)
                            for s in report['samples']))

    def test_export_no_overwrite(self):
        video=self.make_video()
        output=self.root/'report.json'
        original=app.save_report(video,self.config,[0,1,2],output)
        self.assertEqual(json.loads(output.read_text())['source_video_sha256'],original['source_video_sha256'])
        with self.assertRaises(ValueError):app.save_report(video,self.config,[0,1,2],output)

    def test_bad_config_after_video_hash(self):
        video=self.make_video()
        self.cfg['slots'][0]['width']=900;self.write_cfg()
        with self.assertRaises(ValueError):app.analyze(video,self.config,[0,1,2])

    def test_no_output_on_wrong_format(self):
        other=self.root/'bad.txt';other.write_bytes(b'not video')
        with self.assertRaises(ValueError):app.save_report(other,self.config,[0,1],self.root/'out.json')
        self.assertFalse((self.root/'out.json').exists())


if __name__=='__main__':unittest.main(verbosity=2)
