"""Synthetic-only tests for cautious audit-to-ROI frame suggestions."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_consistency_frame_review import (build_consistency_frame_review,
                                               export_consistency_frame_review)
from activity_snapshot_chain import canonical_sha256
from test_activity_visual_timeline_crosswalk import sources, alignment


def changed():
    q, t = sources()
    # A board prefix conflict on table 1 at PTS 3; prior board at PTS 1.
    t['hands'][0]['events'][3]['board_visible'] = ['Qs', 'Js', '9h', '9d']
    return q, t


class ConsistencyFrameReviewTests(unittest.TestCase):
    def test_without_alignment_no_frame_suggestions(self):
        q, t = changed()
        result = build_consistency_frame_review(q, t)
        self.assertEqual(result['counts']['audit_flags'], 1)
        self.assertEqual(result['counts']['suggested_roi_intervals'], 0)
        self.assertEqual(result['flags'][0]['status'], 'pts_alignment_not_declared')
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['automatic_clip_selection_authorized'])

    def test_aligned_board_flag_matches_only_correct_table_and_roi(self):
        q, t = changed()
        result = build_consistency_frame_review(q, t, alignment=alignment(q, t))
        self.assertEqual(result['counts']['flags_with_suggested_roi_frames'], 1)
        flag = result['flags'][0]
        self.assertEqual(flag['hand_id_human_assigned_not_verified'], 'h1')
        self.assertEqual(flag['flag_interval_timeline_pts'], [1, 3])
        self.assertEqual(flag['suggested_roi_frames'][0]['pixel_review_rank'], 1)
        self.assertFalse(flag['suggested_roi_frames'][0]['poker_event_recognized'])
        self.assertFalse(flag['strategic_error_established'])

    def test_region_mismatch_does_not_suggest(self):
        q, t = changed()
        q['candidates'][0]['region_label_hypothesis'] = 'pot'
        result = build_consistency_frame_review(q, t, alignment=alignment(q, t))
        self.assertEqual(result['flags'][0]['status'], 'no_unambiguous_same_hand_roi_overlap')

    def test_ambiguous_hand_overlap_is_never_assigned(self):
        q, t = changed()
        t['hands'][1]['table_id'] = 1
        result = build_consistency_frame_review(q, t, alignment=alignment(q, t))
        self.assertEqual(result['counts']['suggested_roi_intervals'], 0)

    def test_shifted_pts_requires_declared_offset(self):
        q, t = changed()
        q['candidates'][0]['start_pts_seconds'] += 100
        q['candidates'][0]['end_pts_seconds'] += 100
        self.assertEqual(build_consistency_frame_review(q, t)['counts']['suggested_roi_intervals'], 0)
        result = build_consistency_frame_review(q, t, alignment=alignment(q, t, 100))
        self.assertEqual(result['counts']['suggested_roi_intervals'], 1)

    def test_single_observation_collision_can_suggest_frame(self):
        q, t = sources()
        t['hands'][0]['events'][1]['board_visible'] = ['As', 'Js', 'Ts']
        q['candidates'][0]['region_label_hypothesis'] = 'board'
        result = build_consistency_frame_review(q, t, alignment=alignment(q, t))
        collision = next(f for f in result['flags'] if f['audit_kind'] == 'visible_board_hero_collision')
        self.assertEqual(collision['flag_interval_timeline_pts'], [1, 1])
        self.assertEqual(len(collision['suggested_roi_frames']), 1)

    def test_budget_and_determinism(self):
        q, t = changed()
        q['candidates'] = [copy.deepcopy(q['candidates'][0]) for _ in range(4)]
        for i, item in enumerate(q['candidates'], 1):
            item['pixel_review_rank'] = i
            item['review_window_index'] = i
        q['total_candidate_intervals'] = len(q['candidates'])
        before = copy.deepcopy((q, t))
        result = build_consistency_frame_review(q, t, alignment=alignment(q, t), max_frames_per_flag=2)
        self.assertEqual(result['flags'][0]['total_matching_roi_candidates'], 4)
        self.assertEqual(result['flags'][0]['omitted_due_to_per_flag_budget'], 2)
        self.assertEqual(len(result['flags'][0]['suggested_roi_frames']), 2)
        self.assertEqual((q, t), before)
        self.assertEqual(result, build_consistency_frame_review(q, t,
                         alignment=alignment(q, t), max_frames_per_flag=2))

    def test_reject_wrong_source_and_hash(self):
        q, t = changed()
        q['recording_sha256'] = 'f'*64
        with self.assertRaises(ValueError):
            build_consistency_frame_review(q, t)
        q, t = changed()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_consistency_frame_review(q, t, expected_timeline_sha256='0'*64)
        result = build_consistency_frame_review(q, t,
                  expected_queue_sha256=canonical_sha256(q),
                  expected_timeline_sha256=canonical_sha256(t))
        self.assertEqual(result['source_reviewed_timeline_sha256'], canonical_sha256(t))

    def test_reject_unsafe_authority_and_invalid_budget(self):
        q, t = changed()
        t['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build_consistency_frame_review(q, t)
        q, t = changed()
        for bad in (0, 21, True, 1.2):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_consistency_frame_review(q, t, max_frames_per_flag=bad)

    def test_cli_roundtrip_and_no_overwrite(self):
        q, t = changed()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            qp, tp, ap, out = [root/name for name in
                               ('queue.json', 'timeline.json', 'alignment.json', 'frames.json')]
            qp.write_text(json.dumps(q), encoding='utf-8')
            tp.write_text(json.dumps(t), encoding='utf-8')
            ap.write_text(json.dumps(alignment(q, t)), encoding='utf-8')
            command = [sys.executable, str(Path(__file__).with_name('activity_consistency_frame_review.py')),
                       str(qp), str(tp), str(out), '--alignment-json', str(ap)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(out.read_text())['counts']['suggested_roi_intervals'], 1)
            with self.assertRaises(ValueError):
                export_consistency_frame_review(qp, tp, out)
            with self.assertRaises(ValueError):
                export_consistency_frame_review(qp, tp, qp)


if __name__ == '__main__':
    unittest.main()
