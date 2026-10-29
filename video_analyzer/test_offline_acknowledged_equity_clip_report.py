"""Synthetic end-to-end and rejection tests; no poker-platform connection."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_acknowledged_equity_clip_report as gate
import offline_audited_card_gallery as gallery
import offline_manual_frame_snapshot_audit as audit


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class AcknowledgedEquityTests(unittest.TestCase):
    variant = 'PLO6'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clip = self.root / 'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=navy:s=160x90:r=2:d=2',
                        '-c:v', 'mpeg4', '-y', str(self.clip)], check=True, timeout=20)
        self.binding = self.root / 'binding.json'
        self.binding_data = dict(schema_version=1,
            analysis_status='offline_selected_action_roi_clip_identity_only',
            hand_id='HAND_A', table_id=2, variant=self.variant, proposal_index=0,
            timestamp_seconds=0.5, reviewed_action_text='OCR raise (unverified)',
            roi_png_sha256='a'*64, source_video_sha256='b'*64,
            source_roi_ocr_report_sha256='c'*64, source_timeline_sha256='d'*64,
            source_triage_sha256='e'*64, source_clip_attestation_sha256='f'*64,
            clip_sha256=sha(self.clip), selected_action_to_replayed_roi_verified=True,
            selected_action_to_source_video_and_clip_verified=True,
            ocr_semantics_verified=False, actor_identified=False,
            hands_reconstructed=False, ready_for_equity_or_ev=False)
        self.write(self.binding, self.binding_data)
        self.review = self.root / 'review.json'
        hero = ['As', 'Ks', '2c', '3d', '4c'] + (['5d'] if self.variant == 'PLO6' else [])
        board = ['Qs', 'Js', 'Ts', '8d', '7c']
        self.review_data = dict(schema_version=1, source_binding_sha256=sha(self.binding),
            source_clip_sha256=sha(self.clip), hand_id='HAND_A', table_id=2,
            variant=self.variant, proposal_index=0, manual_cards_confirmed=True,
            review_method='manual_video_frame_review',
            review_notes='SYNTHETIC: cards not actually visible in color video.',
            opponent_model={'kind':'uniform'}, iterations=2, seed=42,
            hero_cards=hero, board_cards=board,
            card_frame_evidence=[{'card': c, 'clip_timestamp_seconds': 0.5}
                                 for c in hero + board])
        self.write(self.review, self.review_data)
        self.snap = self.root / 'frames'
        audit.build(self.binding, self.clip, self.review, self.snap)
        self.confirm = self.root / 'confirmation.json'
        manifest, review, names, mh, rh = gallery.load(self.snap, self.review)
        self.confirm_data = dict(schema_version=1, source_manifest_sha256=mh,
            source_manual_review_sha256=rh,
            review_method='human_snapshot_gallery_acknowledgement',
            card_acknowledgements=[dict(card=x['card'], frame_file=x['frame_file'],
                frame_sha256=names[x['frame_file']], human_confirmed=True)
                for x in manifest['card_frame_links']],
            review_notes='SYNTHETIC confirmation for test only, not actual human review.')
        self.write(self.confirm, self.confirm_data)
        self.output = self.root / 'result.json'

    @staticmethod
    def write(path, value):
        Path(path).write_text(json.dumps(value), encoding='utf-8')

    def run_gate(self):
        return gate.build(self.binding, self.clip, self.review, self.snap, self.confirm)

    def assert_rejected(self):
        existed = self.output.exists()
        previous = self.output.read_bytes() if existed else None
        with self.assertRaises((ValueError, OSError)):
            gate.main([str(self.binding), str(self.clip), str(self.review),
                       str(self.snap), str(self.confirm), str(self.output)])
        self.assertEqual(self.output.exists(), existed)
        if existed:
            self.assertEqual(self.output.read_bytes(), previous)

    def test_plo6_complete_synthetic_chain(self):
        r = self.run_gate()
        self.assertEqual(r['human_acknowledged_cards'], 10 if self.variant == 'PLO5' else 11)
        self.assertTrue(r['human_snapshot_acknowledgement_validated'])
        self.assertFalse(r['card_visibility_machine_verified'])
        self.assertFalse(r['hero_actor_at_selected_action_verified'])
        self.assertFalse(r['selected_action_strategic_correctness_verified'])
        self.assertEqual(r['equity_result']['iterations'], 2)
        self.assertEqual(r['equity_result']['equity'], 1.0)
        self.assertIn('sampling error', r['warning'])

    def test_cli_creates_json_once(self):
        args = [str(x) for x in (self.binding, self.clip, self.review, self.snap,
                                 self.confirm, self.output)]
        self.assertEqual(gate.main(args), 0)
        result = json.loads(self.output.read_text())
        self.assertEqual(result['source_gallery_confirmation_sha256'], sha(self.confirm))
        self.assertEqual(result['source_snapshot_manifest_sha256'], sha(self.snap / 'manifest.json'))
        self.assert_rejected()

    def test_deterministic_same_seed(self):
        self.assertEqual(self.run_gate(), self.run_gate())

    def test_source_video_not_rerun(self):
        result = self.run_gate()
        self.assertFalse(result['source_video_replay_audit_rerun'])
        self.assertFalse(result['binding_replay_audit_rerun'])
        self.assertTrue(result['manual_cards_claimed_reviewed_not_independently_verified'])

    def test_reject_unchecked_card(self):
        self.confirm_data['card_acknowledgements'][0]['human_confirmed'] = False
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()

    def test_reject_missing_card_acknowledgement(self):
        self.confirm_data['card_acknowledgements'].pop()
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()

    def test_reject_swapped_card_acknowledgement(self):
        self.confirm_data['card_acknowledgements'][0]['card'] = 'Ac'
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()

    def test_reject_fake_frame_hash(self):
        self.confirm_data['card_acknowledgements'][0]['frame_sha256'] = '0'*64
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()

    def test_reject_wrong_manifest_hash(self):
        self.confirm_data['source_manifest_sha256'] = '0'*64
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()

    def test_reject_wrong_review_hash(self):
        self.confirm_data['source_manual_review_sha256'] = '0'*64
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()

    def test_reject_false_machine_verification(self):
        self.confirm_data['card_visibility_machine_verified'] = True
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()

    def test_reject_tampered_png(self):
        (self.snap / 'frame_00.png').write_bytes(b'not a real PNG')
        self.assert_rejected()

    def test_reject_tampered_manifest(self):
        path = self.snap / 'manifest.json'
        m = json.loads(path.read_text())
        m['source_clip_sha256'] = '0'*64
        self.write(path, m)
        self.assert_rejected()

    def test_reject_modified_review(self):
        self.review_data['seed'] = 43
        self.write(self.review, self.review_data)
        self.assert_rejected()

    def test_reject_modified_binding(self):
        self.binding_data['timestamp_seconds'] = 0.6
        self.write(self.binding, self.binding_data)
        self.assert_rejected()

    def test_reject_modified_clip(self):
        with self.clip.open('ab') as f:
            f.write(b'EXTRA')
        self.assert_rejected()

    def test_reject_unrelated_confirmation(self):
        self.confirm_data['review_method'] = 'auto_ocr'
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()

    def test_reject_symlink_confirmation(self):
        original = self.root / 'actual.json'
        self.confirm.rename(original)
        self.confirm.symlink_to(original)
        self.assert_rejected()

    def test_reject_duplicate_json_keys(self):
        self.confirm.write_text('{"schema_version":1,"schema_version":1}')
        self.assert_rejected()

    def test_reject_unreviewed_cards(self):
        self.review_data['manual_cards_confirmed'] = False
        self.write(self.review, self.review_data)
        self.assert_rejected()

    def test_reject_unsupported_range(self):
        self.review_data['opponent_model'] = {'kind': 'unknown'}
        self.write(self.review, self.review_data)
        self.assert_rejected()

    def test_reject_wrong_snapshot_binding(self):
        mpath = self.snap / 'manifest.json'
        m = json.loads(mpath.read_text())
        m['source_binding_sha256'] = '0'*64
        self.write(mpath, m)
        self.assert_rejected()

    def test_reject_missing_frame(self):
        (self.snap / 'frame_00.png').unlink()
        self.assert_rejected()

    def test_reject_output_overwrite(self):
        self.output.write_text('existing')
        with self.assertRaises(ValueError):
            gate.main([str(x) for x in (self.binding, self.clip, self.review,
                                        self.snap, self.confirm, self.output)])
        self.assertEqual(self.output.read_text(), 'existing')

    def test_reject_output_same_as_source(self):
        with self.assertRaises(ValueError):
            gate.main([str(x) for x in (self.binding, self.clip, self.review,
                                        self.snap, self.confirm, self.review)])

    def test_reject_snapshot_directory_symlink(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.snap, target_is_directory=True)
        with self.assertRaises(ValueError):
            gate.build(self.binding, self.clip, self.review, alias, self.confirm)

    def test_reject_confirmation_without_notes(self):
        self.confirm_data['review_notes'] = ''
        self.write(self.confirm, self.confirm_data)
        self.assert_rejected()


class PLO5AcknowledgedEquityTests(AcknowledgedEquityTests):
    variant = 'PLO5'

    def test_plo5_complete_synthetic_chain(self):
        result = self.run_gate()
        self.assertEqual(result['variant'], 'PLO5')
        self.assertEqual(result['human_acknowledged_cards'], 10)
        self.assertEqual(result['equity_result']['variant'], 'PLO5')


if __name__ == '__main__':
    unittest.main()
