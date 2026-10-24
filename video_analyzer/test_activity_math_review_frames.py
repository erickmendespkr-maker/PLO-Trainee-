"""Synthetic FFmpeg and provenance tests; never claim OCR accuracy."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_hand_review_packet import build_hand_review_packet
from activity_math_readiness_triage import build_math_readiness_triage
from activity_math_review_handoff import build_math_review_handoff
from activity_math_review_frames import (build_math_review_frame_plan,
                                         export_math_review_frames)
from test_activity_consistency_frame_review import changed


class MathReviewFramesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'synthetic_four_tables.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=6:duration=5',
                        '-c:v', 'mpeg4', '-y', str(cls.video)], check=True, capture_output=True)
        sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()
        cls.queue, cls.timeline = changed()
        cls.queue['recording_sha256'] = sha
        cls.timeline['recording_sha256'] = sha
        cls.packet = build_hand_review_packet(cls.queue, cls.timeline)
        cls.triage = build_math_readiness_triage(cls.packet, cls.timeline)
        cls.handoff = build_math_review_handoff(cls.triage, cls.packet, cls.timeline)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_plan_deduplicates_same_pts_for_four_tables(self):
        plan = build_math_review_frame_plan(self.video, self.handoff, self.triage,
                                            self.packet, self.timeline)
        self.assertEqual(plan['counts']['review_tasks'], 4)
        self.assertEqual(plan['counts']['frames_planned'], 1)
        self.assertEqual({r['table_id'] for r in plan['review_tasks']}, {1, 2, 3, 4})
        self.assertEqual({r['frame_filename'] for r in plan['review_tasks']}, {'frame_0000.png'})
        self.assertIsNone(plan['frames'][0]['decoded_frame_pts_seconds'])
        self.assertFalse(plan['automatic_clip_selection_authorized'])
        self.assertFalse(plan['ready_for_equity_or_ev'])

    def test_actual_ffmpeg_png_and_hashes_and_no_overwrite(self):
        out = self.root / 'exported'
        result = export_math_review_frames(self.video, *self._json_sources(), out)
        self.assertEqual(result['counts']['frames_planned'], 1)
        frame = result['frames'][0]
        self.assertEqual(hashlib.sha256((out/frame['filename']).read_bytes()).hexdigest(), frame['sha256'])
        self.assertEqual(json.loads((out/'math_review_frames.json').read_text()), result)
        with self.assertRaises(ValueError):
            export_math_review_frames(self.video, *self._json_sources(), out)

    def _json_sources(self):
        files = []
        for name, obj in [('handoff', self.handoff), ('triage', self.triage),
                          ('packet', self.packet), ('timeline', self.timeline)]:
            path = self.root / (name + '.json')
            path.write_text(json.dumps(obj), encoding='utf-8')
            files.append(path)
        return files

    def test_cli_export_and_no_overwrite(self):
        paths = self._json_sources()
        target = self.root / 'cli_frames'
        command = [sys.executable, str(Path(__file__).with_name('activity_math_review_frames.py')),
                   str(self.video), *map(str, paths), str(target)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads((target/'math_review_frames.json').read_text())['counts']['frames_planned'], 1)
        run = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(run.returncode, 0)

    def test_reject_tampered_handoff_and_permissions(self):
        for path, value in [(['review_tasks', 0, 'decision_pts_seconds'], 3),
                            (['review_tasks', 0, 'ready_for_equity_or_ev'], True),
                            (['source_triage_sha256'], '0'*64),
                            (['counts', 'review_tasks'], 100)]:
            h = copy.deepcopy(self.handoff)
            cur = h
            for key in path[:-1]:
                cur = cur[key]
            cur[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_math_review_frame_plan(self.video, h, self.triage,
                                             self.packet, self.timeline)

    def test_reject_wrong_recording_and_invalid_budget(self):
        t = copy.deepcopy(self.timeline)
        t['recording_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            build_math_review_frame_plan(self.video, self.handoff, self.triage,
                                         self.packet, t)
        for bad in (0, True, 101, 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_math_review_frame_plan(self.video, self.handoff, self.triage,
                                             self.packet, self.timeline, max_frames=bad)

    def test_reject_symlink_input_and_no_partial_output(self):
        alias = self.root / 'video_alias.mp4'
        alias.symlink_to(self.video)
        with self.assertRaises(ValueError):
            build_math_review_frame_plan(alias, self.handoff, self.triage,
                                         self.packet, self.timeline)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._json_sources()
            broken = root / 'bad.json'
            broken.write_text('not json')
            target = root / 'must_not_exist'
            with self.assertRaises(json.JSONDecodeError):
                export_math_review_frames(self.video, broken, *paths[1:], target)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
