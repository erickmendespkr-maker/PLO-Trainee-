"""Synthetic-only tests; no real poker sessions or online integrations."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_four_table_visual_timeline as m


class PureTimelineTests(unittest.TestCase):
    def setUp(self):
        self.meta = {'width': 320, 'height': 192, 'duration_seconds': 12.0}
        self.black = bytes([0]) * m.FRAME_BYTES

    def change(self, rect, level=255):
        frame = bytearray(self.black)
        x, y, w, h = rect
        for row in range(y, y + h):
            frame[row*m.WIDTH+x:row*m.WIDTH+x+w] = bytes([level])*w
        return bytes(frame)

    def test_four_regions_are_disjoint(self):
        seen = set()
        for region in m.regions(4):
            x, y, w, h = region['pixel_rect']
            points = {(i, j) for i in range(x, x+w) for j in range(y, y+h)}
            self.assertFalse(points & seen)
            seen |= points
        self.assertEqual(len(seen), m.FRAME_BYTES)

    def test_one_and_two_table_regions(self):
        self.assertEqual(m.regions(1)[0]['pixel_rect'], [0, 0, 160, 96])
        self.assertEqual([x['pixel_rect'] for x in m.regions(2)],
                         [[0, 0, 80, 96], [80, 0, 80, 96]])

    def test_three_tables_supported(self):
        self.assertEqual(len(m.regions(3)), 3)

    def test_invalid_table_counts(self):
        for count in (0, 5, -1, 2.0, '4'):
            with self.subTest(count=count), self.assertRaises(m.TimelineError):
                m.regions(count)

    def test_single_quadrant_change_is_isolated(self):
        rect = m.regions(4)[2]['pixel_rect']
        frames = [(0.2, self.black), (1.3, self.change(rect))]
        result = m.analyze(frames, self.meta)
        self.assertEqual([len(t['events']) for t in result['tables']], [0, 0, 1, 0])
        self.assertEqual(result['tables'][2]['events'][0]['pts_seconds'], 1.3)

    def test_threshold_is_fraction_not_confidence(self):
        rect = m.regions(4)[0]['pixel_rect']
        frames = [(0, self.black), (1, self.change(rect, 20))]
        self.assertEqual(sum(len(t['events']) for t in m.analyze(frames, self.meta)['tables']), 0)
        frames[1] = (1, self.change(rect, 255))
        self.assertEqual(sum(len(t['events']) for t in m.analyze(frames, self.meta)['tables']), 1)

    def test_candidate_grouping_and_padding(self):
        events = [{'pts_seconds': 1.0, 'changed_fraction': .4},
                  {'pts_seconds': 3.0, 'changed_fraction': .7},
                  {'pts_seconds': 9.0, 'changed_fraction': .3}]
        candidates = m.group_candidates(events, 12)
        self.assertEqual(len(candidates), 2)
        self.assertEqual((candidates[0]['start_seconds'], candidates[0]['end_seconds']), (0, 4))
        self.assertEqual(candidates[0]['event_count'], 2)
        self.assertEqual(candidates[0]['max_changed_fraction'], .7)

    def test_last_window_clamps_to_duration(self):
        self.assertEqual(m.group_candidates([{'pts_seconds': 11.7, 'changed_fraction': .2}], 12)[0]['end_seconds'], 12)

    def test_reject_duplicate_or_nonmonotonic_pts(self):
        for times in ((0, 0), (2, 1), (math.nan, 2), (-1, 1)):
            with self.subTest(times=times), self.assertRaises(m.TimelineError):
                m.analyze([(t, self.black) for t in times], self.meta)

    def test_reject_out_of_duration(self):
        with self.assertRaises(m.TimelineError):
            m.analyze([(0, self.black), (13, self.black)], self.meta)

    def test_reject_bad_frame_length(self):
        with self.assertRaises(m.TimelineError):
            m.analyze([(0, b'bad')], self.meta)

    def test_reject_bad_threshold(self):
        for threshold in (0, -1, 1.1, float('nan')):
            with self.subTest(threshold=threshold), self.assertRaises(m.TimelineError):
                m.analyze([(0, self.black)], self.meta, threshold=threshold)

    def test_no_hand_or_ocr_claim(self):
        result = m.analyze([(0, self.black)], self.meta)
        self.assertFalse(result['hand_boundaries_verified'])
        self.assertFalse(result['ocr_performed'])
        self.assertTrue(result['manual_review_required'])
        self.assertFalse(result['actions_or_cards_identified'])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class FFmpegIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / 'four.mp4'
        filters = ','.join(
            f"drawbox=x={x}:y={y}:w=160:h=96:color=white:t=fill:enable='gte(t,{time})'"
            for x, y, time in [(0, 0, 2), (160, 0, 4), (0, 96, 6), (160, 96, 8)])
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                   '-f', 'lavfi', '-i', 'color=c=black:s=320x192:r=5:d=12',
                   '-vf', filters, '-c:v', 'mpeg4', '-q:v', '2', '-an', str(cls.path)]
        subprocess.run(command, check=True, capture_output=True, timeout=25)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ffprobe_and_real_source_pts(self):
        path, meta = m.inspect_video(self.path)
        frames = m.sampled_frames(path)
        self.assertEqual(len(frames), 12)
        self.assertEqual([t for t, _ in frames], list(range(12)))
        self.assertEqual(meta['width'], 320)
        self.assertEqual(meta['height'], 192)

    def test_source_rect_and_sample_pts_are_recorded(self):
        path, meta = m.inspect_video(self.path)
        result = m.analyze(m.sampled_frames(path), meta, 4)
        self.assertEqual(result['tables'][3]['source_pixel_rect'], [160, 96, 160, 96])
        self.assertEqual(result['sample_pts_seconds'], list(range(12)))

    def test_variable_pts_are_not_rounded_to_second_grid(self):
        vfr = Path(self.tmp.name) / 'vfr.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'color=c=black:s=320x192:r=5:d=6',
                        '-vf', 'setpts=PTS*1.2', '-fps_mode', 'passthrough',
                        '-c:v', 'mpeg4', '-q:v', '3', str(vfr)],
                       check=True, capture_output=True, timeout=25)
        path, _ = m.inspect_video(vfr)
        pts = [round(t, 2) for t, _ in m.sampled_frames(path)]
        self.assertEqual(pts, [0, 1.2, 2.4, 3.6, 4.8, 6])

    def test_four_independent_changes(self):
        path, meta = m.inspect_video(self.path)
        result = m.analyze(m.sampled_frames(path), meta, 4)
        self.assertEqual([[e['pts_seconds'] for e in r['events']] for r in result['tables']],
                         [[2], [4], [6], [8]])
        self.assertEqual(sum(len(t['candidate_windows']) for t in result['tables']), 4)

    def test_cli_json_and_hash(self):
        out = Path(self.tmp.name) / 'timeline.json'
        self.assertEqual(m.main([str(self.path), str(out), '--tables', '4']), 0)
        result = json.loads(out.read_text())
        self.assertEqual(result['video_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(result['sampled_frame_count'], 12)
        self.assertEqual(len(result['tables']), 4)
        self.assertFalse(result['hand_boundaries_verified'])
        with self.assertRaises(m.TimelineError):
            m.main([str(self.path), str(out)])

    def test_bad_media_rejected(self):
        bogus = Path(self.tmp.name) / 'bad.mp4'
        bogus.write_bytes(b'not video')
        with self.assertRaises(m.TimelineError):
            m.inspect_video(bogus)

    def test_no_file_creation_on_bad_table_count(self):
        output = Path(self.tmp.name) / 'should_not_exist.json'
        with self.assertRaises(m.TimelineError):
            m.main([str(self.path), str(output), '--tables', '5'])
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
