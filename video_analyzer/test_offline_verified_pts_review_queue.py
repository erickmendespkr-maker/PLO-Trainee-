"""Real FFmpeg/FFprobe integration tests with synthetic four-region recordings."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_verified_pts_review_queue import build, measure_origin, run
from offline_hand_ocr_review_queue import digest
from test_offline_hand_ocr_review_queue import make_fixture

HERE = Path(__file__).resolve().parent


def write(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')


class VerifiedPTSReviewQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory()
        cls.fixture = make_fixture(cls.fixture_temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / 'video.mp4'
        shutil.copyfile(self.fixture / 'synthetic_4tables.mp4', self.video)
        self.bundle = self.root / 'bundle'
        shutil.copytree(self.fixture / 'bundle', self.bundle)
        self.ocr = self.root / 'ocr.json'
        shutil.copyfile(self.fixture / 'synthetic_original_ocr_report.json', self.ocr)
        self.hands = self.root / 'hands.json'
        write(self.hands, {'schema_version': 1, 'status': 'human_annotated_hand_boundaries',
                           'recording_sha256': digest(self.video),
                           'hands': [{'table_id': i, 'start_seconds': 0, 'end_seconds': 1}
                                     for i in range(1, 5)]})
        self.output = self.root / 'queue.json'

    def execute(self):
        return run(self.video, self.bundle, self.ocr, self.hands, self.output)

    def replace_video_with_offset(self, offset=5):
        video2 = self.root / 'offset.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-i', str(self.video), '-vf', f'setpts=PTS+{offset}/TB',
                        '-fps_mode', 'passthrough', '-an', '-c:v', 'libx264',
                        '-preset', 'ultrafast', str(video2)],
                       check=True, capture_output=True, timeout=30)
        self.video = video2
        source_path = self.bundle / 'region_samples.json'
        source = json.loads(source_path.read_text())
        source['recording_sha256'] = digest(video2)
        for sample in source['samples']:
            sample['decoded_source_pts_seconds'] += offset
        write(source_path, source)
        ocr = json.loads(self.ocr.read_text())
        ocr['recording_sha256'] = digest(video2)
        ocr['source_region_samples_sha256'] = digest(source_path)
        for c in ocr['candidates']:
            c['decoded_source_pts_seconds'] += offset
        write(self.ocr, ocr)
        hands = json.loads(self.hands.read_text())
        hands['recording_sha256'] = digest(video2)
        write(self.hands, hands)

    def test_real_ffmpeg_zero_pts_and_four_tables(self):
        result = self.execute()
        self.assertEqual(result['source_pts_origin_seconds_verified_from_decoded_video'], 0)
        self.assertEqual(result['observations_assigned'], 4)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['ocr_fields_verified'])
        self.assertEqual(json.loads(self.output.read_text()), result)

    def test_nonzero_pts_origin_measured_not_assumed(self):
        self.replace_video_with_offset()
        result = self.execute()
        self.assertEqual(result['source_pts_origin_seconds_verified_from_decoded_video'], 5)
        self.assertEqual(result['observations_assigned'], 4)
        self.assertEqual([x['observations'][0]['playback_seconds_using_declared_origin']
                          for x in result['hands']], [0] * 4)

    def test_ffprobe_stream_start_matches_decoded_frame(self):
        self.replace_video_with_offset(5)
        evidence = measure_origin(self.video)
        self.assertEqual(evidence['ffprobe_video_stream_start_seconds'], 5)
        self.assertEqual(evidence['first_decoded_video_frame_pts_seconds'], 5)

    def test_reject_source_pts_offset_inconsistent_with_video(self):
        source_path = self.bundle / 'region_samples.json'
        source = json.loads(source_path.read_text())
        source['samples'][0]['decoded_source_pts_seconds'] = 5
        write(source_path, source)
        ocr = json.loads(self.ocr.read_text())
        ocr['source_region_samples_sha256'] = digest(source_path)
        for candidate in ocr['candidates']:
            candidate['decoded_source_pts_seconds'] = 5
        write(self.ocr, ocr)
        with self.assertRaisesRegex(ValueError, 'outside measured video timeline'):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_reject_ocr_timestamp_inconsistent_with_source(self):
        ocr = json.loads(self.ocr.read_text())
        ocr['candidates'][0]['decoded_source_pts_seconds'] = 3
        write(self.ocr, ocr)
        with self.assertRaisesRegex(ValueError, 'timestamp'):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_reject_video_sha_mismatch(self):
        self.video.write_bytes(self.video.read_bytes() + b'change')
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_reject_source_duration_disagreement(self):
        path = self.bundle / 'region_samples.json'
        source = json.loads(path.read_text())
        source['recording_duration_seconds'] = 999
        write(path, source)
        ocr = json.loads(self.ocr.read_text())
        ocr['source_region_samples_sha256'] = digest(path)
        write(self.ocr, ocr)
        with self.assertRaisesRegex(ValueError, 'duration disagrees'):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_reject_existing_output_without_modifying(self):
        self.execute()
        original = digest(self.output)
        with self.assertRaisesRegex(ValueError, 'output must be new'):
            self.execute()
        self.assertEqual(original, digest(self.output))

    def test_reject_symlink_video(self):
        alias = self.root / 'alias.mp4'
        alias.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, 'unsafe recording'):
            run(alias, self.bundle, self.ocr, self.hands, self.output)
        self.assertFalse(self.output.exists())

    def test_reject_bad_video_format(self):
        invalid = self.root / 'fake.mp4'
        invalid.write_bytes(b'not a recording')
        with self.assertRaises(ValueError):
            measure_origin(invalid)

    def test_reject_ambiguous_hand_intervals(self):
        hands = json.loads(self.hands.read_text())
        hands['hands'].append(copy.deepcopy(hands['hands'][0]))
        write(self.hands, hands)
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_cli_real_ffmpeg(self):
        proc = subprocess.run(['python', str(HERE / 'offline_verified_pts_review_queue.py'),
                               str(self.video), str(self.bundle), str(self.ocr),
                               str(self.hands), str(self.output)],
                              capture_output=True, text=True, timeout=40)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['observations_assigned'], 4)


if __name__ == '__main__':
    unittest.main()
