"""Synthetic tests for the acknowledged-card-to-EV offline bundle."""
import copy
import shutil
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from offline_acknowledged_sensitivity_bundle import build, main
from offline_reviewed_equity_clip_report import digest


def assumptions():
    return {'schema_version': 1, 'pot_now': 100, 'call_cost': 20,
            'raise_extra': 40, 'fold_probabilities': [0, .35, 1],
            'hypotheses': [{'label': 'uniform', 'call_model': {'kind': 'uniform'},
                            'raise_called_model': {'kind': 'uniform'},
                            'call_iterations': 4, 'raise_called_iterations': 4,
                            'call_seed': 42, 'raise_called_seed': 43,
                            'fold_probability_assumed': .35}]}


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clip = self.root / 'clip.mp4'
        self.clip.write_bytes(b'synthetic MP4 placeholder: not a real video')
        # Synthetic human-acknowledgement fixture; not proof of video content.
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
            'variant': 'PLO5', 'hand_id': 'SYNTHETIC_1',
            'selected_action_ocr_text_not_graded': 'raise? OCR',
            'card_frame_evidence_count': 10,
            'card_frame_evidence_claimed_not_independently_verified': True,
            'source_snapshot_manifest_sha256': 'a'*64,
            'source_gallery_confirmation_sha256': 'b'*64,
            'human_snapshot_acknowledgement_validated': True,
            'human_acknowledged_cards': 10,
            'card_visibility_machine_verified': False,
            'decoded_frame_pts_verified': False,
            'reviewed_cards_are_human_assertions': True,
            'source_video_replay_audit_rerun': False,
            'equity_result': {
                'analysis_status': 'offline_manual_assumptions_monte_carlo_only',
                'strategic_correctness_verified': False,
                'ocr_semantics_verified': False,
                'player_identity_verified': False,
                'variant': 'PLO5',
                'hero_cards': ['As', 'Ks', 'Qh', 'Jh', 'Tc'],
                'board_cards': ['2c', '3d', '4h', '5s', '6c'],
                'equity': .5, 'equity_ci95_sampling_only': [.4, .6],
                'iterations': 4, 'seed': 42, 'opponent_model_kind': 'uniform',
            },
        }
        self.config = assumptions()

    def build(self):
        return build(self.report, self.config, digest(self.clip), 'c'*64, 'd'*64)

    def test_two_variants(self):
        for variant in ('PLO5', 'PLO6'):
            with self.subTest(variant=variant):
                self.report['variant'] = variant
                self.report['equity_result']['variant'] = variant
                if variant == 'PLO6':
                    self.report['equity_result']['hero_cards'].append('9d')
                    self.report['human_acknowledged_cards'] = 11
                    self.report['card_frame_evidence_count'] = 11
                result, html = self.build()
                self.assertEqual(result['variant'], variant)
                self.assertIn('Rastreabilidade', html)
                self.assertFalse(result['action_observed_or_graded'])

    def test_copy_cards_and_provenance(self):
        result, html = self.build()
        self.assertEqual(result['hero_cards'], self.report['equity_result']['hero_cards'])
        self.assertEqual(result['source_acknowledged_report_sha256'], 'c'*64)
        self.assertEqual(result['source_assumptions_sha256'], 'd'*64)
        self.assertIn('d'*64, html)
        self.assertIn('clip.mp4', html)
        self.assertNotIn('https://', html)
        self.assertNotIn('<script', html)

    def test_determinism(self):
        self.assertEqual(self.build(), self.build())

    def test_no_card_or_action_override(self):
        for key, value in [('hero_cards', ['2s']), ('board_cards', []),
                           ('observed_action', 'raise'), ('manual_review_confirmed', True)]:
            with self.subTest(key=key):
                self.config[key] = value
                with self.assertRaises(ValueError): self.build()
                del self.config[key]
        self.config['hypotheses'][0]['hero_cards'] = ['2s']
        with self.assertRaises(ValueError): self.build()

    def test_reject_unsafe_report(self):
        for key, value in [('human_snapshot_acknowledgement_validated', False),
                           ('hero_actor_at_selected_action_verified', True),
                           ('card_visibility_machine_verified', True)]:
            with self.subTest(key=key):
                original = self.report[key]
                self.report[key] = value
                with self.assertRaises(ValueError): self.build()
                self.report[key] = original

    def test_reject_wrong_clip(self):
        self.clip.write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.build()

    def test_reject_invalid_range_and_grid(self):
        self.config['hypotheses'][0]['call_model'] = {'kind': 'invalid'}
        with self.assertRaises(ValueError): self.build()
        self.config['hypotheses'][0]['call_model'] = {'kind': 'uniform'}
        self.config['fold_probabilities'] = [0.5, 0.2]
        with self.assertRaises(ValueError): self.build()

    def test_two_hypotheses_and_escaped_labels(self):
        other = copy.deepcopy(self.config['hypotheses'][0])
        other['label'] = 'tight & uncertain'
        self.config['hypotheses'].append(other)
        result, html = self.build()
        self.assertEqual(len(result['hypotheses']), 2)
        self.assertIn('tight &amp; uncertain', html)
        self.assertEqual(html.count('<polyline'), 2)

    def test_cli_outputs_and_no_overwrite(self):
        report_path, config_path = self.root/'report.json', self.root/'assumptions.json'
        output_json, output_html = self.root/'sensitivity.json', self.root/'explanation.html'
        report_path.write_text(json.dumps(self.report), encoding='utf-8')
        config_path.write_text(json.dumps(self.config), encoding='utf-8')
        args = [str(report_path), str(config_path), str(self.clip), str(output_json), str(output_html)]
        self.assertEqual(main(args), 0)
        result = json.loads(output_json.read_text())
        self.assertEqual(result['source_acknowledged_report_sha256'], digest(report_path))
        self.assertEqual(result['source_assumptions_sha256'], digest(config_path))
        self.assertIn(digest(self.clip), output_html.read_text())
        with self.assertRaises(ValueError): main(args)

    def test_cli_rejects_existing_html_without_creating_json(self):
        rp, cp = self.root/'report.json', self.root/'assumptions.json'
        rp.write_text(json.dumps(self.report)); cp.write_text(json.dumps(self.config))
        html = self.root/'explanation.html'
        html.write_text('do not overwrite')
        with self.assertRaises(ValueError):
            main([str(rp), str(cp), str(self.clip), str(self.root/'sensitivity.json'), str(html)])
        self.assertFalse((self.root/'sensitivity.json').exists())
        self.assertEqual(html.read_text(), 'do not overwrite')

    def test_cli_rejects_sources_as_outputs(self):
        rp, cp = self.root/'report.json', self.root/'assumptions.json'
        rp.write_text(json.dumps(self.report)); cp.write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):
            main([str(rp), str(cp), str(self.clip), str(rp), str(self.root/'explanation.html')])

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg unavailable')
    def test_real_synthetic_ffmpeg_clip(self):
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=black:s=160x90:r=5:d=1', '-an', '-c:v', 'mpeg4',
                        '-y', str(self.clip)], check=True, timeout=15)
        self.report['source_clip_sha256'] = digest(self.clip)
        result, html = self.build()
        self.assertEqual(result['source_clip_sha256'], digest(self.clip))
        self.assertIn('clip.mp4', html)

    def test_cli_subprocess(self):
        rp, cp = self.root/'report.json', self.root/'assumptions.json'
        rp.write_text(json.dumps(self.report)); cp.write_text(json.dumps(self.config))
        run = subprocess.run([sys.executable,
            str(Path(__file__).with_name('offline_acknowledged_sensitivity_bundle.py')),
            str(rp), str(cp), str(self.clip), str(self.root/'sensitivity.json'),
            str(self.root/'explanation.html')], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(json.loads(run.stdout)['action_graded'])


if __name__ == '__main__':
    unittest.main()
