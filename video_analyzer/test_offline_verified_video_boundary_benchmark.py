import json
import subprocess
import tempfile
from pathlib import Path
import unittest

import offline_verified_video_boundary_benchmark as m


class VerifiedVideoBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.video = Path(cls.base.name) / 'four_tables.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=5:duration=3',
                        '-c:v', 'mpeg4', '-q:v', '4', str(cls.video)],
                       check=True, timeout=30)
        cls.hash = m.file_hash(cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.proposals = {
            'schema_version': 1, 'status': 'unverified_offline_hand_boundary_proposals',
            'ready_for_equity_or_ev': False, 'recording_sha256': self.hash,
            'boundaries': [{'table_id': t, 'start_seconds': 0.2, 'end_seconds': 2.2,
                            'status': 'needs_manual_review', 'source_sample_indices': [0, 1]}
                           for t in range(1, 5)]}
        self.labels = {
            'schema_version': 1, 'status': 'human_annotated_hand_boundaries',
            'recording_sha256': self.hash,
            'hands': [{'table_id': t, 'start_seconds': 0.3, 'end_seconds': 2.3}
                      for t in range(1, 5)]}

    def execute(self, video=None, ffprobe='ffprobe', timeline_basis='video-relative'):
        pp, gg, out = [self.path / x for x in ('proposals.json', 'labels.json', 'result.json')]
        pp.write_text(json.dumps(self.proposals))
        gg.write_text(json.dumps(self.labels))
        return m.run(video or self.video, pp, gg, out, ffprobe=ffprobe,
                     timeline_basis=timeline_basis)

    def test_four_tables_real_ffprobe_hash_and_matched(self):
        report = self.execute()
        self.assertEqual(report['summary']['matched'], 4)
        self.assertTrue(report['recording_hash_verified'])
        self.assertFalse(report['human_labels_verified_against_video'])
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertEqual(report['recording_sha256_verified_against_bytes'], self.hash)
        self.assertEqual(json.loads((self.path/'result.json').read_text())['summary']['matched'], 4)

    def test_reject_wrong_recording_sha(self):
        self.proposals['recording_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'hashes'):
            self.execute()
        self.assertFalse((self.path/'result.json').exists())

    def test_reject_wrong_human_label_sha(self):
        self.labels['recording_sha256'] = 'f' * 64
        with self.assertRaises(ValueError):
            self.execute()

    def test_reject_boundary_outside_duration(self):
        self.proposals['boundaries'][0]['end_seconds'] = 5
        with self.assertRaisesRegex(ValueError, 'outside recording'):
            self.execute()

    def test_reject_label_outside_duration(self):
        self.labels['hands'][0]['end_seconds'] = 5
        with self.assertRaisesRegex(ValueError, 'outside recording'):
            self.execute()

    def test_reject_overlapping_hands(self):
        self.labels['hands'].append({'table_id': 1, 'start_seconds': 1, 'end_seconds': 2.5})
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            self.execute()

    def test_reject_video_symlink(self):
        link = self.path / 'link.mp4'
        link.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.execute(video=link)

    def test_reject_nonvideo_bytes_even_with_matching_hash(self):
        bad = self.path / 'invalid.mp4'
        bad.write_bytes(b'not a video')
        self.proposals['recording_sha256'] = m.file_hash(bad)
        self.labels['recording_sha256'] = m.file_hash(bad)
        with self.assertRaisesRegex(ValueError, 'ffprobe rejected'):
            self.execute(video=bad)

    def test_reject_unsupported_extension(self):
        invalid = self.path / 'file.txt'
        invalid.write_bytes(b'abc')
        with self.assertRaisesRegex(ValueError, 'unsupported video extension'):
            self.execute(video=invalid)

    def test_missing_ffprobe(self):
        with self.assertRaisesRegex(ValueError, 'ffprobe unavailable'):
            self.execute(ffprobe='__ffprobe_does_not_exist__')

    def test_output_create_only(self):
        self.execute()
        with self.assertRaisesRegex(ValueError, 'new file'):
            self.execute()

    def test_reject_promoted_proposals(self):
        self.proposals['ready_for_equity_or_ev'] = True
        with self.assertRaisesRegex(ValueError, 'promoted'):
            self.execute()

    def test_source_pts_basis_with_zero_start(self):
        result = self.execute(timeline_basis='source-pts')
        self.assertEqual(result['timestamp_basis'], 'source-pts')
        self.assertAlmostEqual(result['timestamp_origin_seconds'], 0, places=2)

    def test_nonzero_pts_offset_and_explicit_basis(self):
        offset_video = self.path / 'offset.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=5:duration=3',
                        '-output_ts_offset', '5', '-c:v', 'mpeg4', str(offset_video)],
                       check=True, timeout=30)
        digest = m.file_hash(offset_video)
        self.proposals['recording_sha256'] = digest
        self.labels['recording_sha256'] = digest
        for row in self.proposals['boundaries']:
            row['start_seconds'] += 5
            row['end_seconds'] += 5
        for row in self.labels['hands']:
            row['start_seconds'] += 5
            row['end_seconds'] += 5
        result = self.execute(video=offset_video, timeline_basis='source-pts')
        self.assertEqual(result['summary']['matched'], 4)
        self.assertAlmostEqual(result['timestamp_origin_seconds'], 5, places=2)

    def test_nonzero_pts_rejects_wrong_basis(self):
        offset_video = self.path / 'offset.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=5:duration=3',
                        '-output_ts_offset', '5', '-c:v', 'mpeg4', str(offset_video)],
                       check=True, timeout=30)
        digest = m.file_hash(offset_video)
        self.proposals['recording_sha256'] = digest
        self.labels['recording_sha256'] = digest
        for row in self.proposals['boundaries']:
            row['start_seconds'] += 5
            row['end_seconds'] += 5
        for row in self.labels['hands']:
            row['start_seconds'] += 5
            row['end_seconds'] += 5
        with self.assertRaisesRegex(ValueError, 'outside recording'):
            self.execute(video=offset_video, timeline_basis='video-relative')

    def test_reject_invalid_timeline_basis(self):
        with self.assertRaisesRegex(ValueError, 'timeline basis'):
            self.execute(timeline_basis='wall-clock')

    def test_reject_duplicate_json_keys(self):
        pp, gg, out = [self.path / x for x in ('proposals.json', 'labels.json', 'result.json')]
        pp.write_text('{"schema_version":1,"schema_version":1}')
        gg.write_text(json.dumps(self.labels))
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            m.run(self.video, pp, gg, out)


if __name__ == '__main__':
    unittest.main()
