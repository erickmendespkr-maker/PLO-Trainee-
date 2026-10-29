"""Synthetic tests for local frame gallery and human acknowledgement validation."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import offline_audited_card_gallery as g

DEMO = Path(__file__).resolve().parents[1] / 'demo'


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snap = self.root / 'frames'
        shutil.copytree(DEMO / 'frame_audit', self.snap)
        self.review = self.root / 'review.json'
        shutil.copyfile(DEMO / 'browser_review.json', self.review)
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
        self.assertEqual(r['acknowledged_cards'], 11)
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
