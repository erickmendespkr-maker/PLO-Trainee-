"""Synthetic FFmpeg-backed tests for manually declared card/frame timestamps."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_manual_frame_snapshot_audit as m


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg/FFprobe required')
class FrameAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clip = self.root / 'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=2:d=2',
                        '-c:v', 'mpeg4', '-y', str(self.clip)], check=True, timeout=15)
        self.binding = self.root / 'binding.json'
        self.review = self.root / 'review.json'
        self.out = self.root / 'snapshots'
        self.b = dict(schema_version=1,
            analysis_status='offline_selected_action_roi_clip_identity_only',
            hand_id='H4', table_id=4, variant='PLO5', proposal_index=2,
            timestamp_seconds=0.5, reviewed_action_text='raise',
            roi_png_sha256='a'*64, source_video_sha256='b'*64,
            source_roi_ocr_report_sha256='c'*64, source_timeline_sha256='d'*64,
            source_triage_sha256='e'*64, source_clip_attestation_sha256='f'*64,
            clip_sha256=sha(self.clip),
            selected_action_to_replayed_roi_verified=True,
            selected_action_to_source_video_and_clip_verified=True,
            ocr_semantics_verified=False, actor_identified=False,
            hands_reconstructed=False, ready_for_equity_or_ev=False)
        self.cards = ['As', 'Ks', '2c', '3d', '4c', 'Qs', 'Js', 'Ts', '8d', '7c']
        self.r = dict(schema_version=1, source_clip_sha256=sha(self.clip),
            hand_id='H4', table_id=4, variant='PLO5', proposal_index=2,
            manual_cards_confirmed=True, review_method='manual_video_frame_review',
            review_notes='Synthetic test notes only.', opponent_model={'kind':'uniform'},
            iterations=2, seed=42,
            hero_cards=self.cards[:5], board_cards=self.cards[5:],
            card_frame_evidence=[{'card': c, 'clip_timestamp_seconds': 0.5}
                                 for c in self.cards])
        self.write()

    def write(self):
        self.binding.write_text(json.dumps(self.b))
        self.r['source_binding_sha256'] = sha(self.binding)
        self.review.write_text(json.dumps(self.r))

    def run_audit(self):
        return m.build(self.binding, self.clip, self.review, self.out)

    def test_real_ffmpeg_extract_and_manifest(self):
        result = self.run_audit()
        self.assertEqual(len(result['frames']), 1)
        self.assertEqual(len(result['card_frame_links']), 10)
        self.assertFalse(result['card_visibility_verified'])
        self.assertFalse(result['exact_decoded_frame_timestamp_verified'])
        frame = self.out / result['frames'][0]['file']
        self.assertEqual(result['frames'][0]['sha256'], sha(frame))
        self.assertEqual(json.loads((self.out/'manifest.json').read_text()), result)

    def test_two_timestamps_create_two_pngs(self):
        self.r['card_frame_evidence'][-1]['clip_timestamp_seconds'] = 1.0
        self.write()
        self.assertEqual(len(self.run_audit()['frames']), 2)

    def test_repeat_deterministic_frame_hash(self):
        first = self.run_audit()
        second = m.build(self.binding, self.clip, self.review, self.root/'again')
        self.assertEqual(first['frames'], second['frames'])

    def test_reject_timestamp_equal_duration(self):
        self.r['card_frame_evidence'][0]['clip_timestamp_seconds'] = 2
        self.write()
        with self.assertRaisesRegex(ValueError, 'timestamp'):
            self.run_audit()
        self.assertFalse(self.out.exists())

    def test_reject_boolean_timestamp(self):
        self.r['card_frame_evidence'][0]['clip_timestamp_seconds'] = True
        self.write()
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_duplicate_card_evidence(self):
        self.r['card_frame_evidence'][0]['card'] = 'Ks'
        self.write()
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_missing_card_evidence(self):
        self.r['card_frame_evidence'].pop()
        self.write()
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_false_manual_review(self):
        self.r['manual_cards_confirmed'] = False
        self.write()
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_binding_tamper(self):
        self.b['table_id'] = 3
        self.write()
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_clip_tamper(self):
        self.clip.write_bytes(b'not a video')
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_review_source_hash_tamper(self):
        self.r['source_clip_sha256'] = '0'*64
        self.write()
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.run_audit()

    def test_reject_unknown_review_field(self):
        self.r['ocr_verified'] = True
        self.write()
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_missing_notes(self):
        self.r['review_notes'] = ''
        self.write()
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_existing_output(self):
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError, 'new directory'):
            self.run_audit()

    def test_reject_symlink_output(self):
        self.out.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_symlink_clip(self):
        link = self.root/'link.mp4'
        link.symlink_to(self.clip)
        with self.assertRaises(ValueError):
            m.build(self.binding, link, self.review, self.out)

    def test_reject_wrong_variant_card_count(self):
        self.r['variant'] = 'PLO6'
        self.write()
        with self.assertRaises(ValueError): self.run_audit()

    def test_reject_wrong_actor_claim_in_binding(self):
        self.b['actor_identified'] = True
        self.write()
        with self.assertRaises(ValueError): self.run_audit()


if __name__ == '__main__': unittest.main()
