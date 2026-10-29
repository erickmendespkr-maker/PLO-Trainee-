"""Synthetic security, arithmetic, and offline HTML integration tests."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from offline_acknowledged_ev_sensitivity_html import render, main
from offline_conditional_ev_sensitivity import build as build_sensitivity
from offline_reviewed_equity_clip_report import digest
from test_offline_conditional_ev_sensitivity import sample


class AcknowledgedSensitivityHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sensitivity_fixture = build_sensitivity(sample('PLO6'))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clip = self.root / 'clip.mp4'
        self.clip.write_bytes(b'synthetic video placeholder for HTML unit test')
        self.sensitivity = copy.deepcopy(self.sensitivity_fixture)
        hero = self.sensitivity['hero_cards']
        board = self.sensitivity['board_cards']
        self.report = {
            'schema_version': 1,
            'analysis_status': 'offline_conditional_equity_after_human_frame_acknowledgement',
            'source_clip_sha256': digest(self.clip),
            'binding_replay_audit_rerun': False,
            'manual_cards_claimed_reviewed_not_independently_verified': True,
            'hero_actor_at_selected_action_verified': False,
            'selected_action_strategic_correctness_verified': False,
            'ocr_semantics_verified': False,
            'opponent_range_is_assumption': True,
            'variant': 'PLO6', 'hand_id': 'SYNTHETIC_H1',
            'selected_action_ocr_text_not_graded': 'raise? (OCR unverified)',
            'card_frame_evidence_count': 11,
            'card_frame_evidence_claimed_not_independently_verified': True,
            'source_snapshot_manifest_sha256': 'a'*64,
            'source_gallery_confirmation_sha256': 'b'*64,
            'human_snapshot_acknowledgement_validated': True,
            'human_acknowledged_cards': 11,
            'card_visibility_machine_verified': False,
            'decoded_frame_pts_verified': False,
            'reviewed_cards_are_human_assertions': True,
            'source_video_replay_audit_rerun': False,
            'equity_result': {
                'analysis_status': 'offline_manual_assumptions_monte_carlo_only',
                'strategic_correctness_verified': False,
                'ocr_semantics_verified': False,
                'player_identity_verified': False,
                'variant': 'PLO6', 'hero_cards': hero.copy(), 'board_cards': board.copy(),
                'equity': .5, 'equity_ci95_sampling_only': [.4, .6],
                'iterations': 500, 'seed': 42, 'opponent_model_kind': 'uniform',
            },
        }

    def html(self):
        return render(self.report, self.sensitivity, digest(self.clip))

    def test_full_html_and_no_external_assets(self):
        html = self.html()
        for term in ('<video', 'clip.mp4', '<svg', '<table>', 'EV call', 'EV raise',
                     'Confirmação humana registrada', 'Não é avaliação da jogada',
                     'não constitui IC conjunto de 95%', 'não são refeitos'):
            self.assertIn(term, html)
        self.assertNotIn('https://', html)
        self.assertNotIn('<script', html)

    def test_deterministic(self):
        self.assertEqual(self.html(), self.html())

    def test_grid_table_rows(self):
        html = self.html()
        self.assertEqual(html.count('<tr>'), 1 + len(self.sensitivity['fold_probabilities']))
        self.assertIn('100%', html)

    def test_multiple_hypotheses_legend(self):
        extra = copy.deepcopy(self.sensitivity['hypotheses'][0])
        extra['label'] = 'different assumed range'
        self.sensitivity['hypotheses'].append(extra)
        html = self.html()
        self.assertIn('different assumed range', html)
        self.assertEqual(html.count('<polyline'), 2)

    def test_reject_mismatched_cards(self):
        self.sensitivity['hero_cards'][0] = '2s'
        with self.assertRaises(ValueError): self.html()

    def test_reject_mismatched_board(self):
        self.sensitivity['board_cards'][0] = '2s'
        with self.assertRaises(ValueError): self.html()

    def test_reject_mismatched_variant(self):
        self.sensitivity['variant'] = 'PLO5'
        with self.assertRaises(ValueError): self.html()

    def test_reject_legacy_unacknowledged_report(self):
        self.report['analysis_status'] = 'offline_conditional_manual_cards_equity_not_action_grade'
        with self.assertRaises(ValueError): self.html()

    def test_reject_forged_action_grade(self):
        self.sensitivity['action_observed_or_graded'] = True
        with self.assertRaises(ValueError): self.html()

    def test_reject_forged_range_confidence(self):
        self.sensitivity['range_models_are_reviewer_assumptions'] = False
        with self.assertRaises(ValueError): self.html()

    def test_reject_changed_clip(self):
        self.clip.write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.html()

    def test_reject_forged_human_acknowledgement(self):
        self.report['human_acknowledged_cards'] = 10
        with self.assertRaises(ValueError): self.html()

    def test_reject_tampered_ev_arithmetic(self):
        self.sensitivity['hypotheses'][0]['points'][1]['raise_ev_incremental'] += 5
        with self.assertRaises(ValueError): self.html()

    def test_reject_tampered_marginal_bounds(self):
        self.sensitivity['hypotheses'][0]['points'][1]['raise_ev_ci95_sampling_only_fixed_ranges_and_fold_probability'] = [10000, 10001]
        with self.assertRaises(ValueError): self.html()

    def test_reject_inconsistent_probability_grid(self):
        self.sensitivity['fold_probabilities'][1] = .7
        with self.assertRaises(ValueError): self.html()

    def test_reject_invalid_probability_type(self):
        self.sensitivity['fold_probabilities'][0] = True
        with self.assertRaises(ValueError): self.html()

    def test_reject_invalid_label(self):
        self.sensitivity['hypotheses'][0]['label'] = '<img src=x onerror=alert(1)>'
        with self.assertRaises(ValueError): self.html()

    def test_escape_ocr_text(self):
        self.report['selected_action_ocr_text_not_graded'] = '<img src=x onerror=alert(1)>'
        html = self.html()
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)

    def test_cli_writes_once_without_overwrite(self):
        report = self.root / 'report.json'
        sensitivity = self.root / 'sensitivity.json'
        output = self.root / 'explanation.html'
        report.write_text(json.dumps(self.report), encoding='utf-8')
        sensitivity.write_text(json.dumps(self.sensitivity), encoding='utf-8')
        self.assertEqual(main([str(report), str(sensitivity), str(self.clip), str(output)]), 0)
        self.assertIn('<svg', output.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            main([str(report), str(sensitivity), str(self.clip), str(output)])

    def test_cli_requires_clip_basename(self):
        report = self.root / 'report.json'
        sensitivity = self.root / 'sensitivity.json'
        output = self.root / 'explanation.html'
        report.write_text(json.dumps(self.report))
        sensitivity.write_text(json.dumps(self.sensitivity))
        renamed = self.root / 'other.mp4'
        renamed.write_bytes(self.clip.read_bytes())
        with self.assertRaises(ValueError):
            main([str(report), str(sensitivity), str(renamed), str(output)])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not installed')
    def test_real_ffmpeg_mp4_html_generation(self):
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=black:s=160x90:r=5:d=1', '-an', '-c:v', 'mpeg4',
                        '-y', str(self.clip)], check=True, timeout=15)
        self.report['source_clip_sha256'] = digest(self.clip)
        html = self.html()
        self.assertIn('clip.mp4', html)
        self.assertIn(digest(self.clip), html)


if __name__ == '__main__':
    unittest.main()
