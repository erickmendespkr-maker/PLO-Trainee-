"""Synthetic FFmpeg integration tests: audited source replay -> reviewed OCR viewer."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_video_ingest_probe import build
from offline_sampled_visual_change import analyze
from offline_adaptive_change_refinement import refine
from offline_refined_roi_ocr import scan
from offline_verified_evidence_bundle import bundle, sha


class VerifiedBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.base_tmp.name)
        video = cls.base / 'source.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=gray:s=320x180:r=1', '-t', '6',
                        '-vf', "drawbox=x=0:y=0:w=320:h=180:color=white:t=fill:enable='gte(t,2)'",
                        '-c:v', 'mpeg4', '-y', str(video)],
                       capture_output=True, check=True, timeout=60)
        regions = cls.base / 'regions.json'
        regions.write_text(json.dumps({'tables': [
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 180}]}))
        ingest = cls.base / 'ingest'; build(video, regions, ingest)
        changes_dir = cls.base / 'changes'; analyze(ingest, changes_dir)
        changes = changes_dir / 'visual_changes.json'
        refined = cls.base / 'refined'; refine(video, regions, ingest, changes, refined)
        manifest = json.loads((ingest / 'manifest.json').read_text())
        dense = json.loads((refined / 'dense_refinement.json').read_text())
        tasks = cls.base / 'tasks.json'
        tasks.write_text(json.dumps({
            'schema_version': 1,
            'source_ingest_manifest_sha256': sha(ingest / 'manifest.json'),
            'source_dense_refinement_sha256': sha(refined / 'dense_refinement.json'),
            'tasks': [
                {'table_id': 1, 'frame_file': manifest['samples'][0]['file'],
                 'field': 'pot', 'roi': {'x': 1, 'y': 1, 'width': 100, 'height': 40}},
                {'table_id': 1, 'frame_file': dense['refinements'][0]['new_frames'][0]['file'],
                 'field': 'board', 'roi': {'x': 4, 'y': 8, 'width': 120, 'height': 60}}]}))
        scan(video, regions, ingest, changes, refined, tasks, cls.base / 'ocr')

    @classmethod
    def tearDownClass(cls):
        cls.base_tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(self.base, self.root / 'fixture', dirs_exist_ok=True)
        self.f = self.root / 'fixture'
        self.out = self.root / 'viewer'
        self.ocr_path = self.f / 'ocr/roi_ocr_proposals.json'
        self.review_path = self.f / 'review.json'
        self.draft_path = self.f / 'drafts.json'
        self.timeline_path = self.f / 'timeline.json'
        ocr = json.loads(self.ocr_path.read_text())
        observations = []
        for i, proposal in enumerate(ocr['proposals']):
            observations.append({
                'proposal_index': i, 'table_id': proposal['table_id'],
                'field': proposal['field'], 'frame_file': proposal['frame_file'],
                'source_frame_sha256': proposal['source_frame_sha256'],
                'decoded_source_pts_seconds': proposal['decoded_source_pts_seconds'],
                'roi_png': proposal['roi_png'], 'roi_png_sha256': proposal['roi_png_sha256'],
                'raw_ocr_text': proposal['raw_ocr_text'],
                'decision': 'confirmed' if i == 0 else 'pending',
                'normalized_value': '125' if i == 0 else None})
        review = {'analysis_status': 'offline_human_reviewed_ocr_observations_only',
                  'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
                  'source_roi_ocr_report_sha256': sha(self.ocr_path),
                  'observations': observations}
        self.review_path.write_text(json.dumps(review))
        first = observations[0]
        draft = {'analysis_status': 'offline_reviewed_hand_drafts_only',
                 'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
                 'source_boundaries_sha256': 'b' * 64,
                 'source_reviewed_report_sha256': sha(self.review_path),
                 'source_roi_ocr_report_sha256': sha(self.ocr_path),
                 'hands': [{'hand_id': 'H1', 'table_id': 1, 'variant': 'PLO5',
                            'start_seconds': 0, 'end_seconds': 6,
                            'observation_indices': [0, 1], 'unresolved_indices': [1],
                            'reviewed_fields': {'pot': [{'proposal_index': 0,
                                'timestamp_seconds': first['decoded_source_pts_seconds'],
                                'value': '125', 'review': 'confirmed'}]}}]}
        self.draft_path.write_text(json.dumps(draft))
        timeline = {'schema_version': 1, 'analysis_status': 'offline_action_bet_evidence_only',
                    'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
                    'source_boundaries_sha256': 'b' * 64,
                    'source_reviewed_report_sha256': sha(self.review_path),
                    'source_hand_drafts_sha256': sha(self.draft_path),
                    'hands': [{'hand_id': 'H1', 'table_id': 1, 'variant': 'PLO5',
                               'start_seconds': 0, 'end_seconds': 6,
                               'ready_for_equity_or_ev': False,
                               'actor_and_betting_sequence_verified': False,
                               'events': [{'proposal_index': 0,
                                   'timestamp_seconds': first['decoded_source_pts_seconds'],
                                   'field': 'pot', 'value': '125', 'review': 'confirmed'}]}]}
        self.timeline_path.write_text(json.dumps(timeline))

    def run_bundle(self):
        return bundle(self.f / 'source.mp4', self.f / 'regions.json',
                      self.f / 'ingest', self.f / 'changes/visual_changes.json',
                      self.f / 'refined', self.f / 'tasks.json', self.f / 'ocr',
                      self.review_path, self.draft_path, self.timeline_path, self.out)

    def fails_cleanly(self):
        with self.assertRaises(ValueError):
            self.run_bundle()
        self.assertFalse(self.out.exists())

    def test_end_to_end_replay_and_viewer(self):
        result = self.run_bundle()
        self.assertEqual(result['roi_pngs_replayed_exactly'], 2)
        self.assertEqual(result['source_frames_replayed_exactly'], 2)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['ocr_semantics_verified'])
        self.assertEqual(result['viewer_report_sha256'], sha(self.out / 'action_roi_report.json'))
        self.assertEqual(result['viewer_html_sha256'], sha(self.out / 'index.html'))
        self.assertIn('Reprodução FFmpeg', (self.out / 'index.html').read_text())
        self.assertEqual(json.loads((self.out / 'source_replay_attestation.json').read_text()), result)
        self.assertEqual(sha(self.out / 'assets/roi_000.png'), sha(self.f / 'ocr/roi_000.png'))

    def test_source_video_tamper(self):
        with (self.f / 'source.mp4').open('ab') as stream: stream.write(b'changed')
        self.fails_cleanly()

    def test_rehashed_png_tamper_detected_by_replay(self):
        image = self.f / 'ocr/roi_000.png'
        image.write_bytes(image.read_bytes() + b'tamper')
        ocr = json.loads(self.ocr_path.read_text())
        ocr['proposals'][0]['roi_png_sha256'] = sha(image)
        self.ocr_path.write_text(json.dumps(ocr))
        self.fails_cleanly()

    def test_wrong_viewer_ocr_provenance(self):
        review = json.loads(self.review_path.read_text())
        review['source_roi_ocr_report_sha256'] = 'a' * 64
        self.review_path.write_text(json.dumps(review))
        self.fails_cleanly()

    def test_false_equity_claim(self):
        timeline = json.loads(self.timeline_path.read_text())
        timeline['ready_for_equity_or_ev'] = True
        self.timeline_path.write_text(json.dumps(timeline))
        self.fails_cleanly()

    def test_reject_existing_output(self):
        self.out.mkdir()
        with self.assertRaises(ValueError): self.run_bundle()

    def test_reject_output_inside_evidence(self):
        self.out = self.f / 'ocr' / 'viewer'
        self.fails_cleanly()

    def test_reject_symlink_source(self):
        link = self.root / 'linked.json'; link.symlink_to(self.review_path)
        self.review_path = link
        self.fails_cleanly()

    def test_failed_second_replay_does_not_publish(self):
        from offline_ocr_source_replay_audit import audit as actual
        with patch('offline_verified_evidence_bundle.audit', side_effect=[actual(
                self.f / 'source.mp4', self.f / 'regions.json', self.f / 'ingest',
                self.f / 'changes/visual_changes.json', self.f / 'refined',
                self.f / 'tasks.json', self.f / 'ocr'), ValueError('second replay failed')]):
            self.fails_cleanly()

    def test_replay_does_not_mutate_inputs(self):
        originals = [self.f / 'source.mp4', self.ocr_path, self.review_path,
                     self.draft_path, self.timeline_path]
        before = [sha(p) for p in originals]
        self.run_bundle()
        self.assertEqual(before, [sha(p) for p in originals])


if __name__ == '__main__':
    unittest.main()
