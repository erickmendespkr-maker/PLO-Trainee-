"""Synthetic end-to-end clip tests: evidence binding, accounting, FFmpeg overlay."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_ev_decision_clip as clips
import offline_mc_input_contract as contract
import offline_mc_action_ev as action_ev


class ClipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.has_ffmpeg = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / 'input.mp4'
        if self.has_ffmpeg:
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                            '-f', 'lavfi', '-i', 'color=c=blue:s=320x180:r=12:d=5',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(self.video)],
                           check=True, capture_output=True, timeout=20)
            video_sha = contract.sha256(self.video)
        else:
            video_sha = 'a'*64
        self.summary = {'schema_version': 1,
                        'status': 'offline_hand_visual_summary_unverified_not_math_ready',
                        'source_video_sha256_claim': video_sha,
                        'video_content_not_semantically_verified': True,
                        'reviewer_claims_not_authenticated': True,
                        'equity_or_ev_calculated': False, 'eligible_for_equity': 0,
                        'hand_count': 1, 'hands': [
                            {'hand_id': 'H1', 'table_id': 'T1', 'math_ready': False,
                             'eligible_for_equity': False, 'declared_fields': [
                                 {'field': 'action', 'street': 'river',
                                  'visual_status_unverified': 'seen_by_reviewer',
                                  'evidence_pts_seconds': [2.0]}]}]}
        self.summary_path = self.root / 'summary.json'
        self.ev_path = self.root / 'ev.json'
        self.decision_path = self.root / 'decision.json'
        self.dump(self.summary_path, self.summary)
        self.ev = {
            'schema_version': 1, 'status': 'conditional_chip_ev_estimates_not_strategy_verdict',
            'hand_id': 'H1', 'table_id': 'T1', 'variant': 'PLO5', 'street': 'river',
            'source_scenario_sha256': 'b'*64, 'source_action_sha256': 'c'*64,
            'input_origin_claim': 'independent_manual_transcription_not_authenticated',
            'automatic_ocr_math_authorization': False,
            'model': 'single_decision_showdown_no_future_betting_zero_rake',
            'rake_chips': 0, 'pot_before_action_chips': 100,
            'to_call_chips': 25, 'ev_fold_chips': 0.0,
            'ev_call_or_check_chips': 100.0, 'call_action_label': 'call',
            'ev_call_or_check_confidence_interval_95_approx_chips': [100, 100],
            'ev_raise_model': {
                'ev_chips': 50.0, 'raise_total_chips': 75,
                'fold_probability_assumed': 0.2,
                'called_equity_fraction_assumed_not_simulated': 0.5,
                'confidence_interval_95': None,
                'opponent_can_match_raise_assumed': True,
            },
            'equity_fraction': 1.0, 'equity_confidence_interval_95_approx': [1, 1],
            'seed': 123, 'simulations': 1000, 'equity_calculated': True,
            'ev_calculated': True,
            'scenario_assumptions': 'Explicit manual range assumptions for this scenario.',
            'action_assumptions': 'No rake or future action in this model.',
        }
        self.ev['source_summary_sha256'] = contract.sha256(self.summary_path)
        self.ev['source_video_sha256_claim'] = video_sha
        self.dump(self.ev_path, self.ev)
        self.decision = {'schema_version': 1,
                         'source_summary_sha256': contract.sha256(self.summary_path),
                         'source_ev_sha256': contract.sha256(self.ev_path),
                         'hand_id': 'H1', 'table_id': 'T1',
                         'decision_pts_seconds': 2.0, 'action_taken_claim': 'raise',
                         'action_origin': 'manual_review_unverified',
                         'reviewer_confidence_claim': 0.6,
                         'notes': 'Reviewer claims a raise at the indicated video timestamp.',
                         'clip_before_seconds': 1.0, 'clip_after_seconds': 2.0}
        self.dump(self.decision_path, self.decision)

    @staticmethod
    def dump(path, obj):
        path.write_text(json.dumps(obj), encoding='utf-8')

    def build(self):
        return clips.validate(self.summary, self.ev, self.decision,
                              contract.sha256(self.summary_path),
                              contract.sha256(self.ev_path),
                              self.summary['source_video_sha256_claim'], 5)

    def test_valid_gap_and_clip_interval(self):
        plan = self.build()
        self.assertEqual(plan['conditional_gap_to_highest_modeled_ev_chips_not_regret'], 50)
        self.assertEqual(plan['clip_start_seconds'], 1)
        self.assertEqual(plan['clip_duration_seconds'], 3)
        self.assertFalse(plan['automatic_ocr_math_authorization'])

    def test_fold_priority_gap(self):
        self.decision['action_taken_claim'] = 'fold'
        self.assertEqual(self.build()['conditional_priority_score_chips_not_strategy_verdict'], 100)

    def test_call_priority_zero(self):
        self.decision['action_taken_claim'] = 'call'
        self.assertEqual(self.build()['conditional_priority_score_chips_not_strategy_verdict'], 0)

    def test_missing_action_evidence_blocks(self):
        self.summary['hands'][0]['declared_fields'][0]['field'] = 'hero_card'
        with self.assertRaisesRegex(ValueError, 'action evidence'): self.build()

    def test_uncertain_visual_blocks(self):
        self.summary['hands'][0]['declared_fields'][0]['visual_status_unverified'] = 'uncertain'
        with self.assertRaisesRegex(ValueError, 'action evidence'): self.build()

    def test_distant_timestamp_blocks(self):
        self.decision['decision_pts_seconds'] = 3.0
        with self.assertRaisesRegex(ValueError, 'action evidence'): self.build()

    def test_invalid_video_sha_blocks(self):
        self.summary['source_video_sha256_claim'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'EV report'): self.build()

    def test_wrong_summary_sha_blocks(self):
        self.ev['source_summary_sha256'] = 'b'*64
        with self.assertRaisesRegex(ValueError, 'EV report'): self.build()

    def test_wrong_ev_sha_blocks(self):
        self.decision['source_ev_sha256'] = 'b'*64
        with self.assertRaisesRegex(ValueError, 'provenance'): self.build()

    def test_wrong_hand_blocks(self):
        self.decision['hand_id'] = 'H2'
        with self.assertRaisesRegex(ValueError, 'identity'): self.build()

    def test_duplicate_hand_blocks(self):
        self.summary['hands'].append(copy.deepcopy(self.summary['hands'][0]))
        self.summary['hand_count'] = 2
        with self.assertRaisesRegex(ValueError, 'uniquely'): self.build()

    def test_ocr_promotion_blocks(self):
        self.ev['automatic_ocr_math_authorization'] = True
        with self.assertRaisesRegex(ValueError, 'EV report'): self.build()

    def test_fake_math_ready_blocks(self):
        self.summary['hands'][0]['math_ready'] = True
        with self.assertRaisesRegex(ValueError, 'unverified hand'): self.build()

    def test_wrong_call_ev_blocks(self):
        self.ev['ev_call_or_check_chips'] += 1
        with self.assertRaisesRegex(ValueError, 'accounting'): self.build()

    def test_wrong_raise_ev_blocks(self):
        self.ev['ev_raise_model']['ev_chips'] += 1
        with self.assertRaisesRegex(ValueError, 'raise EV accounting'): self.build()

    def test_raise_missing_blocks(self):
        self.ev['ev_raise_model'] = None
        with self.assertRaisesRegex(ValueError, 'chosen action'): self.build()

    def test_nan_confidence_blocks(self):
        self.decision['reviewer_confidence_claim'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'reviewer confidence'): self.build()

    def test_bool_confidence_blocks(self):
        self.decision['reviewer_confidence_claim'] = True
        with self.assertRaisesRegex(ValueError, 'reviewer confidence'): self.build()

    def test_short_notes_blocks(self):
        self.decision['notes'] = 'short'
        with self.assertRaisesRegex(ValueError, 'notes'): self.build()

    def test_unmodeled_check_blocks(self):
        self.decision['action_taken_claim'] = 'check'
        with self.assertRaisesRegex(ValueError, 'chosen action'): self.build()

    def test_wrong_confidence_interval_blocks(self):
        self.ev['ev_call_or_check_confidence_interval_95_approx_chips'] = [0, 0]
        with self.assertRaisesRegex(ValueError, 'interval'): self.build()

    def test_outside_duration_blocks(self):
        self.decision['decision_pts_seconds'] = 10
        with self.assertRaisesRegex(ValueError, 'decision PTS'): self.build()

    def test_no_silent_raise_interval(self):
        self.ev['ev_raise_model']['confidence_interval_95'] = [0, 100]
        with self.assertRaisesRegex(ValueError, 'raise model'): self.build()

    def test_cli_ffmpeg_mp4_with_burned_overlay(self):
        if not self.has_ffmpeg: self.skipTest('ffmpeg/ffprobe not installed')
        out = self.root / 'out'; out.mkdir()
        args = [str(self.summary_path), str(self.ev_path), str(self.decision_path),
                str(self.video), str(out), 'clip-H1']
        self.assertEqual(clips.main(args), 0)
        mp4, report = out / 'clip-H1.mp4', out / 'clip-H1.json'
        self.assertGreater(mp4.stat().st_size, 1000)
        result = json.loads(report.read_text())
        self.assertEqual(result['rendered_clip_sha256'], contract.sha256(mp4))
        self.assertTrue(result['overlay_burned_in'])
        self.assertEqual(result['source_decision_sha256'], contract.sha256(self.decision_path))
        self.assertFalse(result['automatic_ocr_math_authorization'])
        self.assertGreater(clips.video_duration(mp4), 2)
        # Regression: '%' in equity text previously made drawtext silently
        # render no text. Verify actual overlay pixels, not only MP4 existence.
        def pixel(path, second):
            proc = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                                   '-ss', str(second), '-i', str(path), '-frames:v', '1',
                                   '-vf', 'crop=2:2:350:50', '-pix_fmt', 'rgb24',
                                   '-f', 'rawvideo', '-'], capture_output=True,
                                  check=True, timeout=20)
            return proc.stdout
        source_pixel = pixel(self.video, 2.0)
        overlay_pixel = pixel(mp4, 1.0)
        self.assertEqual(len(source_pixel), 12)
        self.assertEqual(len(overlay_pixel), 12)
        self.assertGreater(source_pixel[2] - overlay_pixel[2], 40)
        with self.assertRaisesRegex(ValueError, 'output already exists'): clips.main(args)

    def test_cli_rejects_changed_video_without_writing(self):
        if not self.has_ffmpeg: self.skipTest('ffmpeg/ffprobe not installed')
        out = self.root / 'out'; out.mkdir()
        self.summary['source_video_sha256_claim'] = 'a'*64
        self.dump(self.summary_path, self.summary)
        with self.assertRaisesRegex(ValueError, 'video SHA'):
            clips.main([str(self.summary_path), str(self.ev_path), str(self.decision_path),
                        str(self.video), str(out), 'clip-H1'])
        self.assertEqual(list(out.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
