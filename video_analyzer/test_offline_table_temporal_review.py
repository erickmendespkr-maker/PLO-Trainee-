"""Synthetic-only offline temporal human-review and FFmpeg preview tests."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import offline_table_temporal_review as mod
import offline_table_temporal_regions as temporal
from test_offline_table_temporal_regions import synthetic


class TemporalReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_review_fixture_')
        cls.root = Path(cls.fixture.name)
        cls.video = cls.root / 'moving.mp4'
        synthetic(cls.video)
        cls.evidence_dir = cls.root / 'evidence'
        cls.evidence_dir.mkdir()
        cls.evidence = cls.evidence_dir / 'temporal_regions.json'
        temporal.track(cls.video, cls.evidence_dir, interval=1)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_review_test_')
        self.addCleanup(self.tmp.cleanup)
        self.root_out = Path(self.tmp.name)
        self.draft_path = self.root_out / 'draft.json'
        self.approved_dir = self.root_out / 'approved'
        self.approved_dir.mkdir()
        self.preview_dir = self.root_out / 'previews'
        self.preview_dir.mkdir()

    def draft(self):
        d = mod.template(self.video, self.evidence, self.draft_path)
        d['reviewer_note'] = 'Reviewed each region and the two time boundaries on the recorded source.'
        obs = json.loads(self.evidence.read_text())['observations']
        first, last = obs[0]['regions'], obs[-1]['regions']
        d['segments'] = [{'start_seconds': 0.0, 'end_seconds': 3.0, 'regions': first},
                         {'start_seconds': 3.0, 'end_seconds': 6.0, 'regions': last}]
        self.draft_path.write_text(mod.canonical(d))
        return d

    def approve(self):
        return mod.approve(self.video, self.evidence, self.draft_path,
                           self.approved_dir, confirmed=True)

    def test_template_unapproved(self):
        d = mod.template(self.video, self.evidence, self.draft_path)
        self.assertEqual(d['status'], mod.DRAFT)
        self.assertEqual(d['reviewer_note'], mod.PLACEHOLDER)
        self.assertEqual(len(d['segments']), 1)
        self.assertFalse((self.approved_dir / 'temporal_review.json').exists())

    def test_requires_explicit_confirmation(self):
        self.draft()
        with self.assertRaisesRegex(ValueError, 'human review'):
            mod.approve(self.video, self.evidence, self.draft_path, self.approved_dir)
        self.assertFalse((self.approved_dir / 'temporal_review.json').exists())

    def test_reject_placeholder(self):
        mod.template(self.video, self.evidence, self.draft_path)
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            self.approve()

    def test_two_segments_audited(self):
        self.draft()
        result = self.approve()
        self.assertEqual(result['status'], mod.APPROVED)
        self.assertEqual(len(result['segments']), 2)
        self.assertFalse(result['table_identity_verified'])
        self.assertFalse(result['automatic_ocr_math_authorization'])
        self.assertEqual(json.loads((self.approved_dir / 'temporal_review.json').read_text()), result)

    def test_eight_cropped_previews_and_html(self):
        self.draft()
        self.approve()
        ledger = mod.previews(self.video, self.approved_dir / 'temporal_review.json',
                              self.preview_dir)
        self.assertEqual(ledger['rendered_count'], 8)
        self.assertEqual({x['table_id_claim'] for x in ledger['clips']},
                         {'T1', 'T2', 'T3', 'T4'})
        for c in ledger['clips']:
            p = self.preview_dir / c['filename']
            self.assertTrue(p.is_file())
            self.assertEqual(mod.base.sha256(p), c['sha256'])
            self.assertEqual(mod.base.probe(p)[:2],
                             (c['crop_region_claim']['width'], c['crop_region_claim']['height']))
        self.assertEqual((self.preview_dir / 'temporal_previews.html').read_text().count('<video'), 8)
        self.assertFalse(ledger['automatic_ocr_math_authorization'])

    def test_noncontiguous_segments_rejected(self):
        d = self.draft()
        d['segments'][1]['start_seconds'] = 3.2
        self.assert_bad(d)

    def test_uncovered_end_rejected(self):
        d = self.draft()
        d['segments'][-1]['end_seconds'] = 5.5
        self.assert_bad(d)

    def test_bool_boundary_rejected(self):
        d = self.draft()
        d['segments'][0]['start_seconds'] = False
        self.assert_bad(d)

    def test_overlap_rejected(self):
        d = self.draft()
        d['segments'][0]['regions'][1]['x'] = 0
        self.assert_bad(d)

    def test_odd_crop_origin_rejected(self):
        d = self.draft()
        d['segments'][0]['regions'][0]['x'] = 1
        self.assert_bad(d)

    def test_oversized_crop_rejected(self):
        d = self.draft()
        d['segments'][0]['regions'][0]['width'] = 99999
        self.assert_bad(d)

    def test_changed_table_identity_rejected(self):
        d = self.draft()
        d['segments'][1]['regions'][0]['table_id'] = 'T4'
        self.assert_bad(d)

    def test_extra_segment_field_rejected(self):
        d = self.draft()
        d['segments'][0]['verified'] = True
        self.assert_bad(d)

    def test_too_many_segments_rejected(self):
        d = self.draft()
        d['segments'] = [copy.deepcopy(d['segments'][0])] * 13
        self.assert_bad(d)

    def test_source_hash_mismatch_rejected(self):
        d = self.draft()
        d['source_video_sha256'] = '0' * 64
        self.assert_bad(d)

    def test_evidence_hash_mismatch_rejected(self):
        d = self.draft()
        d['temporal_evidence_sha256'] = '0' * 64
        self.assert_bad(d)

    def test_duplicate_json_key_rejected(self):
        self.draft()
        self.draft_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            self.approve()

    def test_collision_preserves_previous_approval(self):
        self.draft()
        self.approve()
        original = (self.approved_dir / 'temporal_review.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.approve()
        self.assertEqual((self.approved_dir / 'temporal_review.json').read_bytes(), original)

    def test_symlink_output_rejected(self):
        self.draft()
        alias = self.root_out / 'alias'
        alias.symlink_to(self.approved_dir, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unsafe output'):
            mod.approve(self.video, self.evidence, self.draft_path, alias, confirmed=True)

    def test_changed_temporal_observation_rejected(self):
        self.draft()
        tampered = self.root_out / 'tampered.json'
        data = json.loads(self.evidence.read_text())
        data['observations'][0]['regions'][0]['x'] = 24
        tampered.write_text(mod.canonical(data))
        d = json.loads(self.draft_path.read_text())
        d['temporal_evidence_sha256'] = mod.base.sha256(tampered)
        self.draft_path.write_text(mod.canonical(d))
        with self.assertRaisesRegex(ValueError, 'altered or stale'):
            mod.approve(self.video, tampered, self.draft_path, self.approved_dir, confirmed=True)

    def test_preview_collision_preserves_files(self):
        self.draft()
        self.approve()
        dest = self.preview_dir / 'temporal_previews.json'
        dest.write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'collision'):
            mod.previews(self.video, self.approved_dir / 'temporal_review.json', self.preview_dir)
        self.assertEqual(dest.read_text(), 'preserve')

    def test_preview_render_failure_rolls_back(self):
        self.draft()
        self.approve()
        with mock.patch.object(mod.subprocess, 'run', side_effect=RuntimeError('synthetic ffmpeg failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic ffmpeg failure'):
                mod.previews(self.video, self.approved_dir / 'temporal_review.json', self.preview_dir)
        self.assertEqual(list(self.preview_dir.iterdir()), [])

    def assert_bad(self, d):
        self.draft_path.write_text(mod.canonical(d))
        with self.assertRaises(ValueError):
            self.approve()
        self.assertEqual(list(self.approved_dir.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
