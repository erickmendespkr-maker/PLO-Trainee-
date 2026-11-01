"""Synthetic fixture tests; never claim real poker recognition accuracy."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from offline_hand_ocr_review_queue import run

HERE = Path(__file__).resolve().parent


def make_fixture(folder):
    folder = Path(folder)
    video = folder / 'synthetic_4tables.mp4'
    subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error',
                    '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=2:duration=2',
                    '-c:v', 'mpeg4', '-q:v', '3', '-y', str(video)],
                   check=True, capture_output=True, timeout=30)
    bundle = folder / 'bundle'
    (bundle / 'frames').mkdir(parents=True)
    (bundle / 'tables').mkdir()
    frame = bundle / 'frames/frame_00.png'
    subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error',
                    '-i', str(video), '-frames:v', '1', '-update', '1', str(frame)],
                   check=True, capture_output=True, timeout=30)
    crops = []
    for table in range(1, 5):
        x = 320 * ((table-1) % 2)
        y = 180 * ((table-1) // 2)
        path = bundle / f'tables/table_{table:02d}_sample_00.png'
        subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error',
                        '-i', str(frame), '-vf', f'crop=320:180:{x}:{y}',
                        '-frames:v', '1', '-update', '1', str(path)],
                       check=True, capture_output=True, timeout=30)
        crops.append({'table_id':table,'path':f'tables/table_{table:02d}_sample_00.png',
                      'sha256':sha(path),'width':320,'height':180})
    source = {'schema_version':1,
              'analysis_status':'unverified_four_table_region_samples_for_manual_review_only',
              'recording_sha256':sha(video),'ready_for_equity_or_ev':False,
              'automatic_clip_selection_authorized':False,
              'regions':[{'table_id':i} for i in range(1,5)],
              'samples':[{'decoded_source_pts_seconds':0.0,
                          'frame_path':'frames/frame_00.png','frame_sha256':sha(frame),
                          'table_crops':crops}]}
    save(bundle/'region_samples.json',source)
    candidates=[]
    for c in crops:
        candidates.append({'table_id':c['table_id'],'sample_index':0,'field':'pot',
                           'decoded_source_pts_seconds':0.0,'status':'needs_manual_review',
                           'parsed_candidate':None,'source_crop_path':c['path'],
                           'source_crop_sha256':c['sha256'],'raw_ocr_text':'synthetic',
                           'roi':{'x':25,'y':20,'width':220,'height':110}})
    save(folder/'synthetic_original_ocr_report.json',{
        'schema_version':1,'analysis_status':'unverified_four_table_ocr_proposals_only',
        'recording_sha256':sha(video),'source_region_samples_sha256':sha(bundle/'region_samples.json'),
        'requires_manual_review':True,'ready_for_equity_or_ev':False,
        'automatic_hand_or_action_inference':False,'candidates':candidates})
    return folder


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value), encoding='utf-8')


class ReviewQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory()
        cls.fixture = make_fixture(cls.fixture_temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root/'video.mp4'
        shutil.copyfile(self.fixture/'synthetic_4tables.mp4', self.video)
        self.bundle = self.root/'bundle'
        shutil.copytree(self.fixture/'bundle', self.bundle)
        self.ocr = self.root/'ocr.json'
        shutil.copyfile(self.fixture/'synthetic_original_ocr_report.json', self.ocr)
        self.hands = self.root/'hands.json'
        self.out = self.root/'queue.json'
        self.hand_rows = [{'table_id':i, 'start_seconds':0.0, 'end_seconds':1.0}
                          for i in range(1,5)]
        self.write_hands()

    def write_hands(self):
        save(self.hands, {'schema_version':1,'status':'human_annotated_hand_boundaries',
                          'recording_sha256':sha(self.video),'hands':self.hand_rows})

    def execute(self, origin=0):
        return run(self.video,self.bundle,self.ocr,self.hands,self.out,
                   source_pts_origin=origin)

    def test_four_tables_linked_and_fail_closed(self):
        r=self.execute()
        self.assertEqual(r['observations_assigned'],4)
        self.assertEqual(r['observations_unassigned'],0)
        self.assertEqual([len(h['observations']) for h in r['hands']],[1]*4)
        self.assertFalse(r['ready_for_equity_or_ev'])
        self.assertFalse(r['hands_reconstructed'])
        self.assertEqual(json.loads(self.out.read_text()),r)

    def test_pts_offset_explicit_and_unassigned(self):
        r=self.execute(origin=5)
        self.assertEqual(r['observations_assigned'],0)
        self.assertEqual(r['observations_unassigned'],4)
        self.assertEqual(r['source_pts_origin_seconds_supplied_unverified'],5)

    def test_boundary_end_exclusive(self):
        self.hand_rows=[{'table_id':i,'start_seconds':1,'end_seconds':2}
                        for i in range(1,5)]
        self.write_hands()
        r=self.execute()
        self.assertEqual(r['observations_assigned'],0)

    def test_cli_produces_create_only_report(self):
        result=subprocess.run([sys.executable,str(HERE/"offline_hand_ocr_review_queue.py"),
                               str(self.video),str(self.bundle),str(self.ocr),
                               str(self.hands),str(self.out),"--source-pts-origin","0"],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["observations_assigned"],4)
        self.assertTrue(self.out.is_file())

    def test_reject_changed_full_frame(self):
        frame = self.bundle/'frames/frame_00.png'
        frame.write_bytes(frame.read_bytes()+b'change')
        with self.assertRaisesRegex(ValueError, 'image hash'):
            self.execute()
        self.assertFalse(self.out.exists())

    def test_reject_roi_outside_crop(self):
        o = json.loads(self.ocr.read_text())
        o['candidates'][0]['roi']['x'] = 319
        save(self.ocr, o)
        with self.assertRaisesRegex(ValueError, 'ROI outside'):
            self.execute()
        self.assertFalse(self.out.exists())

    def test_reject_duplicate_image_path(self):
        source = json.loads((self.bundle/'region_samples.json').read_text())
        source['samples'][0]['table_crops'][1]['path'] = source['samples'][0]['table_crops'][0]['path']
        save(self.bundle/'region_samples.json', source)
        o = json.loads(self.ocr.read_text())
        o['source_region_samples_sha256'] = sha(self.bundle/'region_samples.json')
        save(self.ocr, o)
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(self.out.exists())

    def test_reject_wrong_video_hash(self):
        self.video.write_bytes(self.video.read_bytes()+b'change')
        with self.assertRaises(ValueError):self.execute()
        self.assertFalse(self.out.exists())

    def test_reject_changed_crop(self):
        crop=self.bundle/'tables/table_01_sample_00.png'
        crop.write_bytes(crop.read_bytes()+b'change')
        with self.assertRaisesRegex(ValueError,'crop hash'):self.execute()
        self.assertFalse(self.out.exists())

    def test_reject_duplicate_candidate(self):
        o=json.loads(self.ocr.read_text())
        o['candidates'].append(copy.deepcopy(o['candidates'][0]))
        save(self.ocr,o)
        with self.assertRaisesRegex(ValueError,'duplicate OCR'):self.execute()

    def test_reject_ocr_promotion(self):
        o=json.loads(self.ocr.read_text())
        o['candidates'][0]['parsed_candidate']=12
        save(self.ocr,o)
        with self.assertRaisesRegex(ValueError,'promoted'):self.execute()

    def test_reject_duplicate_json_key(self):
        self.hands.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError,'duplicate JSON'):self.execute()

    def test_reject_overlapping_hands(self):
        self.hand_rows.append({'table_id':1,'start_seconds':0.5,'end_seconds':1.5})
        self.write_hands()
        with self.assertRaisesRegex(ValueError,'overlapping'):self.execute()

    def test_reject_output_overwrite(self):
        self.execute()
        saved=sha(self.out)
        with self.assertRaises(ValueError):self.execute()
        self.assertEqual(sha(self.out),saved)

    def test_reject_symlink_input(self):
        link=self.root/'alias.json'
        link.symlink_to(self.hands)
        with self.assertRaises(ValueError):
            run(self.video,self.bundle,self.ocr,link,self.out,source_pts_origin=0)
        self.assertFalse(self.out.exists())

    def test_reject_bad_origin(self):
        for origin in (float('nan'),float('inf'),86401,True):
            with self.subTest(origin=origin):
                with self.assertRaises(ValueError):self.execute(origin)
        self.assertFalse(self.out.exists())

    def test_reject_wrong_timestamp(self):
        o=json.loads(self.ocr.read_text())
        o['candidates'][0]['decoded_source_pts_seconds']=3
        save(self.ocr,o)
        with self.assertRaisesRegex(ValueError,'timestamp'):self.execute()

    def test_reject_ocr_mismatched_crop(self):
        o=json.loads(self.ocr.read_text())
        o['candidates'][0]['source_crop_sha256']='0'*64
        save(self.ocr,o)
        with self.assertRaisesRegex(ValueError,'bound to crop'):self.execute()

    def test_reject_hand_wrong_table(self):
        self.hand_rows[0]['table_id']=5
        self.write_hands()
        with self.assertRaises(ValueError):self.execute()


if __name__=='__main__':unittest.main()
