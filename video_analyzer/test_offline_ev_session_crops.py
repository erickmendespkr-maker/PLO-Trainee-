"""Synthetic regression tests for the offline full-frame/crop cross-index."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_ev_session_crops as mod

class CombinedIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_cross_fixture_')
        cls.base = Path(cls.fixture.name)
        video = cls.base / 'source.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'color=c=black:s=640x360:r=12:d=5',
                        '-vf', 'drawbox=x=0:y=0:w=320:h=180:color=red:t=fill,'
                               'drawbox=x=320:y=0:w=320:h=180:color=green:t=fill,'
                               'drawbox=x=0:y=180:w=320:h=180:color=blue:t=fill,'
                               'drawbox=x=320:y=180:w=320:h=180:color=yellow:t=fill',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)],
                       check=True, capture_output=True, timeout=30)
        batch, crops = cls.base / 'batch', cls.base / 'crops'
        batch.mkdir()
        crops.mkdir()
        video_sha = mod.checked_sha(video)
        layout = {'schema_version': 1, 'status': 'manual_offline_table_regions_unverified',
                  'source_video_sha256': video_sha, 'regions': []}
        ledger = {'schema_version': 1, 'status': mod.BATCH_STATUS,
                  'automatic_ocr_math_authorization': False,
                  'source_video_sha256': video_sha, 'clips': [], 'rendered_count': 4}
        for i in range(4):
            cid, table, hand = f'clip-{i}', f'T{i+1}', f'H{i}'
            region = {'table_id': table, 'x': (i % 2) * 320,
                      'y': (i // 2) * 180, 'width': 320, 'height': 180}
            layout['regions'].append(region)
            clip = batch / (cid + '.mp4')
            shutil.copyfile(video, clip)
            detail = {'status': 'offline_conditional_ev_clip_not_strategy_verdict',
                      'automatic_ocr_math_authorization': False,
                      'source_video_sha256': video_sha, 'rendered_clip_sha256': video_sha,
                      'clip_filename': cid + '.mp4', 'table_id': table, 'hand_id': hand,
                      'variant': 'PLO5', 'street': 'river',
                      'action_taken_claim_unverified': 'call',
                      'clip_start_seconds': 1.0, 'clip_duration_seconds': 1.0}
            (batch / (cid + '.json')).write_text(json.dumps(detail), encoding='utf-8')
            ledger['clips'].append({'clip_id': cid, 'table_id': table, 'hand_id': hand,
                                    'clip_filename': cid + '.mp4',
                                    'clip_report_filename': cid + '.json',
                                    'clip_sha256': video_sha,
                                    'clip_start_seconds': 1.0, 'clip_duration_seconds': 1.0})
        layout_path = cls.base / 'layout.json'
        layout_path.write_text(json.dumps(layout), encoding='utf-8')
        (batch / 'batch_report.json').write_text(json.dumps(ledger), encoding='utf-8')
        mod.crop.export(video, batch, layout_path, crops)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(self.base / 'batch', self.root / 'batch')
        shutil.copytree(self.base / 'crops', self.root / 'crops')
        self.batch, self.crops = self.root / 'batch', self.root / 'crops'
        self.out = self.crops / 'session_with_crops.html'

    def edit(self, path, mutate):
        obj = json.loads(path.read_text(encoding='utf-8'))
        mutate(obj)
        path.write_text(json.dumps(obj), encoding='utf-8')

    def rejects(self, collision=False):
        with self.assertRaises((ValueError, OSError)):
            mod.build(self.batch, self.crops)
        if not collision:
            self.assertFalse(self.out.exists())

    def test_four_pairs_and_real_relative_video_links(self):
        result = mod.build(self.batch, self.crops)
        self.assertEqual(result, self.out)
        html = result.read_text(encoding='utf-8')
        self.assertEqual(html.count('<section>'), 4)
        self.assertEqual(html.count('<video '), 8)
        for i in range(4):
            self.assertIn(f'../batch/clip-{i}.mp4', html)
            self.assertIn(f'crop_clip-{i}.mp4', html)
            self.assertIn(f'Mão H{i}', html)
        self.assertIn('não é veredito', html)
        self.assertIn('Sem autorização OCR', html)

    def test_originals_unchanged(self):
        before = {p.relative_to(self.root): mod.checked_sha(p)
                  for p in self.root.rglob('*') if p.is_file()}
        mod.build(self.batch, self.crops)
        after = {p.relative_to(self.root): mod.checked_sha(p)
                 for p in self.root.rglob('*') if p.is_file() and p != self.out}
        self.assertEqual(before, after)

    def test_output_collision(self):
        self.out.write_text('do not overwrite')
        self.rejects(collision=True)
        self.assertEqual(self.out.read_text(), 'do not overwrite')

    def test_output_symlink_collision(self):
        self.out.symlink_to(self.crops / 'crop_batch_report.json')
        self.rejects(collision=True)
        self.assertTrue(self.out.is_symlink())

    def test_crop_ledger_batch_hash_tamper(self):
        self.edit(self.crops / 'crop_batch_report.json',
                  lambda x: x.update(source_batch_report_sha256='0'*64))
        self.rejects()

    def test_video_source_hash_tamper(self):
        self.edit(self.crops / 'crop_batch_report.json',
                  lambda x: x.update(source_video_sha256='0'*64))
        self.rejects()

    def test_crop_mp4_tamper(self):
        with (self.crops / 'crop_clip-1.mp4').open('ab') as f:
            f.write(b'evil')
        self.rejects()

    def test_full_mp4_tamper(self):
        with (self.batch / 'clip-0.mp4').open('ab') as f:
            f.write(b'evil')
        self.rejects()

    def test_crop_meta_tamper(self):
        self.edit(self.crops / 'crop_clip-1.json',
                  lambda x: x.update(source_clip_report_sha256='0'*64))
        self.rejects()

    def test_full_meta_ocr_authorization_tamper(self):
        self.edit(self.batch / 'clip-0.json',
                  lambda x: x.update(automatic_ocr_math_authorization=True))
        self.rejects()

    def test_crop_meta_ocr_authorization_tamper(self):
        self.edit(self.crops / 'crop_clip-0.json',
                  lambda x: x.update(automatic_ocr_math_authorization=True))
        self.rejects()

    def test_batch_ocr_authorization_tamper(self):
        self.edit(self.batch / 'batch_report.json',
                  lambda x: x.update(automatic_ocr_math_authorization=True))
        self.rejects()

    def test_crop_time_tamper(self):
        self.edit(self.crops / 'crop_clip-0.json',
                  lambda x: x.update(clip_start_seconds=0))
        self.rejects()

    def test_crop_region_out_of_bounds(self):
        self.edit(self.crops / 'crop_clip-0.json',
                  lambda x: x['region_claim'].update(x=500))
        self.rejects()

    def test_crop_region_odd_width(self):
        self.edit(self.crops / 'crop_clip-0.json',
                  lambda x: x['region_claim'].update(width=319))
        self.rejects()

    def test_duplicate_crop_id(self):
        self.edit(self.crops / 'crop_batch_report.json',
                  lambda x: x['clips'][1].update(clip_id='clip-0'))
        self.rejects()

    def test_missing_crop_entry(self):
        self.edit(self.crops / 'crop_batch_report.json',
                  lambda x: (x['clips'].pop(), x.update(rendered_count=3)))
        self.rejects()

    def test_unknown_crop_id(self):
        self.edit(self.crops / 'crop_batch_report.json',
                  lambda x: x['clips'][0].update(clip_id='other'))
        self.rejects()

    def test_traversal_id(self):
        self.edit(self.crops / 'crop_batch_report.json',
                  lambda x: x['clips'][0].update(clip_id='../bad'))
        self.rejects()

    def test_crop_symlink_input(self):
        p = self.crops / 'crop_clip-0.mp4'
        original = self.crops / 'copy.mp4'
        p.rename(original)
        p.symlink_to(original)
        self.rejects()

    def test_source_symlink_input(self):
        p = self.batch / 'clip-0.json'
        original = self.batch / 'copy.json'
        p.rename(original)
        p.symlink_to(original)
        self.rejects()

    def test_duplicate_json_keys(self):
        p = self.crops / 'crop_clip-0.json'
        p.write_text(p.read_text().replace('"clip_id":', '"clip_id":"other", "clip_id":', 1))
        self.rejects()

    def test_nan_json(self):
        p = self.crops / 'crop_clip-0.json'
        p.write_text(p.read_text().replace('"clip_start_seconds": 1.0',
                                           '"clip_start_seconds": NaN'))
        self.rejects()

    def test_same_folder(self):
        with self.assertRaises(ValueError):
            mod.build(self.batch, self.batch)

    def test_relative_url_escapes_special_directory(self):
        new = self.root / 'batch & special'
        self.batch.rename(new)
        self.batch = new
        html = mod.build(self.batch, self.crops).read_text()
        self.assertIn('../batch%20%26%20special/clip-0.mp4', html)

    def test_bad_layout_hash(self):
        self.edit(self.crops / 'crop_batch_report.json',
                  lambda x: x.update(source_layout_sha256='not-a-sha'))
        self.rejects()


if __name__ == '__main__':
    unittest.main()
