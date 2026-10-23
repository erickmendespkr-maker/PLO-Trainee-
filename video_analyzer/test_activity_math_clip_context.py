"""Synthetic FFmpeg-backed provenance tests for optional PLO5/PLO6 what-if sidecars."""
import copy
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from activity_hypothetical_math import MODEL, build_hypothetical_report, digest
from activity_math_clip_context import build_math_clip_context, main
from activity_review_clip_export import STATUS, export_review_clips
from activity_review_handoff import build_handoff
from activity_review_packet import build_review_packet
from activity_snapshot_chain import build_activity_snapshot_queue, canonical_sha256
from activity_scenario_worksheet import build_scenario_worksheet
from table_regions import grid_regions
from test_activity_snapshot_chain import fixture


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires FFmpeg')
class MathClipContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'four_tables.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=6:duration=4',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(cls.video)],
                       check=True, capture_output=True)
        import hashlib
        video_sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()
        activity = fixture()
        activity['recording_sha256'] = video_sha
        cls.queue = build_activity_snapshot_queue(activity)
        cls.draft = build_review_packet(cls.queue)['template']
        cls.draft['analysis_status'] = 'manual_review_draft_unverified_no_ev'
        for entry in cls.draft['entries']:
            fields = entry['reviewed_fields']
            for field, value in {'observed_action': 'call'}.items():
                fields[field].update(value=value, confidence=.8, source_timestamp=1,
                                     source='synthetic review', human_confirmed=True)
        first = cls.draft['entries'][0]
        for field, value in {
                'hero_cards': ['As','Ks','2d','3c','4h'],
                'board': ['Qs','Js','Ts','9d','8c'],
                'pot_before_action': 100, 'call_amount': 25}.items():
            first['reviewed_fields'][field].update(
                value=value, confidence=.9, source_timestamp=1,
                source='synthetic review', human_confirmed=True)
        cls.worksheet = build_scenario_worksheet(build_handoff(cls.queue, cls.draft))
        scenario = cls.worksheet['scenarios'][0]
        cls.request = {'schema_version': 1, 'worksheet_sha256': digest(cls.worksheet),
                       'scenarios': [{
                           'table_id': scenario['table_id'], 'event_index': scenario['event_index'],
                           'hand_id': scenario['hand_id'], 'model_acknowledgement': MODEL,
                           'trials': 12, 'seed': 17,
                           'opponent_range': [{'cards': ['2c','3d','4c','5d','6h'], 'weight': 1}],
                       }]}
        cls.report = build_hypothetical_report(cls.worksheet, cls.request)
        selection = {
            'schema_version': 1, 'analysis_status': STATUS,
            'source_queue_sha256': canonical_sha256(cls.queue),
            'source_draft_sha256': canonical_sha256(cls.draft),
            'recording_sha256': video_sha,
            'regions': [asdict(r) for r in grid_regions(160, 120)],
            'selections': [{
                'table_id': e['table_id'], 'hand_id': e['hand_id'],
                'event_index': e['event_index'], 'decision_timestamp': e['decision_timestamp'],
                'reviewer_approved': True, 'reviewer_priority': .7,
                'explanation': 'Revisão sintética, sem diagnóstico',
            } for e in cls.draft['entries']],
            'seconds_before': .6, 'seconds_after': .8, 'max_clips': 4,
            'regions_human_confirmed': True,
        }
        for name, obj in [('queue', cls.queue), ('draft', cls.draft), ('selection', selection)]:
            (cls.root / f'{name}.json').write_text(json.dumps(obj), encoding='utf-8')
        cls.clips_dir = cls.root / 'clips'
        cls.manifest = export_review_clips(cls.video, cls.root/'queue.json',
                                            cls.root/'draft.json', cls.root/'selection.json',
                                            cls.clips_dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, manifest=None, worksheet=None, request=None, report=None, clips_dir=None):
        return build_math_clip_context(
            self.manifest if manifest is None else manifest,
            self.clips_dir if clips_dir is None else clips_dir,
            self.worksheet if worksheet is None else worksheet,
            self.request if request is None else request,
            self.report if report is None else report)

    def test_four_clips_one_hypothetical_call_no_ev_ranking(self):
        result = self.build()
        self.assertEqual(len(result['clips']), 4)
        self.assertEqual(result['clips_with_hypothetical_math'], 1)
        self.assertEqual(result['clips'][0]['math_status'],
                         'conditional_heads_up_all_in_what_if_only')
        self.assertEqual(result['clips'][0]['hypothetical_math']['equity'], 1)
        self.assertEqual(result['clips'][0]['hypothetical_math']['call_ev_vs_fold'], 100)
        self.assertEqual(sum(x['hypothetical_math'] is None for x in result['clips']), 3)
        self.assertFalse(result['authorized_for_ev_based_ranking'])
        self.assertTrue(all(x['strategic_error_established'] is False for x in result['clips']))
        self.assertEqual(result, self.build())

    def test_report_tampering_fails_even_with_matching_source_hashes(self):
        report = copy.deepcopy(self.report)
        report['results'][0]['call_ev_vs_fold'] = 999999
        with self.assertRaisesRegex(ValueError, 'deterministic'):
            self.build(report=report)

    def test_wrong_video_and_queue_provenance_fail(self):
        for field in ('recording_sha256', 'source_queue_sha256', 'source_draft_sha256'):
            worksheet = copy.deepcopy(self.worksheet)
            worksheet[field] = '0'*64
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build(worksheet=worksheet)

    def test_unknown_or_duplicate_clip_decision_fails(self):
        for change in ('unknown', 'duplicate'):
            manifest = copy.deepcopy(self.manifest)
            if change == 'unknown':
                manifest['clips'][0]['hand_id'] = 'unknown'
            else:
                manifest['clips'][1]['hand_id'] = manifest['clips'][0]['hand_id']
                manifest['clips'][1]['table_id'] = manifest['clips'][0]['table_id']
                manifest['clips'][1]['event_index'] = manifest['clips'][0]['event_index']
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.build(manifest=manifest)

    def test_action_or_timestamp_mismatch_fails(self):
        for field, value in [('observed_action', 'raise'), ('decision_timestamp', 3)]:
            worksheet = copy.deepcopy(self.worksheet)
            if field == 'observed_action':
                worksheet['scenarios'][0]['reviewed_visible_inputs'][field] = value
            else:
                worksheet['scenarios'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build(worksheet=worksheet)

    def test_extra_math_result_for_unselected_clip_fails(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['clips'] = manifest['clips'][1:]
        manifest['clips_generated'] = 3
        with self.assertRaisesRegex(ValueError, 'corresponding human-selected clip'):
            self.build(manifest=manifest)

    def test_invalid_or_authorizing_status_fails_closed(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['authorized_for_ev_based_ranking'] = True
        with self.assertRaises(ValueError): self.build(manifest=manifest)
        report = copy.deepcopy(self.report)
        report['authorized_for_clips'] = True
        with self.assertRaises(ValueError): self.build(report=report)

    def test_missing_or_tampered_mp4_fails(self):
        with tempfile.TemporaryDirectory() as td:
            clips = Path(td)
            for clip in self.manifest['clips']:
                shutil.copy2(self.clips_dir / clip['filename'], clips / clip['filename'])
            first = clips / self.manifest['clips'][0]['filename']
            first.write_bytes(first.read_bytes() + b'tamper')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                self.build(clips_dir=clips)
            first.unlink()
            with self.assertRaises(ValueError): self.build(clips_dir=clips)

    def test_plo6_hypothesis_remains_unverified(self):
        worksheet = copy.deepcopy(self.worksheet)
        worksheet['scenarios'][0]['reviewed_visible_inputs']['hero_cards'] = [
            'As','Ks','2d','3c','4h','5s']
        request = copy.deepcopy(self.request)
        request['worksheet_sha256'] = digest(worksheet)
        request['scenarios'][0]['opponent_range'] = [{
            'cards': ['2c','3d','4c','5d','6h','7h'], 'weight': 1}]
        report = build_hypothetical_report(worksheet, request)
        output = self.build(worksheet=worksheet, request=request, report=report)
        self.assertEqual(output['clips'][0]['hypothetical_math']['variant'], 'PLO6')
        self.assertFalse(output['clips'][0]['eligible_for_ev_ranking'])

    def test_cli_writes_only_new_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = []
            for name, obj in [('manifest', self.manifest), ('worksheet', self.worksheet),
                              ('request', self.request), ('report', self.report)]:
                p = root / f'{name}.json'
                p.write_text(json.dumps(obj), encoding='utf-8')
                paths.append(p)
            output = root / 'context.json'
            args = [str(paths[0]), str(self.clips_dir), str(paths[1]), str(paths[2]),
                    str(paths[3]), str(output)]
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(output.read_text())['clips_with_hypothetical_math'], 1)
            with self.assertRaises(ValueError): main(args)
            args[-1] = str(paths[0])
            with self.assertRaises(ValueError): main(args)


if __name__ == '__main__':
    unittest.main()
