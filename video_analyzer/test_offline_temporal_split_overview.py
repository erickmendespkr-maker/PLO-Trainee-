"""Offline HTML index: synthetic split provenance and tampering tests."""
import json
from pathlib import Path
import shutil

import offline_temporal_split_clips as split
import offline_temporal_split_overview as overview
from test_offline_temporal_batch_crops import TemporalBatchTests


class SplitOverviewTests(TemporalBatchTests):
    def make_split(self):
        split.export(self.video, self.batch_dir, self.review, self.out)

    def test_html_renders_four_mp4_and_blocked(self):
        self.make_split()
        result = overview.render(self.video, self.batch_dir, self.review, self.out)
        self.assertEqual(result['parts'], 4)
        self.assertEqual(result['blocked'], 1)
        text = (self.out / overview.PAGE).read_text()
        self.assertEqual(text.count('<video '), 4)
        self.assertIn('decision_near_uncertain_transition', text)
        self.assertIn('2.75–3.25s', text)
        self.assertIn('não reconstruído', text)
        self.assertNotIn('<script', text)

    def test_modified_mp4_rejected(self):
        self.make_split()
        with (self.out / 'split_cross_s01.mp4').open('ab') as f:
            f.write(b'modified')
        with self.assertRaises(ValueError):
            overview.render(self.video, self.batch_dir, self.review, self.out)

    def test_modified_metadata_rejected(self):
        self.make_split()
        p = self.out / 'split_first_s01.json'
        value = json.loads(p.read_text()); value['table_identity_verified'] = True
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            overview.render(self.video, self.batch_dir, self.review, self.out)

    def test_ledger_count_tamper_rejected(self):
        self.make_split()
        p = self.out / 'temporal_split_report.json'
        value = json.loads(p.read_text()); value['rendered_count'] = 5
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            overview.render(self.video, self.batch_dir, self.review, self.out)

    def test_duplicate_html_rejected(self):
        self.make_split()
        overview.render(self.video, self.batch_dir, self.review, self.out)
        with self.assertRaises(ValueError):
            overview.render(self.video, self.batch_dir, self.review, self.out)

    def test_source_clip_changed_rejected(self):
        self.make_split()
        folder = self.mutate_batch(lambda b: None)
        with (folder / 'cross.mp4').open('ab') as f:
            f.write(b'changed')
        with self.assertRaises(ValueError):
            overview.render(self.video, folder, self.review, self.out)

    def test_missing_mp4_rejected(self):
        self.make_split()
        (self.out / 'split_first_s01.mp4').unlink()
        with self.assertRaises(ValueError):
            overview.render(self.video, self.batch_dir, self.review, self.out)
