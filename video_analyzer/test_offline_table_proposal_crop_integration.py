"""Synthetic integration: proposal -> explicit simulated review -> crop -> HTML."""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest

import offline_table_region_proposals as proposals
import offline_ev_table_crop as crop
import offline_ev_session_crops as overview
import test_offline_ev_session_crops as prior


class ProposalToCropIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior.CombinedIndexTests.setUpClass()
        cls.source = prior.CombinedIndexTests.base

    @classmethod
    def tearDownClass(cls):
        prior.CombinedIndexTests.tearDownClass()

    def test_four_tables_export_and_cross_index(self):
        video = self.source / 'source.mp4'
        with tempfile.TemporaryDirectory(prefix='plo_proposal_integration_') as folder:
            root = Path(folder)
            review, crops = root / 'review', root / 'crops'
            review.mkdir()
            crops.mkdir()
            p = proposals.propose(video, review)
            self.assertEqual(len(p['regions']), 4)
            self.assertFalse(p['human_confirmation'])
            self.assertFalse(p['automatic_ocr_math_authorization'])
            # Simulates a review only for this synthetic test, not a real human approval.
            layout = proposals.confirm(video, review / 'proposals.json',
                                       review / 'manual.json', confirmed=True)
            self.assertEqual(layout['status'], 'manual_offline_table_regions_unverified')
            batch = crop.export(video, self.source / 'batch', review / 'manual.json', crops)
            self.assertEqual(batch['rendered_count'], 4)
            index = overview.build(self.source / 'batch', crops)
            self.assertEqual(index.read_text(encoding='utf-8').count('<video '), 8)
            for i in range(4):
                self.assertTrue((crops / f'crop_clip-{i}.mp4').is_file())
                self.assertTrue((crops / f'crop_clip-{i}.json').is_file())


if __name__ == '__main__':
    unittest.main()
