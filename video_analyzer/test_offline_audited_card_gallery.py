"""Synthetic tests for local frame gallery and human acknowledgement validation."""
import copy
import hashlib
import subprocess
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import offline_audited_card_gallery as g
import offline_manual_frame_snapshot_audit as audit


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        clip = self.root / 'clip.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=2:d=2',
                        '-c:v', 'mpeg4', '-y', str(clip)], check=True, timeout=15)
        def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
        binding = self.root / 'binding.json'
        b = dict(schema_version=1,
            analysis_status='offline_selected_action_roi_clip_identity_only',
            hand_id='H4', table_id=4, variant='PLO5', proposal_index=2,
            timestamp_seconds=0.5, reviewed_action_text='raise',
            roi_png_sha256='a'*64, source_video_sha256='b'*64,
            source_roi_ocr_report_sha256='c'*64, source_timeline_sha256='d'*64,
            source_triage_sha256='e'*64, source_clip_attestation_sha256='f'*64,
            clip_sha256=sha(clip), selected_action_to_replayed_roi_verified=True,
            selected_action_to_source_video_and_clip_verified=True,
            ocr_semantics_verified=False, actor_identified=False,
            hands_reconstructed=False, ready_for_equity_or_ev=False)
        binding.write_text(json.dumps(b))
        self.review = self.root / 'review.json'
        cards = ['As', 'Ks', '2c', '3d', '4c', 'Qs', 'Js', 'Ts', '8d', '7c']
        r = dict(schema_version=1, source_binding_sha256=sha(binding),
            source_clip_sha256=sha(clip), hand_id='H4', table_id=4,
            variant='PLO5', proposal_index=2, manual_cards_confirmed=True,
            review_method='manual_video_frame_review',
            review_notes='Synthetic review only, not verified cards.',
            opponent_model={'kind':'uniform'}, iterations=2, seed=42,
            hero_cards=cards[:5], board_cards=cards[5:],
            card_frame_evidence=[{'card': c, 'clip_timestamp_seconds': 0.5} for c in cards])
        self.review.write_text(json.dumps(r))
        self.snap = self.root / 'frames'
        audit.build(binding, clip, self.review, self.snap)
        self.manifest = self.snap / 'manifest.json'
        self.gallery = self.snap / 'gallery.html'
        self.confirmation = self.root / 'confirm.json'

    def payload(self):
        manifest, review, names, mh, rh = g.load(self.snap, self.review)
        return dict(schema_version=1, source_manifest_sha256=mh,
                    source_manual_review_sha256=rh,
                    review_method='human_snapshot_gallery_acknowledgement',
                    card_acknowledgements=[dict(card=x['card'], frame_file=x['frame_file'],
                    frame_sha256=names[x['frame_file']], human_confirmed=True)
                    for x in manifest['card_frame_links']],
                    review_notes='Synthetic human acknowledgement only.')

    def write(self, payload):
        self.confirmation.write_text(json.dumps(payload), encoding='utf-8')

    def test_gallery_renders_offline(self):
        g.generate(self.snap, self.review, self.gallery)
        page = self.gallery.read_text()
        self.assertIn('frame_00.png', page)
        self.assertNotIn('https://', page)
        self.assertIn('human_snapshot_gallery_acknowledgement', page)

    def test_verify_human_confirmation(self):
        self.write(self.payload())
        r = g.verify(self.snap, self.review, self.confirmation)
        self.assertEqual(r['acknowledged_cards'], 10)
        self.assertFalse(r['card_visibility_machine_verified'])
        self.assertFalse(r['ocr_semantics_verified'])

    def test_reject_unchecked_card(self):
        p = self.payload(); p['card_acknowledgements'][3]['human_confirmed'] = False
        self.write(p)
        with self.assertRaises(ValueError): g.verify(self.snap, self.review, self.confirmation)

    def test_reject_tampered_png(self):
        (self.snap / 'frame_00.png').write_bytes(b'fake')
        with self.assertRaisesRegex(ValueError, 'hash'): g.generate(self.snap, self.review, self.gallery)

    def test_reject_tampered_manifest(self):
        m = json.loads(self.manifest.read_text()); m['hand_id'] = 'FAKE'
        self.manifest.write_text(json.dumps(m))
        with self.assertRaises(ValueError): g.generate(self.snap, self.review, self.gallery)

    def test_reject_tampered_review(self):
        self.review.write_text(self.review.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'fingerprint'): g.load(self.snap, self.review)

    def test_reject_path_traversal(self):
        m = json.loads(self.manifest.read_text()); m['frames'][0]['file'] = '../secret.png'
        self.manifest.write_text(json.dumps(m))
        with self.assertRaises(ValueError): g.load(self.snap, self.review)

    def test_reject_duplicate_frame(self):
        m = json.loads(self.manifest.read_text()); m['frames'].append(copy.deepcopy(m['frames'][0]))
        self.manifest.write_text(json.dumps(m))
        with self.assertRaises(ValueError): g.load(self.snap, self.review)

    def test_reject_wrong_confirmation_source(self):
        p = self.payload(); p['source_manifest_sha256'] = '0'*64
        self.write(p)
        with self.assertRaises(ValueError): g.verify(self.snap, self.review, self.confirmation)

    def test_reject_swapped_card(self):
        p = self.payload(); p['card_acknowledgements'][0]['card'] = 'Kd'
        self.write(p)
        with self.assertRaises(ValueError): g.verify(self.snap, self.review, self.confirmation)

    def test_reject_unknown_claim(self):
        p = self.payload(); p['ocr_verified'] = True
        self.write(p)
        with self.assertRaises(ValueError): g.verify(self.snap, self.review, self.confirmation)

    def test_reject_symlink_frame(self):
        frame = self.snap / 'frame_00.png'; real = self.root / 'real.png'
        frame.rename(real); frame.symlink_to(real)
        with self.assertRaises(ValueError): g.load(self.snap, self.review)

    def test_reject_overwrite_html(self):
        self.gallery.write_text('existing')
        with self.assertRaises(ValueError): g.generate(self.snap, self.review, self.gallery)

    def test_reject_incomplete_confirmation(self):
        p = self.payload(); p['card_acknowledgements'].pop()
        self.write(p)
        with self.assertRaises(ValueError): g.verify(self.snap, self.review, self.confirmation)

    def test_reject_mismatched_frame_timestamp(self):
        m = json.loads(self.manifest.read_text())
        m['card_frame_links'][0]['requested_clip_timestamp_seconds'] = 1.5
        self.manifest.write_text(json.dumps(m))
        with self.assertRaises(ValueError): g.load(self.snap, self.review)

    def test_reject_missing_notes(self):
        p = self.payload(); p['review_notes'] = 'short'
        self.write(p)
        with self.assertRaises(ValueError): g.verify(self.snap, self.review, self.confirmation)


if __name__ == '__main__': unittest.main()
