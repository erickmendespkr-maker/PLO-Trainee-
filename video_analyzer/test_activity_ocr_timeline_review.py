"""Synthetic tests for OCR-to-reviewed-timeline hints; never poker truth."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_ocr_timeline_review import build_ocr_timeline_review, write_ocr_timeline_review
from activity_reviewed_hand_timeline import build_reviewed_hand_timeline
from activity_snapshot_chain import canonical_sha256
from test_activity_reviewed_hand_timeline import fixture


def sources():
    timeline = build_reviewed_hand_timeline(fixture())
    ocr = {'schema_version': 1, 'analysis_status': 'unverified_ocr_candidates_only',
           'requires_manual_review': True, 'ready_for_equity_or_ev': False,
           'recording_sha256': timeline['recording_sha256'],
           'evidence_manifest_sha256': 'd'*64,
           'timestamp_semantics': 'decoded_filtergraph_pts_not_capture_time',
           'candidates': []}
    for table in range(1, 5):
        ocr['candidates'].append({'table_id': table, 'timestamp': 1., 'field': 'board',
            'raw_text': 'Qs Js Ts', 'parsed_candidate': ['Qs', 'Js', 'Ts'],
            'mean_engine_confidence': .99, 'status': 'candidate_unverified',
            'source': 'tesseract_manually_selected_roi',
            'source_image': f'table_{table:02d}/frame_00001.png',
            'source_sha256': 'a'*64, 'source_pts_ticks': 1000,
            'timestamp_semantics': ocr['timestamp_semantics'],
            'evidence_manifest_sha256': ocr['evidence_manifest_sha256']})
    return ocr, timeline


def align(o, t, offset=0):
    return {'schema_version': 1, 'recording_sha256': o['recording_sha256'],
            'ocr_timestamp_semantics': o['timestamp_semantics'],
            'timeline_timestamp_semantics': t['timestamp_semantics'],
            'reviewer_confirmed_same_recording_pts_origin': True,
            'ocr_pts_minus_timeline_pts_seconds': offset,
            'reviewer_note': 'Synthetic shared source PTS, reviewed explicitly.'}


class OCRTimelineReviewTests(unittest.TestCase):
    def test_unaligned_does_not_associate_even_same_pts(self):
        o, t = sources()
        result = build_ocr_timeline_review(o, t)
        self.assertEqual(len(result['candidates']), 4)
        self.assertTrue(all(not x['possible_human_assigned_hands_not_verified'] for x in result['candidates']))
        self.assertTrue(all(x['status'] == 'clock_alignment_not_declared' for x in result['candidates']))
        self.assertFalse(result['ready_for_equity_or_ev'])

    def test_four_tables_match_exact_field_without_authorizing_math(self):
        o, t = sources()
        result = build_ocr_timeline_review(o, t, alignment=align(o, t))
        self.assertTrue(all('agrees' in x['status'] for x in result['candidates']))
        self.assertEqual([x['possible_human_assigned_hands_not_verified'][0]['hand_id']
                          for x in result['candidates']], ['h1', 'h2', 'h3', 'h4'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['strategic_error_established'])

    def test_conflicts_disagreements_and_unparseable(self):
        o, t = sources()
        o['candidates'][0]['parsed_candidate'] = ['Qs', 'Js', '9h']
        other = copy.deepcopy(o['candidates'][0])
        other['parsed_candidate'] = None
        other['status'] = 'needs_manual_review'
        o['candidates'].append(other)
        o['candidates'].append({**copy.deepcopy(other), 'parsed_candidate': ['Qs', 'Js', 'Ts']})
        result = build_ocr_timeline_review(o, t, alignment=align(o, t))
        self.assertEqual(result['counts']['reviewed_label_disagreements'], 1)
        self.assertEqual(result['counts']['conflicting_ocr_candidates'], 3)
        self.assertEqual(result['candidates'][4]['status'], 'ocr_unparseable_manual_review')

    def test_no_fuzzy_join_and_offset_declaration(self):
        o, t = sources()
        o['candidates'][0]['timestamp'] = 1.01
        result = build_ocr_timeline_review(o, t, alignment=align(o, t))
        self.assertEqual(result['candidates'][0]['status'], 'no_exact_reviewed_field_at_pts')
        o['candidates'][0]['timestamp'] = 101.
        result = build_ocr_timeline_review(o, t, alignment=align(o, t, 100))
        self.assertIn('agrees', result['candidates'][0]['status'])
        self.assertEqual(result['candidates'][1]['status'], 'no_exact_reviewed_field_at_pts')

    def test_reject_cross_video_and_hash_tamper(self):
        o, t = sources()
        o['recording_sha256'] = 'f'*64
        with self.assertRaises(ValueError):
            build_ocr_timeline_review(o, t)
        o, t = sources()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_ocr_timeline_review(o, t, expected_ocr_sha256='0'*64)
        build_ocr_timeline_review(o, t, expected_ocr_sha256=canonical_sha256(o))

    def test_reject_malformed_candidate_and_unsafe_flags(self):
        for field, value in [('table_id', True), ('timestamp', float('nan')),
                             ('source_image', '../evil.png'), ('source_sha256', 'broken'),
                             ('source_pts_ticks', True), ('parsed_candidate', ['As']*3),
                             ('mean_engine_confidence', 2), ('field', 'action')]:
            o, t = sources()
            o['candidates'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_ocr_timeline_review(o, t)
        o, t = sources()
        t['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build_ocr_timeline_review(o, t)

    def test_reject_forged_alignment(self):
        o, t = sources()
        a = align(o, t)
        a['reviewer_confirmed_same_recording_pts_origin'] = False
        with self.assertRaises(ValueError):
            build_ocr_timeline_review(o, t, alignment=a)

    def test_json_cli_and_no_overwrite(self):
        o, t = sources()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name, obj in [('ocr.json', o), ('timeline.json', t), ('alignment.json', align(o, t))]:
                (d/name).write_text(json.dumps(obj))
            output = d/'out.json'
            cmd = [sys.executable, str(Path(__file__).with_name('activity_ocr_timeline_review.py')),
                   str(d/'ocr.json'), str(d/'timeline.json'), str(output),
                   '--alignment-json', str(d/'alignment.json')]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.assertEqual(len(json.loads(output.read_text())['candidates']), 4)
            with self.assertRaises(ValueError):
                write_ocr_timeline_review(d/'ocr.json', d/'timeline.json', output)


if __name__ == '__main__':
    unittest.main()
