"""Synthetic tests for browser review; visual truth is never certified."""
import json
import unittest
from pathlib import Path

import test_offline_hand_frame_evidence_audit as fixture
import offline_visual_evidence_review_ui as ui


class VisualReviewUiTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixture.EvidenceAuditTests('test_matching_frame_bytes_not_visual_truth')
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def packet(self):
        f = self.fx
        return ui.build(f.ocr_file, f.rec_file, f.review_file, f.frames)

    def test_linked_frame_embedded_without_math_promotion(self):
        data = self.packet()
        self.assertEqual(len(data['cards']), 1)
        self.assertTrue(data['cards'][0]['evidence'][0]['image'].startswith('data:image/png;base64,'))
        self.assertEqual(data['eligible_for_equity'], 0)
        self.assertFalse(data['equity_or_ev_calculated'])

    def test_unmatched_correction_has_no_image(self):
        self.fx.draft['hands'][0]['fields'][0]['reviewer_value'] = 'Kd'
        self.fx.draft_file.write_text(json.dumps(self.fx.draft))
        import offline_hand_street_review_import as importer
        self.fx.review_file.write_text(json.dumps(importer.build(self.fx.rec_file, self.fx.worksheet_file, self.fx.draft_file)))
        self.assertEqual(self.packet()['cards'][0]['evidence'], [])

    def test_tampered_frame_rejected(self):
        self.fx.frame_file.write_bytes(b'altered')
        with self.assertRaises(ValueError): self.packet()

    def test_frame_changed_after_audit_rejected(self):
        from unittest.mock import patch
        original = ui.audit.build
        def tamper(*args):
            result = original(*args)
            self.fx.frame_file.write_bytes(b'changed after audit')
            return result
        with patch.object(ui.audit, 'build', side_effect=tamper):
            with self.assertRaisesRegex(ValueError, 'frame changed after audit'):
                self.packet()

    def test_bad_review_ledger_rejected(self):
        self.fx.review_file.write_text('{}')
        with self.assertRaises(ValueError): self.packet()

    def test_html_escape_script_breakout(self):
        packet = self.packet()
        packet['cards'][0]['value_unverified'] = '</script><img onerror=alert(1)>'
        page = ui.render(packet)
        self.assertEqual(page.count('</script>'), 1)
        self.assertIn('\\u003c/script\\u003e', page)

    def test_cli_does_not_overwrite(self):
        f = self.fx
        target = f.root/'visual.html'
        args = [str(f.ocr_file),str(f.rec_file),str(f.review_file),str(f.frames),str(target)]
        self.assertEqual(ui.main(args),0)
        with self.assertRaises(ValueError): ui.main(args)


if __name__ == '__main__': unittest.main()
