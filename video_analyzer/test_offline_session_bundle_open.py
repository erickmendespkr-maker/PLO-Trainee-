"""Synthetic tests for verified offline ZIP-to-gallery handoff."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import offline_session_bundle as bundle
import offline_session_bundle_open as opener
import offline_reviewed_clip_gallery as gallery


class UnpackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'clips'
        self.root.mkdir()
        self.zip = self.base / 'session.zip'
        self.dest = self.base / 'opened'
        (self.root / 'H001.mp4').write_bytes(b'synthetic placeholder, not actual poker')
        self.clip_sha = gallery.sha(self.root / 'H001.mp4')
        self.source_sha = 'a' * 64
        self.write('manifest.json', {
            'schema_version': 1, 'status': 'human_reviewed_clips_not_verified_hands',
            'source_video_sha256': self.source_sha,
            'automatic_hand_detection': False, 'equity_or_ev_calculated': False,
            'clips': [{'hand_id': 'H001', 'file': 'H001.mp4',
                       'sidecar': 'H001.mp4.json', 'source_table_id': 'table_1',
                       'clip_sha256': self.clip_sha}]})
        self.write('H001.mp4.json', {
            'schema_version': 1, 'analysis_status': 'manually_selected_offline_clip',
            'hand_id': 'H001', 'clip_sha256': self.clip_sha,
            'source_video_sha256': self.source_sha,
            'video_evidence_verified': False, 'automatic_clip_selection_authorized': False,
            'start_seconds': 1, 'end_seconds': 3,
            'explanation': 'Synthetic review; not a real poker hand.'})

    def write(self, name, obj):
        (self.root / name).write_text(json.dumps(obj), encoding='utf-8')

    def attach(self):
        report = {
            'schema_version': 1,
            'analysis_status': 'offline_conditional_equity_after_human_frame_acknowledgement',
            'human_snapshot_acknowledgement_validated': True,
            'source_clip_sha256': self.clip_sha,
            'source_video_sha256_claim_from_binding': self.source_sha,
            'hand_id': 'H001', 'hero_actor_at_selected_action_verified': False,
            'selected_action_strategic_correctness_verified': False,
            'card_visibility_machine_verified': False,
            'equity_result': {'variant': 'PLO5', 'equity': .375,
                              'hero_cards': ['As', 'Ks', 'Qh', 'Jh', 'Tc'],
                              'board_cards': ['2c', '3d', '4h']}}
        self.write('H001.ack.json', report)
        self.write('H001.ev.json', {
            'schema_version': 1,
            'analysis_status': 'offline_hypothetical_ev_sensitivity_not_an_action_grade',
            'source_acknowledged_report_sha256': gallery.sha(self.root / 'H001.ack.json'),
            'source_clip_sha256': self.clip_sha, 'source_hand_id': 'H001',
            'variant': 'PLO5', 'hero_cards': report['equity_result']['hero_cards'],
            'board_cards': report['equity_result']['board_cards'],
            'action_observed_or_graded': False,
            'range_models_are_reviewer_assumptions': True,
            'fold_probabilities_are_assumptions': True,
            'confidence_intervals_cover_sampling_only': True,
            'hypotheses': [{'label': 'synthetic'}]})
        self.write('attachments.json', {'schema_version': 1, 'analyses': {
            'H001': {'acknowledged_report': 'H001.ack.json',
                     'sensitivity': 'H001.ev.json'}}})

    def test_unpack_no_analysis(self):
        original = bundle.export(self.root, self.zip)
        result = opener.unpack(self.zip, self.dest)
        self.assertEqual(result['clips'], 1)
        self.assertEqual(result['conditional_analyses'], 0)
        self.assertFalse(result['source_video_included'])
        self.assertEqual(bundle.hash_file(self.dest / 'H001.mp4'),
                         original['files']['H001.mp4']['sha256'])
        self.assertIn('Cortes de revisão humana',
                      (self.dest / 'index.html').read_text(encoding='utf-8'))
        self.assertEqual(json.loads((self.dest / bundle.MANIFEST_NAME).read_text()), original)

    def test_unpack_with_conditional_analysis(self):
        self.attach()
        bundle.export(self.root, self.zip, 'attachments.json')
        result = opener.unpack(self.zip, self.dest)
        self.assertEqual(result['conditional_analyses'], 1)
        self.assertTrue((self.dest / 'H001.ack.json').is_file())
        self.assertTrue((self.dest / 'H001.ev.json').is_file())
        self.assertIn('Ranges e fold são suposições',
                      (self.dest / 'index.html').read_text(encoding='utf-8'))

    def test_destination_no_overwrite(self):
        bundle.export(self.root, self.zip)
        self.dest.mkdir()
        (self.dest / 'sentinel.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'new directory'):
            opener.unpack(self.zip, self.dest)
        self.assertEqual((self.dest / 'sentinel.txt').read_text(), 'keep')

    def test_destination_symlink_rejected(self):
        bundle.export(self.root, self.zip)
        self.dest.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'new directory'):
            opener.unpack(self.zip, self.dest)

    def test_source_symlink_rejected(self):
        bundle.export(self.root, self.zip)
        link = self.base / 'link.zip'
        link.symlink_to(self.zip)
        with self.assertRaisesRegex(ValueError, 'regular ZIP'):
            opener.unpack(link, self.dest)

    def test_tampered_archive_does_not_create_destination(self):
        bundle.export(self.root, self.zip)
        with zipfile.ZipFile(self.zip, 'a') as archive:
            archive.writestr('untracked.txt', 'tampered')
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            opener.unpack(self.zip, self.dest)
        self.assertFalse(self.dest.exists())

    def test_rehashed_false_claim_rejected(self):
        bundle.export(self.root, self.zip)
        with zipfile.ZipFile(self.zip) as archive:
            content = {name: archive.read(name) for name in archive.namelist()}
        manifest = json.loads(content[bundle.MANIFEST_NAME])
        manifest['action_graded'] = True
        content[bundle.MANIFEST_NAME] = bundle.canonical_json(manifest)
        with zipfile.ZipFile(self.zip, 'w') as archive:
            for name, data in content.items():
                archive.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'unsupported session claims'):
            opener.unpack(self.zip, self.dest)
        self.assertFalse(self.dest.exists())

    def test_bad_source_and_missing_parent(self):
        with self.assertRaisesRegex(ValueError, 'regular ZIP'):
            opener.unpack(self.root / 'missing.zip', self.dest)
        bundle.export(self.root, self.zip)
        with self.assertRaisesRegex(ValueError, 'new directory'):
            opener.unpack(self.zip, self.base / 'missing' / 'opened')

    def test_cli(self):
        bundle.export(self.root, self.zip)
        self.assertEqual(opener.main([str(self.zip), str(self.dest)]), 0)
        self.assertTrue((self.dest / 'index.html').exists())

    def test_no_unverified_extraction_on_zip_traversal(self):
        bundle.export(self.root, self.zip)
        with zipfile.ZipFile(self.zip, 'a') as archive:
            archive.writestr('../escape.txt', 'danger')
        with self.assertRaisesRegex(ValueError, 'unsafe archive member'):
            opener.unpack(self.zip, self.dest)
        self.assertFalse((self.base / 'escape.txt').exists())
        self.assertFalse(self.dest.exists())


if __name__ == '__main__':
    unittest.main()
