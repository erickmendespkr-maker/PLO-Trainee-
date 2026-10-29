"""Synthetic-only tests: candidate -> manually reviewed MP4, with fail-closed gates."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).parent))
from offline_action_review_triage import build as build_triage
from offline_triage_reviewed_clip_pipeline import prepare_selection, run

ROOT = Path(__file__).resolve().parents[1]
TIMELINE_FIXTURE = ROOT / 'demo' / 'synthetic_inputs' / 'timeline.json'
VIDEO_FIXTURE = ROOT / 'demo' / 'synthetic_four_table_placeholder.mp4'


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', 'utf8')
    return path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TriageClipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_triage_test_')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.video = self.base / 'source.mp4'
        shutil.copyfile(VIDEO_FIXTURE, self.video)
        self.timeline = json.loads(TIMELINE_FIXTURE.read_text('utf8'))
        h = next(h for h in self.timeline['hands'] if h['hand_id'] == 'H4')
        h['end_seconds'] = 9
        self.drafts = {
            'schema_version': 1, 'analysis_status': 'offline_reviewed_hand_drafts_only',
            'source_reviewed_report_sha256': self.timeline['source_reviewed_report_sha256'],
            'source_boundaries_sha256': self.timeline['source_boundaries_sha256'],
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
            'hands': [{'hand_id': 'H4', 'table_id': 4, 'variant': 'PLO6',
                       'start_seconds': 0, 'end_seconds': 9,
                       'boundary_origin': 'manual_unverified',
                       'status': 'draft_requires_human_reconstruction',
                       'ready_for_equity_or_ev': False}]
        }
        self.timeline_path = write(self.base / 'timeline.json', self.timeline)
        self.drafts_path = write(self.base / 'drafts.json', self.drafts)
        self.queue = dict(build_triage(self.timeline), source_timeline_sha256=sha(self.timeline_path))
        self.queue_path = write(self.base / 'triage.json', self.queue)
        self.review = {
            'schema_version': 1, 'analysis_status': 'offline_boundary_review_import_only',
            'source_hand_drafts_sha256': sha(self.drafts_path),
            'source_reviewed_report_sha256': self.drafts['source_reviewed_report_sha256'],
            'ready_for_equity_or_ev': False,
            'reviewed_boundaries_are_poker_verified': False,
            'annotations': [{'hand_id': 'H4', 'table_id': 4,
                             'review_status': 'confirmed', 'changed': False,
                             'review_note': '', 'source_start_seconds': 0,
                             'source_end_seconds': 9, 'revised_start_seconds': 0,
                             'revised_end_seconds': 9}]
        }
        self.review_path = write(self.base / 'review.json', self.review)
        self.crop_path = write(self.base / 'crop.json',
                               {'x': 320, 'y': 180, 'width': 320, 'height': 180})
        self.output = self.base / 'result'

    def invoke(self, hand='H4', index=42):
        return run(self.video, self.drafts_path, self.review_path, self.crop_path,
                   self.timeline_path, self.queue_path, hand, index, self.output)

    def assert_rejected(self):
        with self.assertRaises((ValueError, OSError)):
            self.invoke()
        self.assertFalse(self.output.exists())

    def test_end_to_end_mp4(self):
        result = self.invoke()
        self.assertEqual(result['hand_id'], 'H4')
        self.assertEqual(result['proposal_index'], 42)
        self.assertEqual(result['action_ocr'], 'raise')
        self.assertEqual(result['timestamp_seconds'], 2.5)
        self.assertEqual(result['clip_sha256'], sha(self.output / 'clip.mp4'))
        self.assertEqual(result['source_triage_sha256'], sha(self.queue_path))
        self.assertEqual(result['clip_start_seconds'], 0)
        self.assertEqual(result['clip_end_seconds'], 9)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['actor_identified'])
        self.assertFalse(result['source_video_matches_ocr_source_verified'])
        self.assertTrue((self.output / 'manifest.json').is_file())
        self.assertEqual(json.loads((self.output / 'triage_clip_link.json').read_text()), result)

    def test_another_valid_candidate(self):
        result = self.invoke(index=44)
        self.assertEqual(result['action_ocr'], 'call')
        self.assertEqual(result['timestamp_seconds'], 7)

    def test_no_candidate(self):
        with self.assertRaises(ValueError):
            self.invoke(index=999)
        self.assertFalse(self.output.exists())

    def test_wrong_hand(self):
        with self.assertRaises(ValueError):
            self.invoke(hand='H3')
        self.assertFalse(self.output.exists())

    def test_reject_boolean_index(self):
        with self.assertRaises(ValueError):
            self.invoke(index=True)
        self.assertFalse(self.output.exists())

    def test_reject_forged_priority(self):
        self.queue['candidates'][0]['review_priority_points'] += 10
        write(self.queue_path, self.queue)
        self.assert_rejected()

    def test_reject_forged_action(self):
        self.queue['candidates'][0]['action_ocr'] = 'fold'
        write(self.queue_path, self.queue)
        self.assert_rejected()

    def test_reject_forged_authorization(self):
        self.queue['clip_export_authorized'] = True
        write(self.queue_path, self.queue)
        self.assert_rejected()

    def test_reject_modified_timeline(self):
        self.timeline['hands'][3]['warnings'].append('modified')
        write(self.timeline_path, self.timeline)
        self.assert_rejected()

    def test_reject_mismatched_draft_table(self):
        self.drafts['hands'][0]['table_id'] = 3
        write(self.drafts_path, self.drafts)
        self.assert_rejected()

    def test_reject_mismatched_provenance(self):
        self.drafts['source_boundaries_sha256'] = 'b' * 64
        write(self.drafts_path, self.drafts)
        self.assert_rejected()

    def test_reject_missing_manual_approval(self):
        self.review['annotations'][0]['review_status'] = 'pending'
        write(self.review_path, self.review)
        self.assert_rejected()

    def test_reject_unsafe_crop(self):
        write(self.crop_path, {'x': 320, 'y': 180, 'width': 321, 'height': 180})
        self.assert_rejected()

    def test_reject_duplicate_json_keys(self):
        self.queue_path.write_text('{"schema_version":1,"schema_version":1}', 'utf8')
        self.assert_rejected()

    def test_reject_nan(self):
        self.queue_path.write_text('{"schema_version":NaN}', 'utf8')
        self.assert_rejected()

    def test_reject_existing_destination(self):
        self.output.mkdir()
        with self.assertRaises(ValueError):
            self.invoke()

    def test_reject_edited_video(self):
        self.video.write_bytes(b'not a video')
        self.assert_rejected()

    def test_reject_candidate_outside_corrected_interval(self):
        a = self.review['annotations'][0]
        a.update(review_status='corrected', changed=True,
                 review_note='synthetic narrower interval',
                 revised_start_seconds=4, revised_end_seconds=8)
        write(self.review_path, self.review)
        self.assert_rejected()

    def test_reject_tampered_source_identity(self):
        self.timeline['source_reviewed_report_sha256'] = 'b' * 64
        write(self.timeline_path, self.timeline)
        self.queue = dict(build_triage(self.timeline),
                          source_timeline_sha256=sha(self.timeline_path))
        write(self.queue_path, self.queue)
        self.assert_rejected()

    def test_candidate_preflight_does_not_mutate_input(self):
        original = copy.deepcopy(self.queue)
        c = prepare_selection(self.drafts, self.timeline, self.queue, 'H4', 42,
                              sha(self.timeline_path))
        self.assertEqual(c['hand_id'], 'H4')
        self.assertEqual(self.queue, original)


if __name__ == '__main__':
    unittest.main()
