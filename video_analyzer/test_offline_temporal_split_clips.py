"""Synthetic offline tests: split geometry intervals without claiming strategy facts."""
import json
from pathlib import Path
import subprocess
from unittest import mock

import offline_ev_table_crop as crop
import offline_temporal_split_clips as split
from test_offline_temporal_batch_crops import TemporalBatchTests


class TemporalSplitTests(TemporalBatchTests):
    def test_split_preflight_four_parts_and_near_blocked(self):
        _, _, plans, blocked, _ = split.preflight(self.video, self.batch_dir,
                                                   self.review, self.out)
        self.assertEqual(len(plans), 4)
        self.assertEqual([p['clip_id'] for p in plans],
                         ['first', 'second', 'cross', 'cross'])
        self.assertEqual([p['segment_index'] for p in plans[-2:]], [1, 2])
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['clip_id'], 'near')

    def test_transition_guard_omission_explicit(self):
        *_, plans, _, _ = split.preflight(self.video, self.batch_dir,
                                          self.review, self.out)
        cross = [p for p in plans if p['clip_id'] == 'cross']
        self.assertEqual([(p['start'], p['end']) for p in cross],
                         [(1.0, 2.75), (3.25, 4.0)])
        self.assertEqual(cross[0]['omitted_intervals'],
                         [{'start_seconds': 2.75, 'end_seconds': 3.25}])
        self.assertEqual([p['decision_in_part'] for p in cross], [True, False])

    def test_no_omission_for_static_safe_clip(self):
        *_, plans, _, _ = split.preflight(self.video, self.batch_dir,
                                          self.review, self.out)
        self.assertEqual(plans[0]['omitted_intervals'], [])

    def test_short_piece_discarded_and_reported(self):
        segments = [{'start_seconds': 0, 'end_seconds': 3,
                     'regions': [{'table_id': 'T1'}]},
                    {'start_seconds': 3, 'end_seconds': 6,
                     'regions': [{'table_id': 'T1'}]}]
        pieces = split.intersections(2.6, 3.7, segments, 'T1')
        self.assertEqual(len(pieces), 0)
        self.assertEqual(split.omitted_intervals(2.6, 3.7, pieces),
                         [{'start_seconds': 2.6, 'end_seconds': 3.7}])

    def test_review_hash_mismatch(self):
        p = self.mutate_review(lambda r: r.update(source_video_sha256='0' * 64))
        with self.assertRaises(ValueError):
            split.preflight(self.video, self.batch_dir, p, self.out)

    def test_modified_clip_rejected(self):
        folder = self.mutate_batch(lambda b: None)
        with (folder / 'cross.mp4').open('ab') as f:
            f.write(b'not the original')
        with self.assertRaises(ValueError):
            split.preflight(self.video, folder, self.review, self.out)

    def test_existing_output_collision_rejected(self):
        (self.out / 'split_first_s01.mp4').write_bytes(b'existing')
        with self.assertRaises(ValueError):
            split.preflight(self.video, self.batch_dir, self.review, self.out)

    def test_near_transition_never_rendered(self):
        _, _, plans, blocked, _ = split.preflight(self.video, self.batch_dir,
                                                   self.review, self.out)
        self.assertNotIn('near', [p['clip_id'] for p in plans])
        self.assertEqual(blocked[0]['reason'], 'decision_near_uncertain_transition')

    def test_render_real_ffmpeg_and_integrity(self):
        result = split.export(self.video, self.batch_dir, self.review, self.out)
        self.assertEqual((result['rendered_count'], result['blocked_count']), (4, 1))
        self.assertFalse(result['automatic_ocr_math_authorization'])
        self.assertFalse(result['table_identity_verified'])
        self.assertEqual(len(list(self.out.iterdir())), 9)
        for item in result['parts']:
            mp4 = self.out / item['filename']
            meta = json.loads((self.out / item['metadata']).read_text())
            self.assertEqual(item['sha256'], crop.digest(mp4))
            self.assertEqual(item['sha256'], meta['sha256'])
            self.assertFalse(meta['automatic_ocr_math_authorization'])
            self.assertEqual(crop.media_info(mp4)[:2],
                             (meta['region_claim']['width'], meta['region_claim']['height']))
        self.assertEqual(result['parts'][-1]['omitted_intervals_seconds'],
                         [{'start_seconds': 2.75, 'end_seconds': 3.25}])

    def test_render_failure_rolls_back(self):
        prepared = split.preflight(self.video, self.batch_dir, self.review, self.out)
        original = split.subprocess.run
        count = {'n': 0}
        def fail_second(*args, **kwargs):
            count['n'] += 1
            if count['n'] == 2:
                raise subprocess.CalledProcessError(1, args[0])
            return original(*args, **kwargs)
        with mock.patch.object(split, 'preflight', return_value=prepared):
            with mock.patch.object(split.subprocess, 'run', side_effect=fail_second):
                with self.assertRaises(subprocess.CalledProcessError):
                    split.export(self.video, self.batch_dir, self.review, self.out)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_ledger_collision_rejected(self):
        (self.out / 'temporal_split_report.json').write_text('{}')
        with self.assertRaises(ValueError):
            split.preflight(self.video, self.batch_dir, self.review, self.out)

    def test_cli_requires_arguments(self):
        with self.assertRaises(SystemExit):
            split.main([])
