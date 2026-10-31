"""Synthetic regression tests for the offline full-frame/crop cross-index."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import offline_ev_session_crops as mod

FIXTURE = Path(__file__).parent / 'demo'


class CombinedIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(FIXTURE / 'batch', self.root / 'batch')
        shutil.copytree(FIXTURE / 'crops', self.root / 'crops')
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
