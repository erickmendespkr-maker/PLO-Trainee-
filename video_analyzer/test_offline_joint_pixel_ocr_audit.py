"""Synthetic integration/regression tests for the joint FFmpeg pixel/OCR audit."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

from offline_joint_pixel_ocr_audit import run

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


class JointAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory()
        root = Path(cls.fixture_temp.name)
        cls.fixture = root
        bundle = root / 'bundle'
        (bundle/'frames').mkdir(parents=True)
        (bundle/'tables').mkdir()
        image = Image.new('RGB', (640, 360), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 64)
        for table, number in enumerate(('12', '23', '34', '45'), 1):
            x, y = ((table-1)%2)*320, ((table-1)//2)*180
            draw.text((x+50, y+40), number, font=font, fill='black')
        still = root/'still.png'
        image.save(still)
        video = root/'video.mp4'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-loop','1','-i',str(still),
                        '-t','2','-r','2','-c:v','libx264','-pix_fmt','yuv420p',
                        str(video)], check=True, capture_output=True, timeout=40)
        frame = bundle/'frames/frame_00.png'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(video),
                        '-frames:v','1','-update','1',str(frame)],
                       check=True, capture_output=True, timeout=40)
        regions, crops, candidates, gold = [], [], [], []
        for table, number in enumerate((12, 23, 34, 45), 1):
            x, y = ((table-1)%2)*320, ((table-1)//2)*180
            crop = bundle/f'tables/table_{table:02d}_sample_00.png'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(frame),
                            '-vf',f'crop=320:180:{x}:{y}',
                            '-frames:v','1','-update','1',str(crop)],
                           check=True, capture_output=True, timeout=40)
            rel = crop.relative_to(bundle).as_posix()
            regions.append({'table_id':table,'x':x,'y':y,'width':320,'height':180})
            crops.append({'table_id':table,'path':rel,'sha256':sha(crop),
                          'width':320,'height':180})
            candidates.append({'table_id':table,'sample_index':0,'field':'pot',
                               'decoded_source_pts_seconds':0.0,
                               'status':'needs_manual_review','parsed_candidate':None,
                               'source_crop_sha256':sha(crop),'source_crop_path':rel,
                               'raw_ocr_text':str(number),
                               'roi':{'x':25,'y':20,'width':220,'height':110}})
            gold.append({'table_id':table,'field':'pot','timestamp':0.0,
                         'expected':float(number)})
        source = {'schema_version':1,
                  'analysis_status':'unverified_four_table_region_samples_for_manual_review_only',
                  'recording_sha256':sha(video),'layout_sha256':'a'*64,
                  'recording_duration_seconds':2.0,'frame_width':640,'frame_height':360,
                  'regions':regions,
                  'samples':[{'requested_seek_seconds':0.0,
                              'decoded_source_pts_seconds':0.0,'seek_delta_seconds':0.0,
                              'frame_path':'frames/frame_00.png',
                              'frame_sha256':sha(frame),'table_crops':crops}],
                  'timestamp_semantics':'decoded_source_pts_seconds_from_ffmpeg_showinfo',
                  'regions_human_confirmed':False,'cards_actions_verified':False,
                  'hand_boundaries_verified':False,'ready_for_equity_or_ev':False,
                  'automatic_clip_selection_authorized':False}
        save(bundle/'region_samples.json', source)
        proposal = {'schema_version':1,
                    'analysis_status':'unverified_four_table_ocr_proposals_only',
                    'ready_for_equity_or_ev':False,'requires_manual_review':True,
                    'automatic_hand_or_action_inference':False,
                    'engine_confidence_is_calibrated_probability':False,
                    'recording_sha256':sha(video),
                    'source_region_samples_sha256':sha(bundle/'region_samples.json'),
                    'candidates':candidates}
        save(root/'ocr.json', proposal)
        save(root/'labels.json', gold)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'video.mp4'
        self.bundle = self.root / 'bundle'
        self.proposals = self.root / 'ocr.json'
        self.labels = self.root / 'labels.json'
        self.output = self.root / 'joint'
        shutil.copyfile(self.fixture/'video.mp4', self.video)
        shutil.copytree(self.fixture/'bundle', self.bundle)
        shutil.copyfile(self.fixture/'ocr.json', self.proposals)
        shutil.copyfile(self.fixture/'labels.json', self.labels)

    def execute(self, **kwargs):
        return run(self.video, self.bundle, self.proposals, self.labels, self.output, **kwargs)

    def test_actual_ffmpeg_joint_audits(self):
        result = self.execute()
        self.assertEqual(result['table_crops_verified_by_both_audits'], 4)
        self.assertEqual(result['source_frames_independently_decoded'], 1)
        self.assertEqual(result['recording_sha256'], sha(self.video))
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['real_poker_ocr_accuracy_verified'])
        self.assertEqual(sorted(p.name for p in self.output.iterdir()),
                         ['joint_report.json', 'ocr_agreement.json', 'pixel_audit.json'])
        self.assertEqual(result['pixel_audit_sha256'], sha(self.output/'pixel_audit.json'))
        self.assertEqual(result['ocr_agreement_sha256'], sha(self.output/'ocr_agreement.json'))

    def test_existing_output_never_overwritten(self):
        self.execute()
        saved = sha(self.output / 'joint_report.json')
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(sha(self.output/'joint_report.json'), saved)

    def test_recording_bytes_modified(self):
        self.video.write_bytes(self.video.read_bytes() + b'changed')
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.output.exists())

    def test_source_crop_replaced_and_rehashed(self):
        source = self.bundle / 'region_samples.json'
        data = json.loads(source.read_text())
        crop1 = self.bundle / 'tables/table_01_sample_00.png'
        crop2 = self.bundle / 'tables/table_02_sample_00.png'
        crop1.write_bytes(crop2.read_bytes())
        data['samples'][0]['table_crops'][0]['sha256'] = sha(crop1)
        save(source, data)
        proposals = json.loads(self.proposals.read_text())
        proposals['source_region_samples_sha256'] = sha(source)
        proposals['candidates'][0]['source_crop_sha256'] = sha(crop1)
        save(self.proposals, proposals)
        with self.assertRaisesRegex(ValueError, 'crop pixels'):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_wrong_ocr_source_hash(self):
        data = json.loads(self.proposals.read_text())
        data['source_region_samples_sha256'] = 'f'*64
        save(self.proposals, data)
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.output.exists())

    def test_invalid_label_timestamp(self):
        data = json.loads(self.labels.read_text())
        data[0]['timestamp'] = 200
        save(self.labels, data)
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.output.exists())

    def test_output_symlink_rejected(self):
        self.output.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaises(ValueError): self.execute()
        self.assertTrue(self.output.is_symlink())

    def test_bundle_symlink_rejected(self):
        alias = self.root/'alias'
        alias.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaises(ValueError):
            run(self.video, alias, self.proposals, self.labels, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_ffmpeg(self):
        with self.assertRaises(ValueError): self.execute(ffmpeg='ffmpeg_missing_joint')
        self.assertFalse(self.output.exists())

    def test_missing_ffprobe(self):
        with self.assertRaises(ValueError): self.execute(ffprobe='ffprobe_missing_joint')
        self.assertFalse(self.output.exists())

    def test_duplicate_json_keys(self):
        self.proposals.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.output.exists())

    def test_no_publish_if_second_audit_fails(self):
        with patch('offline_joint_pixel_ocr_audit.ocr.run', side_effect=ValueError('OCR failure')):
            with self.assertRaisesRegex(ValueError, 'OCR failure'): self.execute()
        self.assertFalse(self.output.exists())

    def test_conflicting_report_hash_rejected(self):
        from offline_joint_pixel_ocr_audit import ocr
        original = ocr.run
        def conflicting(*args, **kwargs):
            result = original(*args, **kwargs)
            result['source_region_samples_sha256_verified'] = '0'*64
            return result
        with patch('offline_joint_pixel_ocr_audit.ocr.run', side_effect=conflicting):
            with self.assertRaisesRegex(ValueError, 'same recording'):
                self.execute()
        self.assertFalse(self.output.exists())

    def test_unsafe_promotion_rejected(self):
        from offline_joint_pixel_ocr_audit import ocr
        original = ocr.run
        def unsafe(*args, **kwargs):
            result = original(*args, **kwargs)
            result['ready_for_equity_or_ev'] = True
            return result
        with patch('offline_joint_pixel_ocr_audit.ocr.run', side_effect=unsafe):
            with self.assertRaisesRegex(ValueError, 'unsafe downstream'):
                self.execute()
        self.assertFalse(self.output.exists())

    def test_input_modified_between_audits(self):
        from offline_joint_pixel_ocr_audit import ocr
        original = ocr.run
        def tamper(*args, **kwargs):
            result = original(*args, **kwargs)
            self.labels.write_bytes(self.labels.read_bytes() + b' ')
            return result
        with patch('offline_joint_pixel_ocr_audit.ocr.run', side_effect=tamper):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                self.execute()
        self.assertFalse(self.output.exists())

    def test_cli_with_real_ffmpeg(self):
        proc = subprocess.run([
            'python', str(HERE/'offline_joint_pixel_ocr_audit.py'),
            str(self.video), str(self.bundle), str(self.proposals),
            str(self.labels), str(self.output)], capture_output=True, text=True,
            timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(json.loads(proc.stdout)['ready_for_equity_or_ev'])
        self.assertTrue((self.output/'joint_report.json').is_file())


if __name__ == '__main__':
    unittest.main()
