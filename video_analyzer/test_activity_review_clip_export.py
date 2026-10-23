"""Synthetic four-table FFmpeg tests for explicit human-selected neutral clips."""
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from activity_review_clip_export import (STATUS, build_review_clip_plan,
                                         export_review_clips, main)
from activity_review_packet import build_review_packet
from activity_snapshot_chain import build_activity_snapshot_queue, canonical_sha256
from table_regions import grid_regions
from test_activity_snapshot_chain import fixture


class NeutralReviewClipsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'four_tables.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=6:duration=4',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(cls.video)],
                       check=True, capture_output=True)
        video_sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()
        report = fixture()
        report['recording_sha256'] = video_sha
        cls.queue = build_activity_snapshot_queue(report)
        cls.draft = build_review_packet(cls.queue)['template']
        cls.draft['analysis_status'] = 'manual_review_draft_unverified_no_ev'
        for entry in cls.draft['entries']:
            entry['reviewed_fields']['observed_action'].update(
                value='call', confidence=.8, source_timestamp=1.5,
                source='revisão manual sintética', human_confirmed=True)
        cls.selection = {
            'schema_version': 1, 'analysis_status': STATUS,
            'source_queue_sha256': canonical_sha256(cls.queue),
            'source_draft_sha256': canonical_sha256(cls.draft),
            'recording_sha256': video_sha,
            'regions': [asdict(r) for r in grid_regions(160, 120)],
            'selections': [{
                'table_id': e['table_id'], 'hand_id': e['hand_id'],
                'event_index': e['event_index'],
                'decision_timestamp': e['decision_timestamp'],
                'reviewer_approved': True, 'reviewer_priority': 1 - .1 * e['table_id'],
                'explanation': f'Evento sintético da mesa {e["table_id"]}',
            } for e in cls.draft['entries']],
            'seconds_before': .6, 'seconds_after': .8, 'max_clips': 4,
            'regions_human_confirmed': True,
        }

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_four_tables_plan_is_explicit_and_ev_blocked(self):
        plan = build_review_clip_plan(self.video, self.queue, self.draft, self.selection)
        self.assertEqual(len(plan['clips']), 4)
        self.assertEqual({x['table_id'] for x in plan['clips']}, {1, 2, 3, 4})
        self.assertFalse(plan['ready_for_equity_or_ev'])
        self.assertFalse(plan['authorized_for_ev_based_ranking'])
        self.assertFalse(plan['source_visual_content_verified'])
        self.assertTrue(all('sem conclusão de erro' in x['explanation'] for x in plan['clips']))
        self.assertEqual(plan['clips'][0]['table_id'], 1)

    def test_real_ffmpeg_exports_four_cropped_mp4_and_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, obj in [('queue', self.queue), ('draft', self.draft),
                              ('selection', self.selection)]:
                (root / f'{name}.json').write_text(json.dumps(obj), encoding='utf-8')
            out = root / 'clips'
            result = export_review_clips(self.video, root/'queue.json',
                                         root/'draft.json', root/'selection.json', out)
            self.assertEqual(result['clips_generated'], 4)
            self.assertEqual(json.loads((out/'review_clip_manifest.json').read_text()), result)
            for clip in result['clips']:
                file = out / clip['filename']
                self.assertGreater(file.stat().st_size, 500)
                self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), clip['mp4_sha256'])
                self.assertEqual(clip['decoded_output']['width'], 80)
                self.assertEqual(clip['decoded_output']['height'], 60)
            with self.assertRaisesRegex(ValueError, 'new'):
                export_review_clips(self.video, root/'queue.json',
                                    root/'draft.json', root/'selection.json', out)

    def test_wrong_video_hash_rejected(self):
        value = copy.deepcopy(self.selection); value['recording_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'Recording SHA'):
            build_review_clip_plan(self.video, self.queue, self.draft, value)

    def test_changed_queue_hash_rejected(self):
        value = copy.deepcopy(self.selection); value['source_queue_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'Queue or draft'):
            build_review_clip_plan(self.video, self.queue, self.draft, value)

    def test_changed_draft_rejected(self):
        draft = copy.deepcopy(self.draft)
        draft['entries'][0]['reviewed_fields']['observed_action']['value'] = 'raise'
        with self.assertRaisesRegex(ValueError, 'Queue or draft'):
            build_review_clip_plan(self.video, self.queue, draft, self.selection)

    def test_unapproved_rejected(self):
        value = copy.deepcopy(self.selection); value['selections'][0]['reviewer_approved'] = False
        with self.assertRaisesRegex(ValueError, 'approval'):
            build_review_clip_plan(self.video, self.queue, self.draft, value)

    def test_unconfirmed_action_rejected(self):
        draft = copy.deepcopy(self.draft)
        draft['entries'][0]['reviewed_fields']['observed_action']['human_confirmed'] = False
        value = copy.deepcopy(self.selection)
        value['source_draft_sha256'] = canonical_sha256(draft)
        with self.assertRaisesRegex(ValueError, 'confirmed action'):
            build_review_clip_plan(self.video, self.queue, draft, value)

    def test_future_action_timestamp_rejected(self):
        draft = copy.deepcopy(self.draft)
        draft['entries'][0]['reviewed_fields']['observed_action']['source_timestamp'] = 3
        value = copy.deepcopy(self.selection)
        value['source_draft_sha256'] = canonical_sha256(draft)
        with self.assertRaises(ValueError):
            build_review_clip_plan(self.video, self.queue, draft, value)

    def test_wrong_table_hand_and_pts_rejected(self):
        for field, value in [('table_id', 3), ('hand_id', 'other'),
                             ('decision_timestamp', 2.1), ('event_index', 999)]:
            selection = copy.deepcopy(self.selection)
            selection['selections'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_review_clip_plan(self.video, self.queue, self.draft, selection)

    def test_duplicate_selection_rejected(self):
        value = copy.deepcopy(self.selection)
        value['selections'].append(copy.deepcopy(value['selections'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            build_review_clip_plan(self.video, self.queue, self.draft, value)

    def test_malformed_region_rejected(self):
        for mutation in [('x', True), ('width', -1), ('table_id', 5)]:
            value = copy.deepcopy(self.selection)
            value['regions'][0][mutation[0]] = mutation[1]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build_review_clip_plan(self.video, self.queue, self.draft, value)
        value = copy.deepcopy(self.selection)
        value['regions'][1]['x'] = 0
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            build_review_clip_plan(self.video, self.queue, self.draft, value)

    def test_unconfirmed_table_regions_rejected(self):
        value = copy.deepcopy(self.selection); value['regions_human_confirmed'] = False
        with self.assertRaisesRegex(ValueError, 'crop regions'):
            build_review_clip_plan(self.video, self.queue, self.draft, value)

    def test_bad_manual_priority_and_notes_rejected(self):
        for field, value in [('reviewer_priority', True), ('reviewer_priority', 2),
                             ('reviewer_priority', float('nan')), ('explanation', ''),
                             ('explanation', 'x'*501)]:
            selection = copy.deepcopy(self.selection)
            selection['selections'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_review_clip_plan(self.video, self.queue, self.draft, selection)

    def test_preapproved_ev_rejected(self):
        draft = copy.deepcopy(self.draft); draft['ready_for_equity_or_ev'] = True
        value = copy.deepcopy(self.selection)
        value['source_draft_sha256'] = canonical_sha256(draft)
        with self.assertRaises(ValueError):
            build_review_clip_plan(self.video, self.queue, draft, value)

    def test_budget_and_bounds(self):
        value = copy.deepcopy(self.selection); value['max_clips'] = 2
        self.assertEqual(len(build_review_clip_plan(self.video, self.queue,
                                                     self.draft, value)['clips']), 2)
        for field, bad in [('seconds_before', -1), ('seconds_after', 0),
                           ('max_clips', True), ('max_clips', 21)]:
            value = copy.deepcopy(self.selection); value[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_review_clip_plan(self.video, self.queue, self.draft, value)

    def test_output_atomic_on_invalid_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            value = copy.deepcopy(self.selection); value['selections'][0]['reviewer_approved'] = False
            for name, obj in [('queue', self.queue), ('draft', self.draft), ('selection', value)]:
                (root / f'{name}.json').write_text(json.dumps(obj), encoding='utf-8')
            out = root / 'clips'
            with self.assertRaises(ValueError):
                export_review_clips(self.video, root/'queue.json',
                                    root/'draft.json', root/'selection.json', out)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
