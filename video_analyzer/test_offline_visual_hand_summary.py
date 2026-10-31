"""Synthetic, fail-closed tests for visual/street aggregation; no video truth."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_visual_hand_summary as summary
import offline_visual_evidence_review_import as visual_import
import test_offline_visual_evidence_review_import as visual_fixture
import offline_hand_street_review as review


class VisualSummaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = visual_fixture.VisualImportTests('test_default_uncertain')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.reviewed_path = f.fx.review_file
        self.visual_path = f.fx.root / 'imported_visual.json'
        self.output = f.fx.root / 'summary.json'
        self.reviewed = review.read(self.reviewed_path)
        self.visual = f.run_import()
        self.write()

    def write(self):
        self.visual_path.write_text(json.dumps(self.visual))

    def build(self):
        return summary.build(self.reviewed, self.visual,
                             review.digest(self.reviewed_path), review.digest(self.visual_path))

    def test_uncertain_default_blocks_math(self):
        out = self.build()
        self.assertEqual(out['hand_count'], 1)
        self.assertEqual(out['declared_field_count'], 1)
        self.assertEqual(out['visual_status_counts']['uncertain'], 1)
        self.assertEqual(out['eligible_for_equity'], 0)
        self.assertFalse(out['equity_or_ev_calculated'])
        self.assertTrue(out['video_content_not_semantically_verified'])

    def test_seen_remains_unverified(self):
        self.visual['claims'][0]['visual_review_status_unverified'] = 'seen_by_reviewer'
        self.visual['seen_by_reviewer_unverified'] = 1
        self.visual['uncertain'] = 0
        out = self.build()
        self.assertEqual(out['visual_status_counts']['seen_by_reviewer'], 1)
        self.assertFalse(out['hands'][0]['math_ready'])
        self.assertIn('video_content_not_independently_verified', out['hands'][0]['blockers'])
        self.assertEqual(out['hands'][0]['declared_fields'][0]['evidence_pts_seconds'], [10])

    def test_not_visible_count(self):
        self.visual['claims'][0]['visual_review_status_unverified'] = 'not_visible'
        self.visual['not_visible_by_reviewer_unverified'] = 1
        self.visual['uncertain'] = 0
        self.assertEqual(self.build()['visual_status_counts']['not_visible'], 1)

    def test_source_review_hash_mismatch(self):
        self.visual['source_review_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'unbound visual ledger'): self.build()

    def test_video_hash_mismatch(self):
        self.visual['source_video_sha256_claim'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'unbound visual ledger'): self.build()

    def test_math_forgery_visual(self):
        self.visual['eligible_for_equity'] = True
        with self.assertRaisesRegex(ValueError, 'unbound visual ledger'): self.build()

    def test_math_forgery_reviewed(self):
        self.reviewed['eligible_for_equity'] = 1
        with self.assertRaisesRegex(ValueError, 'invalid reviewed ledger'): self.build()

    def test_claim_value_mismatch(self):
        self.visual['claims'][0]['value_unverified'] = 'Kd'
        with self.assertRaisesRegex(ValueError, 'differs'): self.build()

    def test_claim_hand_mismatch(self):
        self.visual['claims'][0]['hand_id'] = 'H99'
        with self.assertRaisesRegex(ValueError, 'differs'): self.build()

    def test_claim_table_mismatch(self):
        self.visual['claims'][0]['table_id'] = 'T99'
        with self.assertRaisesRegex(ValueError, 'differs'): self.build()

    def test_duplicate_visual_claim(self):
        self.visual['claims'].append(copy.deepcopy(self.visual['claims'][0]))
        self.visual['claim_count'] = 2
        with self.assertRaisesRegex(ValueError, 'duplicate visual claim'): self.build()

    def test_missing_visual_claim(self):
        self.visual['claims'] = []
        self.visual['claim_count'] = 0
        self.visual['uncertain'] = 0
        with self.assertRaisesRegex(ValueError, 'differs'): self.build()

    def test_invalid_frame_hash(self):
        self.visual['claims'][0]['evidence'][0]['frame_sha256'] = 'notsha'
        with self.assertRaisesRegex(ValueError, 'frame evidence'): self.build()

    def test_nan_pts(self):
        self.visual['claims'][0]['evidence'][0]['pts_seconds'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'frame evidence'): self.build()

    def test_negative_pts(self):
        self.visual['claims'][0]['evidence'][0]['pts_seconds'] = -1
        with self.assertRaisesRegex(ValueError, 'frame evidence'): self.build()

    def test_duplicate_frame_evidence(self):
        e = self.visual['claims'][0]['evidence'][0]
        self.visual['claims'][0]['evidence'].append(copy.deepcopy(e))
        with self.assertRaisesRegex(ValueError, 'duplicate frame evidence'): self.build()

    def test_seen_without_evidence(self):
        self.visual['claims'][0]['evidence'] = []
        self.visual['claims'][0]['visual_review_status_unverified'] = 'seen_by_reviewer'
        self.visual['seen_by_reviewer_unverified'] = 1
        self.visual['uncertain'] = 0
        with self.assertRaisesRegex(ValueError, 'without frame'): self.build()

    def test_status_counter_forgery(self):
        self.visual['uncertain'] = 0
        with self.assertRaisesRegex(ValueError, 'counters mismatch'): self.build()

    def test_duplicate_review_field(self):
        hand = self.reviewed['hands'][0]
        hand['fields'].append(copy.deepcopy(hand['fields'][0]))
        self.reviewed['field_count'] += 1
        with self.assertRaisesRegex(ValueError, 'duplicate reviewed field'): self.build()

    def test_unconfirmed_value_forgery(self):
        self.reviewed['hands'][0]['fields'][1]['reviewer_value_unverified'] = 'Kd'
        with self.assertRaisesRegex(ValueError, 'unconfirmed field'): self.build()

    def test_cli_no_overwrite(self):
        args = [str(self.reviewed_path), str(self.visual_path), str(self.output)]
        self.assertEqual(summary.main(args), 0)
        self.assertEqual(json.loads(self.output.read_text())['eligible_for_equity'], 0)
        with self.assertRaisesRegex(ValueError, 'new and distinct'): summary.main(args)

    def test_duplicate_json_key_rejected(self):
        self.visual_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            summary.main([str(self.reviewed_path), str(self.visual_path), str(self.output)])

    def test_nonfinite_json_rejected(self):
        self.visual_path.write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'):
            summary.main([str(self.reviewed_path), str(self.visual_path), str(self.output)])


if __name__ == '__main__':
    unittest.main()
