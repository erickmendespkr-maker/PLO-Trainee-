"""Offline index checks using synthetic temporal clips."""
import json
from pathlib import Path
import unittest

import offline_temporal_batch_crops as export
import offline_temporal_batch_overview as overview
import test_offline_temporal_batch_crops as fixture


class OverviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.TemporalBatchTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.TemporalBatchTests.tearDownClass.__func__(cls)

    def setUp(self):
        fixture.TemporalBatchTests.setUp(self)
        export.export(self.video, self.batch_dir, self.review, self.out)

    def tearDown(self):
        fixture.TemporalBatchTests.tearDown(self)

    def test_html_index_contains_safe_and_blocked(self):
        target = overview.build(self.video, self.batch_dir, self.review, self.out)
        html = target.read_text()
        self.assertEqual(html.count('<video controls'), 4)
        self.assertIn('near: decision_near_uncertain_transition', html)
        self.assertIn('cross: clip_overlaps_or_approaches_geometry_transition', html)
        self.assertIn('Geometria e identidade', html)

    def test_modified_crop_rejected(self):
        with (self.out / 'temporal_first.mp4').open('ab') as f: f.write(b'tamper')
        with self.assertRaises(ValueError):
            overview.build(self.video, self.batch_dir, self.review, self.out)
        self.assertFalse((self.out / 'temporal_crop_overview.html').exists())

    def test_modified_ledger_rejected(self):
        p = self.out / 'temporal_crop_batch_report.json'
        value = json.loads(p.read_text()); value['blocked_count'] = 0; fixture.write(p, value)
        with self.assertRaises(ValueError): overview.build(self.video, self.batch_dir, self.review, self.out)

    def test_modified_metadata_rejected(self):
        p = self.out / 'temporal_first.json'
        value = json.loads(p.read_text()); value['temporal_segment_index'] = 2; fixture.write(p, value)
        with self.assertRaises(ValueError): overview.build(self.video, self.batch_dir, self.review, self.out)

    def test_index_collision_rejected(self):
        overview.build(self.video, self.batch_dir, self.review, self.out)
        with self.assertRaises(ValueError): overview.build(self.video, self.batch_dir, self.review, self.out)


if __name__ == '__main__':
    unittest.main()
