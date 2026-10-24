"""Synthetic crosswalk tests; no recognition or automatic hand assignment."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_reviewed_hand_timeline import build_reviewed_hand_timeline
from activity_snapshot_chain import canonical_sha256
from activity_visual_timeline_crosswalk import (build_visual_timeline_crosswalk,
                                                 export_visual_timeline_crosswalk)
from test_activity_reviewed_hand_timeline import fixture


def sources():
    timeline = build_reviewed_hand_timeline(fixture())
    items = []
    for rank, (table, start, end) in enumerate(((1, .5, 2.5), (2, 1., 3.),
                                                 (3, 5., 6.), (4, 5., 6.)), 1):
        items.append({'pixel_review_rank': rank, 'table_id': table,
                      'review_window_index': 0, 'region_label_hypothesis': 'board',
                      'start_pts_seconds': start, 'end_pts_seconds': end,
                      'peak_luma_difference': .5, 'comparison_count': 1,
                      'confidence_in_poker_semantics': 'not_calibrated',
                      'confidence_in_region_mapping': 'not_calibrated',
                      'requires_manual_review': True, 'first_frame': 'a.png',
                      'last_frame': 'b.png'})
    queue = {'schema_version': 1, 'analysis_status': 'unverified_region_pixel_review_queue',
             'recording_sha256': timeline['recording_sha256'],
             'timestamp_semantics': 'decoded_source_pts_seconds_not_exact_hand_boundary',
             'source_region_change_hints_sha256': 'c'*64,
             'source_contact_sheet_sha256': 'd'*64,
             'source_region_profile_sha256': 'e'*64,
             'ranking_method': 'descending_peak_mean_absolute_luma_difference_only',
             'requires_manual_review': True,
             'ready_for_equity_or_ev': False,
             'automatic_hand_boundaries_authorized': False,
             'automatic_clip_selection_authorized': False,
             'strategic_error_established': False,
             'total_candidate_intervals': len(items), 'omitted_due_to_budget': 0,
             'candidates': items}
    return queue, timeline


def alignment(queue, timeline, offset=0):
    return {'schema_version': 1, 'recording_sha256': queue['recording_sha256'],
            'queue_timestamp_semantics': queue['timestamp_semantics'],
            'timeline_timestamp_semantics': timeline['timestamp_semantics'],
            'reviewer_confirmed_same_recording_pts_origin': True,
            'queue_pts_minus_timeline_pts_seconds': offset,
            'reviewer_note': 'Synthetic shared clock; human confirmation required on real recordings.'}


class CrosswalkTests(unittest.TestCase):
    def test_default_is_safe_unaligned_no_links(self):
        q, t = sources()
        out = build_visual_timeline_crosswalk(q, t)
        self.assertEqual(out['counts']['without_alignment'], 4)
        self.assertTrue(all(not x['possible_human_assigned_hands'] for x in out['associations']))
        self.assertFalse(out['automatic_clip_selection_authorized'])
        self.assertFalse(out['ready_for_equity_or_ev'])
        self.assertFalse(out['strategic_error_established'])

    def test_four_tables_single_overlap_and_unmatched(self):
        q, t = sources()
        out = build_visual_timeline_crosswalk(q, t, alignment=alignment(q, t))
        self.assertEqual(out['counts']['single_overlap_unverified'], 2)
        self.assertEqual(out['counts']['without_observed_overlap'], 2)
        self.assertEqual(out['associations'][0]['possible_human_assigned_hands'][0]
                         ['hand_id_human_assigned_not_verified'], 'h1')
        self.assertEqual(out['associations'][1]['possible_human_assigned_hands'][0]
                         ['hand_id_human_assigned_not_verified'], 'h2')
        self.assertEqual(out['associations'][0]['possible_human_assigned_hands'][0]
                         ['observed_event_indices_within_candidate'], [1, 2])
        self.assertTrue(all(x['hand_assigned_automatically'] is False for x in out['associations']))

    def test_ambiguous_multiple_hands_not_assigned(self):
        q, t = sources()
        # Move a separately indexed synthetic hand into the same table/time span.
        # Do not duplicate observation indices (upstream would reject them).
        t['hands'][1]['table_id'] = 1
        out = build_visual_timeline_crosswalk(q, t, alignment=alignment(q, t))
        self.assertEqual(out['counts']['ambiguous_overlap_unverified'], 1)
        self.assertEqual(len(out['associations'][0]['possible_human_assigned_hands']), 2)

    def test_manual_offset_required_for_shifted_clock(self):
        q, t = sources()
        for item in q['candidates']:
            item['start_pts_seconds'] += 100
            item['end_pts_seconds'] += 100
        without = build_visual_timeline_crosswalk(q, t)
        self.assertEqual(without['counts']['without_alignment'], 4)
        out = build_visual_timeline_crosswalk(q, t, alignment=alignment(q, t, 100))
        self.assertEqual(out['counts']['single_overlap_unverified'], 2)

    def test_cross_video_and_expected_digest_rejected(self):
        q, t = sources()
        q['recording_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'Different recording'):
            build_visual_timeline_crosswalk(q, t)
        q, t = sources()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_visual_timeline_crosswalk(q, t, expected_queue_sha256='0'*64)
        out = build_visual_timeline_crosswalk(q, t,
              expected_queue_sha256=canonical_sha256(q),
              expected_timeline_sha256=canonical_sha256(t))
        self.assertEqual(out['source_roi_queue_sha256'], canonical_sha256(q))

    def test_reject_unverified_or_malformed_sources(self):
        for field, value in [('ready_for_equity_or_ev', True),
                             ('analysis_status', 'automatic_poker_action'),
                             ('recording_sha256', 'broken')]:
            q, t = sources()
            q[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_visual_timeline_crosswalk(q, t)
        q, t = sources()
        q['candidates'][0]['start_pts_seconds'] = float('nan')
        with self.assertRaises(ValueError):
            build_visual_timeline_crosswalk(q, t)
        q, t = sources()
        q['candidates'][0]['table_id'] = True
        with self.assertRaises(ValueError):
            build_visual_timeline_crosswalk(q, t)
        q, t = sources()
        q['candidates'][0]['pixel_review_rank'] = 4
        with self.assertRaises(ValueError):
            build_visual_timeline_crosswalk(q, t)
        q, t = sources()
        t['hands'][0]['events'][0]['timestamp'] = -1
        with self.assertRaises(ValueError):
            build_visual_timeline_crosswalk(q, t)

    def test_alignment_declaration_must_be_explicit_and_matching(self):
        q, t = sources()
        for key, val in [('reviewer_confirmed_same_recording_pts_origin', False),
                         ('queue_pts_minus_timeline_pts_seconds', float('inf')),
                         ('reviewer_note', ''), ('recording_sha256', 'f'*64)]:
            a = alignment(q, t)
            a[key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_visual_timeline_crosswalk(q, t, alignment=a)

    def test_no_mutation_and_determinism(self):
        q, t = sources()
        a = alignment(q, t)
        original = copy.deepcopy((q, t, a))
        self.assertEqual(build_visual_timeline_crosswalk(q, t, alignment=a),
                         build_visual_timeline_crosswalk(q, t, alignment=a))
        self.assertEqual((q, t, a), original)

    def test_cli_and_no_overwrite(self):
        q, t = sources()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            qp, tp, ap, output = [root / name for name in ('queue.json', 'timeline.json',
                                                           'alignment.json', 'crosswalk.json')]
            qp.write_text(json.dumps(q), encoding='utf-8')
            tp.write_text(json.dumps(t), encoding='utf-8')
            ap.write_text(json.dumps(alignment(q, t)), encoding='utf-8')
            proc = subprocess.run([sys.executable,
                                   str(Path(__file__).with_name('activity_visual_timeline_crosswalk.py')),
                                   str(qp), str(tp), str(output), '--alignment-json', str(ap)],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(output.read_text())['counts']['single_overlap_unverified'], 2)
            with self.assertRaises(ValueError):
                export_visual_timeline_crosswalk(qp, tp, output)
            with self.assertRaises(ValueError):
                export_visual_timeline_crosswalk(qp, tp, qp)


if __name__ == '__main__':
    unittest.main()
