"""Synthetic end-to-end: proposal -> edited geometry -> audit -> crop -> HTML."""
from pathlib import Path
import json
import tempfile
import unittest
import offline_table_region_proposals as proposal
import offline_table_region_corrections as correction
import offline_ev_table_crop as crop
import offline_ev_session_crops as overview
import test_offline_ev_session_crops as prior


class CorrectedCropIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior.CombinedIndexTests.setUpClass()
        cls.source = prior.CombinedIndexTests.base

    @classmethod
    def tearDownClass(cls):
        prior.CombinedIndexTests.tearDownClass()

    def test_corrected_four_table_export(self):
        video = self.source / 'source.mp4'
        with tempfile.TemporaryDirectory(prefix='plo_corrected_integration_') as tmp:
            root = Path(tmp)
            proposals, corrected, crops = (root / n for n in ('proposals','corrected','crops'))
            for directory in (proposals, corrected, crops):
                directory.mkdir()
            proposal.propose(video, proposals)
            draft = root / 'draft.json'
            correction.draft_template(video, proposals / 'proposals.json', draft)
            data = json.loads(draft.read_text())
            data['reviewer_note'] = 'Synthetic review only: trim two pixels from first table.'
            data['regions'][0]['width'] -= 2
            draft.write_text(json.dumps(data))
            audit = correction.apply(video, proposals / 'proposals.json', draft,
                                     corrected, confirmed=True)
            self.assertEqual(len(audit['changes']), 1)
            result = crop.export(video, self.source / 'batch', corrected / 'manual_layout.json', crops)
            self.assertEqual(result['rendered_count'], 4)
            html = overview.build(self.source / 'batch', crops)
            self.assertEqual(html.read_text(encoding='utf-8').count('<video '), 8)
            self.assertTrue((corrected / 'correction_audit.json').is_file())
            self.assertFalse(audit['automatic_ocr_math_authorization'])


if __name__ == '__main__':
    unittest.main()
