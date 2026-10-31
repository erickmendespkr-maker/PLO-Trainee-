"""Synthetic, offline temporal batch crop tests; no actual poker footage."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_ev_table_crop as crop
import offline_temporal_batch_crops as mod


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


class TemporalBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_temporal_fixture_')
        cls.root = Path(cls.fixture.name)
        cls.video = cls.root / 'moving.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', 'testsrc2=size=320x180:rate=10', '-t', '6', '-an',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                        str(cls.video)], capture_output=True, check=True, timeout=30)
        cls.review = cls.root / 'review.json'
        def regions(split_x, split_y):
            return [{'table_id': f'T{i}', 'x': x, 'y': y, 'width': w, 'height': h}
                    for i, (x, y, w, h) in enumerate([
                        (0, 0, split_x, split_y), (split_x, 0, 320-split_x, split_y),
                        (0, split_y, split_x, 180-split_y),
                        (split_x, split_y, 320-split_x, 180-split_y)], 1)]
        review = {'schema_version': 1,
                  'status': 'manual_offline_temporal_layout_claim_unverified',
                  'source_video_sha256': crop.digest(cls.video),
                  'source_width': 320, 'source_height': 180,
                  'source_duration_seconds': 6.0,
                  'human_confirmation_claimed': True,
                  'table_identity_verified': False,
                  'automatic_ocr_math_authorization': False,
                  'reviewer_note': 'SYNTHETIC TEST: human review is simulated only',
                  'segments': [
                      {'start_seconds': 0.0, 'end_seconds': 3.0, 'regions': regions(160, 90)},
                      {'start_seconds': 3.0, 'end_seconds': 6.0, 'regions': regions(184, 102)}]}
        write(cls.review, review)
        cls.batch_dir = cls.root / 'batch'
        cls.batch_dir.mkdir()
        cls.cases = [
            ('first', 'T1', 'H1', .5, 1.0, 1.0),
            ('second', 'T4', 'H4', 3.5, 1.0, 4.0),
            ('near', 'T2', 'H2', 2.5, 1.0, 2.9),
            ('cross', 'T3', 'H3', 1.0, 3.0, 2.0),
        ]
        clips = []
        for cid, table, hand, start, length, pts in cls.cases:
            mp4 = cls.batch_dir / f'{cid}.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-ss', str(start),
                            '-i', str(cls.video), '-t', str(length), '-an', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(mp4)],
                           capture_output=True, check=True, timeout=30)
            report = {'schema_version': 1, 'status': 'offline_conditional_ev_clip_not_strategy_verdict',
                      'clip_filename': mp4.name, 'source_video_sha256': crop.digest(cls.video),
                      'rendered_clip_sha256': crop.digest(mp4), 'table_id': table,
                      'hand_id': hand, 'variant': 'PLO5', 'street': 'river',
                      'clip_start_seconds': start, 'clip_duration_seconds': length,
                      'decision_pts_seconds_claim': pts, 'action_taken_claim_unverified': 'call',
                      'automatic_ocr_math_authorization': False}
            write(cls.batch_dir / f'{cid}.json', report)
            clips.append({'clip_id': cid, 'table_id': table, 'hand_id': hand,
                          'clip_filename': mp4.name, 'clip_report_filename': f'{cid}.json',
                          'clip_sha256': crop.digest(mp4), 'clip_start_seconds': start,
                          'clip_duration_seconds': length, 'decision_pts_seconds_claim': pts})
        cls.batch = {'schema_version': 1,
                     'status': 'offline_conditional_ev_batch_unverified_not_strategy_verdict',
                     'source_video_sha256': crop.digest(cls.video),
                     'rendered_count': len(clips), 'clips': clips,
                     'automatic_ocr_math_authorization': False}
        write(cls.batch_dir / 'batch_report.json', cls.batch)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_temporal_test_')
        self.out = Path(self.tmp.name) / 'out'
        self.out.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def preflight(self, **kwargs):
        return mod.preflight(kwargs.get('video', self.video),
                             kwargs.get('batch_dir', self.batch_dir),
                             kwargs.get('review', self.review), self.out)

    def mutate_review(self, change):
        value = json.loads(self.review.read_text())
        change(value)
        p = Path(self.tmp.name) / 'review.json'
        write(p, value)
        return p

    def mutate_batch(self, change):
        folder = Path(self.tmp.name) / 'batch'
        shutil.copytree(self.batch_dir, folder)
        data = json.loads((folder / 'batch_report.json').read_text())
        change(data)
        write(folder / 'batch_report.json', data)
        return folder

    def test_preflight_two_safe_two_blocked(self):
        *_, plans, blocked, inputs = self.preflight()
        self.assertEqual([x[0] for x in plans], ['first', 'second'])
        self.assertEqual([x['clip_id'] for x in blocked], ['near', 'cross'])
        self.assertEqual(len(inputs), 3 + 2 * 4)

    def test_crossing_clip_blocked_even_when_decision_safe(self):
        *_, plans, blocked, _ = self.preflight()
        self.assertNotIn('cross', [x[0] for x in plans])
        self.assertEqual(blocked[1]['reason'], 'clip_overlaps_or_approaches_geometry_transition')

    def test_near_transition_decision_blocked(self):
        *_, _, blocked, _ = self.preflight()
        self.assertEqual(blocked[0]['reason'], 'decision_near_uncertain_transition')

    def test_region_changes_across_segments(self):
        *_, plans, _, _ = self.preflight()
        self.assertEqual(plans[0][4]['width'], 160)
        self.assertEqual(plans[1][4]['width'], 136)
        self.assertEqual([x[5] for x in plans], [1, 2])

    def test_invalid_confirmation_rejected(self):
        p = self.mutate_review(lambda r: r.update(human_confirmation_claimed=False))
        with self.assertRaises(ValueError): self.preflight(review=p)

    def test_math_authorization_rejected(self):
        p = self.mutate_review(lambda r: r.update(automatic_ocr_math_authorization=True))
        with self.assertRaises(ValueError): self.preflight(review=p)

    def test_review_video_hash_mismatch_rejected(self):
        p = self.mutate_review(lambda r: r.update(source_video_sha256='0' * 64))
        with self.assertRaises(ValueError): self.preflight(review=p)

    def test_noncontiguous_review_rejected(self):
        p = self.mutate_review(lambda r: r['segments'][1].update(start_seconds=3.1))
        with self.assertRaises(ValueError): self.preflight(review=p)

    def test_batch_wrong_source_rejected(self):
        folder = self.mutate_batch(lambda b: b.update(source_video_sha256='0' * 64))
        with self.assertRaises(ValueError): self.preflight(batch_dir=folder)

    def test_duplicate_clip_id_rejected(self):
        folder = self.mutate_batch(lambda b: b['clips'][1].update(clip_id='first'))
        with self.assertRaises(ValueError): self.preflight(batch_dir=folder)

    def test_unsafe_clip_filename_rejected(self):
        folder = self.mutate_batch(lambda b: b['clips'][0].update(clip_filename='../escape.mp4'))
        with self.assertRaises(ValueError): self.preflight(batch_dir=folder)

    def test_modified_full_clip_rejected(self):
        folder = self.mutate_batch(lambda b: None)
        with (folder / 'first.mp4').open('ab') as f: f.write(b'bad')
        with self.assertRaises(ValueError): self.preflight(batch_dir=folder)

    def test_modified_report_rejected(self):
        folder = self.mutate_batch(lambda b: None)
        p = folder / 'first.json'
        obj = json.loads(p.read_text()); obj['table_id'] = 'T4'; write(p, obj)
        with self.assertRaises(ValueError): self.preflight(batch_dir=folder)

    def test_wrong_timestamp_rejected(self):
        folder = self.mutate_batch(lambda b: b['clips'][0].update(decision_pts_seconds_claim=1.7))
        with self.assertRaises(ValueError): self.preflight(batch_dir=folder)

    def test_existing_output_rejected(self):
        (self.out / 'temporal_first.mp4').write_bytes(b'collision')
        with self.assertRaises(ValueError): self.preflight()

    def test_symlink_review_rejected(self):
        alias = Path(self.tmp.name) / 'alias.json'
        alias.symlink_to(self.review)
        with self.assertRaises(ValueError): self.preflight(review=alias)

    def test_real_ffmpeg_two_clips_and_hashes(self):
        ledger = mod.export(self.video, self.batch_dir, self.review, self.out)
        self.assertEqual((ledger['rendered_count'], ledger['blocked_count']), (2, 2))
        self.assertFalse(ledger['automatic_ocr_math_authorization'])
        self.assertFalse(ledger['table_identity_verified'])
        for c in ledger['clips']:
            f = self.out / c['filename']
            self.assertEqual(c['sha256'], crop.digest(f))
            metadata = json.loads((self.out / c['metadata']).read_text())
            self.assertEqual(metadata['crop_sha256'], crop.digest(f))
            self.assertEqual(crop.media_info(f)[:2],
                             (metadata['region_claim']['width'], metadata['region_claim']['height']))
        self.assertEqual(len(list(self.out.iterdir())), 5)

    def test_failure_rolls_back_published_files(self):
        original = mod.subprocess.run
        counter = {'n': 0}
        def broken(*args, **kwargs):
            counter['n'] += 1
            if counter['n'] == 2:
                raise subprocess.CalledProcessError(1, args[0], 'synthetic failure')
            return original(*args, **kwargs)
        # Preflight ffprobe calls before patched render; validate both clips first.
        prepared = self.preflight()
        with mock.patch.object(mod, 'preflight', return_value=prepared):
            with mock.patch.object(mod.subprocess, 'run', side_effect=broken):
                with self.assertRaises(subprocess.CalledProcessError):
                    mod.export(self.video, self.batch_dir, self.review, self.out)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_cli_invalid_arguments(self):
        with self.assertRaises(SystemExit): mod.main([])


if __name__ == '__main__':
    unittest.main()
