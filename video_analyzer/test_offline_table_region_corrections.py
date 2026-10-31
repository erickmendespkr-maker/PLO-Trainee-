"""Synthetic FFmpeg-only tests for explicit audited geometry corrections."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
import offline_table_region_corrections as mod
import offline_table_region_proposals as proposals
from test_offline_table_region_proposals import synthetic


class CorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_correction_video_')
        cls.video = Path(cls.fixture.name) / 'four.mp4'
        synthetic(cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plo_correction_test_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proposal_dir = self.root / 'proposals'
        self.proposal_dir.mkdir()
        proposals.propose(self.video, self.proposal_dir)
        self.p = self.proposal_dir / 'proposals.json'
        self.draft = self.root / 'draft.json'
        mod.draft_template(self.video, self.p, self.draft)
        self.output = self.root / 'results'
        self.output.mkdir()

    def update(self, change=None):
        d = json.loads(self.draft.read_text())
        d['reviewer_note'] = 'Manually adjusted rectangle to avoid the frame edge.'
        d['regions'][0]['width'] -= 2
        if change:
            change(d)
        self.draft.write_text(json.dumps(d))

    def test_audit_and_compatible_layout(self):
        self.update()
        audit = mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)
        self.assertEqual(len(audit['changes']), 1)
        self.assertFalse(audit['automatic_ocr_math_authorization'])
        self.assertEqual(audit['changes'][0]['before']['width'] - 2,
                         audit['changes'][0]['after']['width'])
        layout = json.loads((self.output / 'manual_layout.json').read_text())
        self.assertEqual(set(layout), {'schema_version','status','source_video_sha256','regions'})
        self.assertEqual(layout['status'], proposals.MANUAL_STATUS)
        self.assertEqual(audit['manual_layout_sha256'], mod.base.sha256(self.output / 'manual_layout.json'))
        self.assertEqual(audit['corrected_preview_sha256'], mod.base.sha256(self.output / 'corrected_preview.png'))

    def test_requires_explicit_confirmation(self):
        self.update()
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output)

    def test_requires_actual_change(self):
        d = json.loads(self.draft.read_text())
        d['reviewer_note'] = 'I inspected the entire video and geometry.'
        self.draft.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_unchanged_note(self):
        d = json.loads(self.draft.read_text())
        d['regions'][0]['width'] -= 2
        self.draft.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_overlap(self):
        self.update(lambda d: d['regions'][0].update(width=400))
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_oob(self):
        self.update(lambda d: d['regions'][0].update(x=620))
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_duplicate_ids(self):
        self.update(lambda d: d['regions'][1].update(table_id='T1'))
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_boolean_coordinate(self):
        self.update(lambda d: d['regions'][0].update(x=True))
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_changed_proposal(self):
        self.update()
        self.p.write_text(self.p.read_text().replace('"human_confirmation": false', '"human_confirmation": true'))
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_wrong_source_video(self):
        self.update()
        other = self.root / 'other.mp4'
        synthetic(other, 'flat')
        with self.assertRaises(ValueError):
            mod.apply(other, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_output_collision(self):
        self.update()
        target = self.output / 'correction_audit.json'
        target.write_text('protected')
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)
        self.assertEqual(target.read_text(), 'protected')

    def test_rejects_symlink_draft(self):
        self.update()
        self.draft.rename(self.root / 'original.json')
        self.draft.symlink_to(self.root / 'original.json')
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_extra_ocr_authorization(self):
        self.update(lambda d: d.update(automatic_ocr_math_authorization=True))
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_rejects_duplicate_json_keys(self):
        self.update()
        self.draft.write_text(self.draft.read_text().replace('"schema_version": 1',
                                 '"schema_version": 1, "schema_version": 1', 1))
        with self.assertRaises(ValueError):
            mod.apply(self.video, self.p, self.draft, self.output, confirmed=True)

    def test_template_collision(self):
        with self.assertRaises(ValueError):
            mod.draft_template(self.video, self.p, self.draft)


if __name__ == '__main__':
    unittest.main()
