"""Synthetic archive integrity and provenance tests; no poker footage used."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import offline_reviewed_clip_gallery as gallery
import offline_session_bundle as bundle


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'clips'
        self.root.mkdir()
        self.target = self.base / 'session.zip'
        (self.root / 'H001.mp4').write_bytes(b'fake synthetic video, no real cards')
        self.clip_hash = gallery.sha(self.root / 'H001.mp4')
        self.source_hash = 'a' * 64
        self.write('manifest.json', {
            'schema_version': 1, 'status': 'human_reviewed_clips_not_verified_hands',
            'source_video_sha256': self.source_hash,
            'automatic_hand_detection': False, 'equity_or_ev_calculated': False,
            'clips': [{'hand_id': 'H001', 'file': 'H001.mp4',
                       'sidecar': 'H001.mp4.json', 'source_table_id': 'table_1',
                       'clip_sha256': self.clip_hash}]})
        self.write('H001.mp4.json', {
            'schema_version': 1, 'analysis_status': 'manually_selected_offline_clip',
            'hand_id': 'H001', 'clip_sha256': self.clip_hash,
            'source_video_sha256': self.source_hash,
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
            'source_clip_sha256': self.clip_hash,
            'source_video_sha256_claim_from_binding': self.source_hash,
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
            'source_clip_sha256': self.clip_hash, 'source_hand_id': 'H001',
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

    def test_round_trip_no_analysis(self):
        result = bundle.export(self.root, self.target)
        self.assertFalse(result['clips'][0]['has_conditional_analysis'])
        self.assertFalse(result['source_video_included'])
        self.assertEqual(bundle.verify(self.target)['source_manifest_sha256'],
                         gallery.sha(self.root / 'manifest.json'))

    def test_round_trip_with_analysis(self):
        self.attach()
        result = bundle.export(self.root, self.target, 'attachments.json')
        self.assertTrue(result['clips'][0]['has_conditional_analysis'])
        with zipfile.ZipFile(self.target) as z:
            self.assertIn('H001.ev.json', z.namelist())
            self.assertIn('index.html', z.namelist())
            self.assertNotIn('source_video.mp4', z.namelist())
            self.assertIn('Ranges e fold são suposições', z.read('index.html').decode())

    def test_no_overwrite(self):
        bundle.export(self.root, self.target)
        with self.assertRaisesRegex(ValueError, 'new ZIP'):
            bundle.export(self.root, self.target)

    def test_destination_inside_root_rejected(self):
        with self.assertRaisesRegex(ValueError, 'new ZIP'):
            bundle.export(self.root, self.root / 'session.zip')

    def test_tampered_clip_rejected_before_export(self):
        (self.root / 'H001.mp4').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'MP4 hash'):
            bundle.export(self.root, self.target)
        self.assertFalse(self.target.exists())

    def test_missing_analysis_pair_rejected(self):
        self.attach()
        (self.root / 'H001.ev.json').unlink()
        with self.assertRaises(ValueError):
            bundle.export(self.root, self.target, 'attachments.json')

    def test_archive_tamper_detected(self):
        bundle.export(self.root, self.target)
        with zipfile.ZipFile(self.target, 'a') as z:
            z.writestr('evil.txt', b'unexpected')
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            bundle.verify(self.target)

    def test_archive_traversal_rejected(self):
        bundle.export(self.root, self.target)
        with zipfile.ZipFile(self.target, 'a') as z:
            z.writestr('../evil.txt', b'evil')
        with self.assertRaisesRegex(ValueError, 'unsafe archive member'):
            bundle.verify(self.target)

    def test_archive_duplicate_rejected(self):
        bundle.export(self.root, self.target)
        with zipfile.ZipFile(self.target, 'a') as z:
            z.writestr('index.html', b'evil')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            bundle.verify(self.target)

    def test_manifest_tamper_detected(self):
        bundle.export(self.root, self.target)
        with zipfile.ZipFile(self.target, 'r') as z:
            content = {name: z.read(name) for name in z.namelist()}
        manifest = json.loads(content['session_bundle_manifest.json'])
        manifest['action_graded'] = True
        content['session_bundle_manifest.json'] = bundle.canonical_json(manifest)
        with zipfile.ZipFile(self.target, 'w') as z:
            for name, data in content.items():
                z.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'unsupported session claims'):
            bundle.verify(self.target)

    def test_inconsistent_clip_inventory_rejected_even_if_manifest_rewritten(self):
        bundle.export(self.root, self.target)
        with zipfile.ZipFile(self.target) as z:
            content = {name: z.read(name) for name in z.namelist()}
        manifest = json.loads(content['session_bundle_manifest.json'])
        manifest['clips'][0]['start_seconds'] = 12
        content['session_bundle_manifest.json'] = bundle.canonical_json(manifest)
        with zipfile.ZipFile(self.target, 'w') as z:
            for name, data in content.items():
                z.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'clip inventory mismatch'):
            bundle.verify(self.target)

    def test_modified_html_with_rehashed_inventory_rejected(self):
        bundle.export(self.root, self.target)
        with zipfile.ZipFile(self.target) as z:
            content = {name: z.read(name) for name in z.namelist()}
        manifest = json.loads(content['session_bundle_manifest.json'])
        content['index.html'] = b'<h1>Fake evaluation</h1>'
        manifest['files']['index.html'] = {
            'sha256': bundle.hash_bytes(content['index.html']),
            'size_bytes': len(content['index.html'])}
        content['session_bundle_manifest.json'] = bundle.canonical_json(manifest)
        with zipfile.ZipFile(self.target, 'w') as z:
            for name, data in content.items():
                z.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'HTML does not match'):
            bundle.verify(self.target)

    def test_symlink_rejected(self):
        (self.root / 'H001.mp4').unlink()
        external = self.base / 'external.mp4'
        external.write_bytes(b'fake synthetic video, no real cards')
        (self.root / 'H001.mp4').symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'linked'):
            bundle.export(self.root, self.target)

    def test_cli_export_verify(self):
        self.assertEqual(bundle.main(['export', str(self.root), str(self.target)]), 0)
        self.assertEqual(bundle.main(['verify', str(self.target)]), 0)


if __name__ == '__main__':
    unittest.main()
