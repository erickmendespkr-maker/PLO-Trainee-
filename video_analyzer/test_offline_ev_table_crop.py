"""Synthetic-only tests for four-table offline crop export."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_ev_table_crop as crop


class CropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_crop_base_')
        cls.video_base = Path(cls.fixture.name) / 'video.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'color=c=black:s=640x360:r=12:d=5',
                        '-vf', 'drawbox=x=0:y=0:w=320:h=180:color=red:t=fill,'
                               'drawbox=x=320:y=0:w=320:h=180:color=green:t=fill,'
                               'drawbox=x=0:y=180:w=320:h=180:color=blue:t=fill,'
                               'drawbox=x=320:y=180:w=320:h=180:color=yellow:t=fill',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video_base)],
                       check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_crop_test_')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / 'source.mp4'
        shutil.copyfile(self.video_base, self.video)
        self.batch = self.root / 'batch'
        self.batch.mkdir()
        self.out = self.root / 'out'
        self.out.mkdir()
        self.layout_path = self.root / 'layout.json'
        self.make(2)

    def dump(self, path, data):
        path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    def make(self, count):
        self.layout = {'schema_version': 1, 'status': 'manual_offline_table_regions_unverified',
                       'source_video_sha256': crop.digest(self.video), 'regions': []}
        self.ledger = {'schema_version': 1,
                       'status': 'offline_conditional_ev_batch_unverified_not_strategy_verdict',
                       'automatic_ocr_math_authorization': False,
                       'source_video_sha256': crop.digest(self.video), 'clips': [], 'rendered_count': count}
        for i in range(count):
            table = f'T{i+1}'
            self.layout['regions'].append({'table_id': table, 'x': (i % 2)*320,
                                           'y': (i // 2)*180, 'width': 320, 'height': 180})
            cid = f'clip-{i}'
            clip_file = self.batch / (cid + '.mp4')
            shutil.copyfile(self.video, clip_file)
            detail = {'status': 'offline_conditional_ev_clip_not_strategy_verdict',
                      'automatic_ocr_math_authorization': False,
                      'source_video_sha256': crop.digest(self.video),
                      'rendered_clip_sha256': crop.digest(clip_file),
                      'clip_filename': cid + '.mp4', 'table_id': table, 'hand_id': f'H{i}',
                      'variant': 'PLO5' if i % 2 == 0 else 'PLO6', 'street': 'river',
                      'action_taken_claim_unverified': 'call',
                      'clip_start_seconds': 1.0, 'clip_duration_seconds': 1.0}
            self.dump(self.batch / (cid + '.json'), detail)
            self.ledger['clips'].append({'clip_id': cid, 'table_id': table,
                                         'hand_id': f'H{i}', 'clip_filename': cid + '.mp4',
                                         'clip_report_filename': cid + '.json',
                                         'clip_sha256': crop.digest(clip_file),
                                         'clip_start_seconds': 1.0, 'clip_duration_seconds': 1.0})
        self.dump(self.layout_path, self.layout)
        self.dump(self.batch / 'batch_report.json', self.ledger)

    def run_export(self):
        return crop.export(self.video, self.batch, self.layout_path, self.out)

    def assert_empty(self):
        self.assertEqual(list(self.out.iterdir()), [])

    def test_four_table_render_and_hashes(self):
        self.make(4)
        ledger = self.run_export()
        self.assertEqual(ledger['rendered_count'], 4)
        self.assertFalse(ledger['automatic_ocr_math_authorization'])
        for i in range(4):
            name = f'crop_clip-{i}'
            mp4 = self.out / (name + '.mp4')
            meta = crop.read_json(self.out / (name + '.json'))
            self.assertEqual(meta['crop_sha256'], crop.digest(mp4))
            self.assertEqual(crop.media_info(mp4)[:2], (320, 180))
            self.assertAlmostEqual(meta['clip_start_seconds'], 1.0)
        self.assertEqual(crop.read_json(self.out / 'crop_batch_report.json')['rendered_count'], 4)

    def test_manual_layout_not_auto_detection(self):
        plans, *_ = crop.validate(self.video, self.batch, self.layout_path, self.out)
        self.assertEqual(plans[0][3]['x'], 0)
        self.assertEqual(plans[1][3]['x'], 320)

    def test_out_of_bounds(self):
        self.layout['regions'][0]['x'] = 500
        self.dump(self.layout_path, self.layout)
        with self.assertRaisesRegex(ValueError, 'crop'): self.run_export()
        self.assert_empty()

    def test_odd_dimensions(self):
        self.layout['regions'][0]['width'] = 319
        self.dump(self.layout_path, self.layout)
        with self.assertRaisesRegex(ValueError, 'crop'): self.run_export()

    def test_bool_geometry(self):
        self.layout['regions'][0]['x'] = True
        self.dump(self.layout_path, self.layout)
        with self.assertRaisesRegex(ValueError, 'crop'): self.run_export()

    def test_layout_source_hash_mismatch(self):
        self.layout['source_video_sha256'] = '0'*64
        self.dump(self.layout_path, self.layout)
        with self.assertRaisesRegex(ValueError, 'layout or source'): self.run_export()

    def test_missing_region(self):
        self.layout['regions'] = self.layout['regions'][:1]
        self.dump(self.layout_path, self.layout)
        with self.assertRaisesRegex(ValueError, 'missing table'): self.run_export()

    def test_symlinked_clip(self):
        path = self.batch / 'clip-0.mp4'
        real = self.root / 'real.mp4'
        path.rename(real)
        path.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'unsafe or missing'): self.run_export()

    def test_ocr_authorization_blocked(self):
        self.ledger['automatic_ocr_math_authorization'] = True
        self.dump(self.batch / 'batch_report.json', self.ledger)
        with self.assertRaisesRegex(ValueError, 'batch ledger'): self.run_export()

    def test_clip_hash_tamper(self):
        path = self.batch / 'clip-0.mp4'
        with path.open('ab') as f: f.write(b'altered')
        with self.assertRaisesRegex(ValueError, 'provenance'): self.run_export()

    def test_report_time_mismatch(self):
        p = self.batch / 'clip-0.json'
        data = crop.read_json(p)
        data['clip_start_seconds'] = 2
        self.dump(p, data)
        with self.assertRaisesRegex(ValueError, 'time provenance'): self.run_export()

    def test_existing_output_rejected(self):
        path = self.out / 'crop_clip-0.mp4'
        path.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'crop output exists'): self.run_export()
        self.assertEqual(path.read_bytes(), b'keep')

    def test_duplicate_json_key(self):
        self.layout_path.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'): self.run_export()

    def test_failure_rolls_back_previous_clips(self):
        original = crop.media_info
        count = [0]
        def break_second(path):
            if Path(path).name == 'crop.mp4':
                count[0] += 1
                if count[0] == 2: raise RuntimeError('synthetic media failure')
            return original(path)
        with mock.patch.object(crop, 'media_info', side_effect=break_second):
            with self.assertRaisesRegex(RuntimeError, 'synthetic media failure'):
                self.run_export()
        self.assert_empty()

    def test_input_mutation_rolls_back(self):
        original = crop.media_info
        done = [False]
        def mutate(path):
            result = original(path)
            if Path(path).name == 'crop.mp4' and not done[0]:
                done[0] = True
                with (self.batch / 'clip-0.json').open('a') as f: f.write(' ')
            return result
        with mock.patch.object(crop, 'media_info', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'inputs changed'):
                self.run_export()
        self.assert_empty()

    def test_zero_clips(self):
        self.make(1)
        self.ledger['clips'] = []
        self.ledger['rendered_count'] = 0
        self.dump(self.batch / 'batch_report.json', self.ledger)
        ledger = self.run_export()
        self.assertEqual(ledger['rendered_count'], 0)
        self.assertEqual([p.name for p in self.out.iterdir()], ['crop_batch_report.json'])


if __name__ == '__main__':
    unittest.main()
