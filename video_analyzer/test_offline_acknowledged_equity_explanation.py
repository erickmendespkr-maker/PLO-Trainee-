"""Synthetic integration of the acknowledged report with the offline HTML renderer."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_equity_clip_explanation as renderer
from offline_reviewed_equity_clip_report import digest


DEMO = Path(__file__).resolve().parent.parent / 'demo'


class AcknowledgedHtmlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clip = self.root / 'clip.mp4'
        self.clip.write_bytes((DEMO / 'clip.mp4').read_bytes())
        self.report = json.loads((DEMO / 'acknowledged_equity.json').read_text())
        self.assertEqual(digest(self.clip), self.report['source_clip_sha256'])
        self.report_path = self.root / 'acknowledged.json'
        self.out = self.root / 'explanation.html'

    def save(self):
        self.report_path.write_text(json.dumps(self.report), encoding='utf-8')

    def render(self):
        return renderer.render(self.report, digest(self.clip))

    def test_acknowledged_report_rendered_without_strategy_grade(self):
        html = self.render()
        self.assertIn('Confirmação humana registrada', html)
        self.assertIn('11 cartas', html)
        self.assertIn('não reexecuta a auditoria', html)
        self.assertIn('Não é avaliação da jogada', html)
        self.assertIn('100.00%', html)
        self.assertNotIn('https://', html)

    def test_cli_uses_actual_clip_and_writes_once(self):
        self.save()
        self.assertEqual(renderer.main([str(self.report_path), str(self.clip), str(self.out)]), 0)
        self.assertIn('clip.mp4', self.out.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            renderer.main([str(self.report_path), str(self.clip), str(self.out)])

    def test_reject_clip_changed(self):
        self.clip.write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.render()

    def test_escape_ocr_html(self):
        self.report['selected_action_ocr_text_not_graded'] = '<img src=x onerror=alert(1)>'
        html = self.render()
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)

    def test_reject_unconfirmed_cards(self):
        self.report['human_acknowledged_cards'] = 10
        with self.assertRaises(ValueError): self.render()

    def test_reject_false_acknowledgement(self):
        self.report['human_snapshot_acknowledgement_validated'] = False
        with self.assertRaises(ValueError): self.render()

    def test_reject_false_visibility_claim(self):
        self.report['card_visibility_machine_verified'] = True
        with self.assertRaises(ValueError): self.render()

    def test_reject_false_pts_claim(self):
        self.report['decoded_frame_pts_verified'] = True
        with self.assertRaises(ValueError): self.render()

    def test_reject_false_replay_claim(self):
        self.report['source_video_replay_audit_rerun'] = True
        with self.assertRaises(ValueError): self.render()

    def test_reject_false_human_assertion(self):
        self.report['reviewed_cards_are_human_assertions'] = False
        with self.assertRaises(ValueError): self.render()

    def test_reject_bad_manifest_hash(self):
        self.report['source_snapshot_manifest_sha256'] = 'not-a-hash'
        with self.assertRaises(ValueError): self.render()

    def test_reject_missing_confirmation_hash(self):
        del self.report['source_gallery_confirmation_sha256']
        with self.assertRaises(ValueError): self.render()

    def test_reject_frame_count_mismatch(self):
        self.report['card_frame_evidence_count'] = 10
        with self.assertRaises(ValueError): self.render()

    def test_reject_variant_card_count_mismatch(self):
        self.report['variant'] = 'PLO5'
        self.report['equity_result']['variant'] = 'PLO5'
        with self.assertRaises(ValueError): self.render()

    def test_reject_unknown_status(self):
        self.report['analysis_status'] = 'action_grade'
        with self.assertRaises(ValueError): self.render()

    def test_reject_legacy_forged_acknowledgement(self):
        self.report['analysis_status'] = 'offline_conditional_manual_cards_equity_not_action_grade'
        with self.assertRaises(ValueError): self.render()

    def test_reject_unsafe_equity_status(self):
        self.report['equity_result']['strategic_correctness_verified'] = True
        with self.assertRaises(ValueError): self.render()

    def test_reject_unsafe_ocr_status(self):
        self.report['ocr_semantics_verified'] = True
        with self.assertRaises(ValueError): self.render()


if __name__ == '__main__':
    unittest.main()
