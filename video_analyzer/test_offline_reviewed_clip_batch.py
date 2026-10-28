"""Offline tests for four-table manual batch clips (synthetic video only)."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_reviewed_clip_batch as batch


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.video_dir = tempfile.TemporaryDirectory()
        cls.video = Path(cls.video_dir.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=10',
                        '-t', '4', '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                        '-pix_fmt', 'yuv420p', str(cls.video)], check=True, timeout=30)
        cls.sha = batch.single.digest(cls.video)
        cls.width, cls.height, cls.duration = batch.single.probe(cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.video_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.req = {'schema_version': 1, 'hand_id': 'hand_1', 'table_id': 1,
                    'start_seconds': 0.5, 'end_seconds': 1.5,
                    'crop': {'x': 0, 'y': 0, 'width': 320, 'height': 180},
                    'explanation': 'Synthetic manual selection only.',
                    'source_video_sha256': self.sha, 'reviewer_confirmed_offline': True}
        self.raw = {'schema_version': 1, 'source_video_sha256': self.sha,
                    'reviewer_confirmed_offline': True,
                    'reviewer_note': 'Offline synthetic test only.',
                    'clips': [copy.deepcopy(self.req)]}

    def check(self, raw=None):
        return batch.validate_manifest(raw if raw is not None else self.raw,
                                       self.width, self.height, self.duration, self.sha)

    def rejects(self, change):
        raw = copy.deepcopy(self.raw)
        change(raw)
        with self.assertRaises((ValueError, TypeError, KeyError)):
            self.check(raw)

    def test_valid_one(self):
        clips, total = self.check()
        self.assertEqual(len(clips), 1)
        self.assertEqual(total, 1.0)

    def test_valid_four_tables_same_time(self):
        self.raw['clips'] = []
        for i in range(1, 5):
            req = copy.deepcopy(self.req)
            req['table_id'] = i
            req['hand_id'] = f'hand_{i}'
            self.raw['clips'].append(req)
        self.assertEqual(len(self.check()[0]), 4)

    def test_valid_adjacent_same_table(self):
        req = copy.deepcopy(self.req)
        req['hand_id'] = 'next'
        req['start_seconds'], req['end_seconds'] = 1.5, 2.5
        self.raw['clips'].append(req)
        self.assertEqual(len(self.check()[0]), 2)

    def test_overlap_same_table_rejected(self):
        def edit(raw):
            req = copy.deepcopy(raw['clips'][0]); req['hand_id'] = 'next'
            req['start_seconds'] = 1.4; req['end_seconds'] = 2.4
            raw['clips'].append(req)
        self.rejects(edit)

    def test_duplicate_hand_table_rejected(self):
        self.rejects(lambda r: r['clips'].append(copy.deepcopy(r['clips'][0])))

    def test_same_hand_different_table_allowed(self):
        req = copy.deepcopy(self.req); req['table_id'] = 2
        self.raw['clips'].append(req)
        self.assertEqual(len(self.check()[0]), 2)

    def test_empty_clips(self): self.rejects(lambda r: r.update(clips=[]))
    def test_too_many_clips(self): self.rejects(lambda r: r.update(clips=[self.req] * 13))
    def test_clips_not_list(self): self.rejects(lambda r: r.update(clips={}))
    def test_missing_key(self): self.rejects(lambda r: r.pop('reviewer_note'))
    def test_extra_key(self): self.rejects(lambda r: r.update(extra='no'))
    def test_wrong_version(self): self.rejects(lambda r: r.update(schema_version=True))
    def test_wrong_hash(self): self.rejects(lambda r: r.update(source_video_sha256='a'*64))
    def test_bad_hash_type(self): self.rejects(lambda r: r.update(source_video_sha256=123))
    def test_unapproved_batch(self): self.rejects(lambda r: r.update(reviewer_confirmed_offline=False))
    def test_missing_note(self): self.rejects(lambda r: r.update(reviewer_note='  '))
    def test_note_too_long(self): self.rejects(lambda r: r.update(reviewer_note='x'*1001))
    def test_unapproved_clip(self): self.rejects(lambda r: r['clips'][0].update(reviewer_confirmed_offline=False))
    def test_wrong_clip_hash(self): self.rejects(lambda r: r['clips'][0].update(source_video_sha256='a'*64))
    def test_bad_table(self): self.rejects(lambda r: r['clips'][0].update(table_id=5))
    def test_bad_crop(self): self.rejects(lambda r: r['clips'][0]['crop'].update(width=321))
    def test_invalid_start(self): self.rejects(lambda r: r['clips'][0].update(start_seconds=-1))
    def test_inverted_time(self): self.rejects(lambda r: r['clips'][0].update(end_seconds=0.4))
    def test_nan_timestamp(self): self.rejects(lambda r: r['clips'][0].update(start_seconds=float('nan')))
    def test_unsafe_hand_path(self): self.rejects(lambda r: r['clips'][0].update(hand_id='../bad'))
    def test_hand_spaces(self): self.rejects(lambda r: r['clips'][0].update(hand_id='hand one'))
    def test_empty_hand(self): self.rejects(lambda r: r['clips'][0].update(hand_id=''))
    def test_too_long_hand(self): self.rejects(lambda r: r['clips'][0].update(hand_id='x'*65))
    def test_unexpected_clip_field(self): self.rejects(lambda r: r['clips'][0].update(automatic=True))

    def test_aggregate_duration_limit(self):
        # mock single validator to isolate the aggregate cap from its 180s cap
        self.raw['clips'] = []
        for i in range(12):
            req = copy.deepcopy(self.req)
            req['hand_id'] = f'h{i}'
            req['table_id'] = (i % 4) + 1
            req['start_seconds'] = i * 100
            req['end_seconds'] = i * 100 + 100
            self.raw['clips'].append(req)
        with mock.patch.object(batch.single, 'validate_request', return_value=None):
            with self.assertRaisesRegex(ValueError, 'aggregate'):
                self.check()

    def write_manifest(self, raw=None):
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(raw if raw is not None else self.raw), encoding='utf-8')
        return path

    def test_read_duplicate_keys(self):
        path = self.root / 'duplicate.json'
        path.write_text('{"a":1,"a":2}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            batch.read_manifest(path)

    def test_read_nan(self):
        path = self.root / 'nan.json'
        path.write_text('{"a":NaN}', encoding='utf-8')
        with self.assertRaises(ValueError): batch.read_manifest(path)

    def test_read_symlink(self):
        p = self.write_manifest()
        link = self.root / 'link.json'; link.symlink_to(p)
        with self.assertRaises(ValueError): batch.read_manifest(link)

    def test_read_oversize(self):
        path = self.root / 'big.json'
        path.write_bytes(b'x'*(batch.MAX_MANIFEST_BYTES+1))
        with self.assertRaises(ValueError): batch.read_manifest(path)

    def test_refuse_existing_destination(self):
        manifest = self.write_manifest()
        dest = self.root / 'out'; dest.mkdir()
        with self.assertRaisesRegex(ValueError, 'new'):
            batch.export_batch(self.video, manifest, dest)

    def test_refuse_symlink_destination(self):
        manifest = self.write_manifest()
        dest = self.root / 'out'; dest.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): batch.export_batch(self.video, manifest, dest)

    def test_refuse_manifest_symlink(self):
        manifest = self.write_manifest()
        link = self.root / 'manifest-link.json'; link.symlink_to(manifest)
        with self.assertRaises(ValueError): batch.export_batch(self.video, link, self.root / 'out')

    def test_refuse_tampered_source_hash(self):
        self.raw['source_video_sha256'] = 'f'*64
        manifest = self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            batch.export_batch(self.video, manifest, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    def test_single_real_ffmpeg_and_sidecars(self):
        manifest = self.write_manifest()
        dest = self.root / 'out'
        result = batch.export_batch(self.video, manifest, dest)
        self.assertEqual(result['clip_count'], 1)
        self.assertFalse(result['automatic_clip_selection_authorized'])
        item = result['clips'][0]
        clip = dest / item['clip_file']
        self.assertTrue(clip.is_file())
        self.assertEqual(batch.single.digest(clip), item['clip_sha256'])
        self.assertTrue((dest / item['sidecar_file']).is_file())
        self.assertTrue((dest / item['request_file']).is_file())
        self.assertTrue((dest / 'batch_report.json').is_file())
        self.assertAlmostEqual(batch.single.probe(clip)[2], 1.0, delta=0.15)

    def test_four_table_real_ffmpeg(self):
        self.raw['clips'] = []
        for i in range(1, 5):
            req = copy.deepcopy(self.req)
            req['table_id'] = i
            req['hand_id'] = f'h{i}'
            req['crop']['x'] = (i % 2) * 320
            req['crop']['y'] = (i // 3) * 180
            self.raw['clips'].append(req)
        result = batch.export_batch(self.video, self.write_manifest(), self.root / 'four')
        self.assertEqual(result['clip_count'], 4)
        self.assertEqual(len(list((self.root / 'four').glob('*.mp4'))), 4)
        self.assertEqual(result['aggregate_selected_seconds'], 4.0)

    def test_failure_leaves_no_published_batch(self):
        self.raw['clips'].append(dict(self.req, hand_id='second', table_id=2))
        manifest = self.write_manifest()
        actual_export = batch.single.export
        calls = [0]
        def fail_second(*args):
            calls[0] += 1
            if calls[0] == 2: raise ValueError('Synthetic second clip failure')
            return actual_export(*args)
        with mock.patch.object(batch.single, 'export', side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, 'second clip'):
                batch.export_batch(self.video, manifest, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())
        self.assertFalse(list(self.root.glob('plo_batch_*')))

    def test_unchanged_manifest_verified(self):
        self.raw['clips'].append(dict(self.req, hand_id='second', table_id=2))
        manifest = self.write_manifest()
        real_export = batch.single.export
        calls = [0]
        def tamper(*args):
            result = real_export(*args)
            calls[0] += 1
            if calls[0] == 1:
                manifest.write_text(manifest.read_text() + ' ', encoding='utf-8')
            return result
        with mock.patch.object(batch.single, 'export', side_effect=tamper):
            with self.assertRaisesRegex(ValueError, 'changed'):
                batch.export_batch(self.video, manifest, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
