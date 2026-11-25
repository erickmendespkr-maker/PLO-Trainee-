import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw
from plo5_boundary_candidates import (observe, propose_resets, validate_calibration,
                                      analyze_job, EMPTY)

CFG = {'felt_rgb':[20,100,40], 'tolerance':30, 'board_strip':
       {'offset_x':8,'offset_y':5,'step_x':10,'width':8,'height':10,
        'white_min_rgb':200,'min_white_fraction':.8}}
REGION = {'table_id':1,'x':64,'y':0,'width':64,'height':64}


def frame(count=0, visible=True, flags=None):
    image=Image.new('RGB',(64,64),(20,100,40) if visible else (0,0,0))
    draw=ImageDraw.Draw(image)
    for k in (range(count) if flags is None else flags):
        x=8+k*10
        draw.rectangle((x,5,x+7,14),fill='white')
    return image


def sequence(stages, table=1, start=0):
    return [{'table_id':table,'pts':start+i,'street':stage,'visible':stage is not None,
             'file':f't{table}_{start+i}.jpg'} for i,stage in enumerate(stages)]


class BoundaryTests(unittest.TestCase):
    def test_reused_classifiers(self):
        validate_calibration(CFG,[REGION])
        for n,street in [(0,EMPTY),(3,'flop_candidate'),(4,'turn_candidate'),(5,'river_candidate')]:
            presence, board=observe(frame(n),REGION,CFG)
            self.assertEqual(presence['proposal'],'likely_visible')
            self.assertEqual(board['street_proposal'],street)
        self.assertIsNone(observe(frame(5,False),REGION,CFG)[1])
        self.assertEqual(observe(frame(flags=[0,2,3]),REGION,CFG)[1]['street_proposal'],'ambiguous')

    def test_reset_interval_and_four_frames(self):
        candidates,_=propose_resets(sequence(['flop_candidate','river_candidate',EMPTY,EMPTY,EMPTY]))
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['interval_pts'],[1,2])
        self.assertEqual(candidates[0]['confirmation_observation_pts'],3)
        self.assertEqual(len(candidates[0]['evidence_files']),4)
        self.assertFalse(candidates[0]['hand_boundary_verified'])

    def test_negative_fixtures(self):
        cases=[['flop_candidate','turn_candidate','river_candidate'],
               [EMPTY,EMPTY,EMPTY,EMPTY],
               ['flop_candidate','turn_candidate',EMPTY,'river_candidate'],
               ['flop_candidate',EMPTY,EMPTY],
               ['flop_candidate','river_candidate',None,EMPTY,EMPTY],
               ['flop_candidate','river_candidate','ambiguous',EMPTY,EMPTY]]
        for stages in cases:
            with self.subTest(stages=stages):
                self.assertEqual(propose_resets(sequence(stages))[0],[])

    def test_table_isolation(self):
        rows=sequence(['flop_candidate','river_candidate',EMPTY,EMPTY],1)+sequence([EMPTY]*4,2)+sequence(['flop_candidate']*4,3)+sequence([None]*4,4)
        candidates,_=propose_resets(rows)
        self.assertEqual([r['table_id'] for r in candidates],[1])

    def test_duplicate_and_long_gap(self):
        rows=sequence(['flop_candidate','turn_candidate',EMPTY])
        self.assertEqual(propose_resets(rows+[dict(rows[-1])]),([],1))
        self.assertEqual(propose_resets(rows[:2]+sequence([EMPTY,EMPTY],start=50))[0],[])

    def test_calibration_rejected(self):
        with self.assertRaises(ValueError):
            validate_calibration(dict(CFG,board_strip=dict(CFG['board_strip'],offset_x=50)),[REGION])
        with self.assertRaises(ValueError):
            validate_calibration(dict(CFG,tolerance=True),[REGION])


class BoundJobTests(unittest.TestCase):
    def test_real_job_handoff_and_tampering(self):
        import local_ingest
        from plo5_ingest_job import run_job
        from pathlib import Path
        import subprocess
        import shutil
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('requires FFmpeg/FFprobe')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            video=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x146428:s=128x128:r=5:d=2','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
            regions=root/'regions.json'
            regions.write_text(json.dumps({'tables':[dict(REGION,x=0,y=0)]}))
            cal=root/'cal.json';cal.write_text(json.dumps(CFG))
            db=root/'jobs.db'
            job=local_ingest.ingest_local(video,root/'uploads',db)
            result=run_job(db,job['job_id'],regions,root/'output',pixel_checks=1)
            report=analyze_job(db,job['job_id'],cal)
            self.assertEqual(len(report['observations']),3)
            self.assertTrue(all(r['visible'] for r in report['observations']))
            self.assertEqual(report['candidates'],[])
            self.assertFalse(report['equity_ev_authorized'])
            crop=next((Path(result['result_path']).parent/'evidence/ingest').glob('*.jpg'))
            crop.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'crop mismatch'):
                analyze_job(db,job['job_id'],cal)
