"""Synthetic regression tests; no real poker content is asserted or recognized."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import offline_reviewed_clip_gallery as gallery


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        clip = self.root / 'H001.mp4'
        clip.write_bytes(b'synthetic placeholder, not a real poker recording')
        source_sha = 'a'*64
        self.manifest = self.root / 'manifest.json'
        self.sidecar = self.root / 'H001.mp4.json'
        self.write(self.manifest, {
            'schema_version': 1,
            'status': 'human_reviewed_clips_not_verified_hands',
            'source_video_sha256': source_sha,
            'automatic_hand_detection': False,
            'equity_or_ev_calculated': False,
            'clips': [{'hand_id': 'H001', 'file': 'H001.mp4',
                       'sidecar': 'H001.mp4.json', 'source_table_id': 'table_1',
                       'clip_sha256': gallery.sha(clip)}]})
        self.write(self.sidecar, {
            'schema_version': 1, 'analysis_status': 'manually_selected_offline_clip',
            'hand_id': 'H001', 'clip_sha256': gallery.sha(clip),
            'source_video_sha256': source_sha,
            'video_evidence_verified': False,
            'automatic_clip_selection_authorized': False,
            'start_seconds': 1.2, 'end_seconds': 3.4,
            'explanation': 'Revisor selecionou intervalo sintético; nenhuma carta confirmada.'})

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def change(self, path, fn):
        data = json.loads(path.read_text())
        fn(data)
        self.write(path, data)

    def attachments(self):
        m = json.loads(self.manifest.read_text())
        clip_sha = m['clips'][0]['clip_sha256']
        hand = 'H001'
        report = {
            'schema_version': 1,
            'analysis_status': 'offline_conditional_equity_after_human_frame_acknowledgement',
            'human_snapshot_acknowledgement_validated': True,
            'source_clip_sha256': clip_sha,
            'source_video_sha256_claim_from_binding': m['source_video_sha256'],
            'hand_id': hand,
            'hero_actor_at_selected_action_verified': False,
            'selected_action_strategic_correctness_verified': False,
            'card_visibility_machine_verified': False,
            'equity_result': {'variant': 'PLO5', 'equity': .375,
                              'hero_cards': ['As','Ks','Qh','Jh','Tc'],
                              'board_cards': ['2c','3d','4h']}}
        self.write(self.root / 'H001.ack.json', report)
        sensitivity = {
            'schema_version': 1,
            'analysis_status': 'offline_hypothetical_ev_sensitivity_not_an_action_grade',
            'source_acknowledged_report_sha256': gallery.sha(self.root / 'H001.ack.json'),
            'source_clip_sha256': clip_sha,
            'source_hand_id': hand,
            'variant': 'PLO5',
            'hero_cards': report['equity_result']['hero_cards'],
            'board_cards': report['equity_result']['board_cards'],
            'action_observed_or_graded': False,
            'range_models_are_reviewer_assumptions': True,
            'fold_probabilities_are_assumptions': True,
            'confidence_intervals_cover_sampling_only': True,
            'hypotheses': [{'label': 'synthetic only'}]}
        self.write(self.root / 'H001.ev.json', sensitivity)
        self.write(self.root / 'attachments.json', {
            'schema_version': 1,
            'analyses': {hand: {'acknowledged_report': 'H001.ack.json',
                                'sensitivity': 'H001.ev.json'}}})

    def test_original_fixture_hash_and_gallery(self):
        result = gallery.build(self.root)
        self.assertEqual(len(result['clips']), 1)
        self.assertIsNone(result['clips'][0]['analysis'])
        self.assertFalse(result['action_graded'])
        html = gallery.render(result)
        self.assertIn('H001.mp4', html)
        self.assertIn('Sem análise matemática', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('https://', html)

    def test_cli_output_no_overwrite(self):
        dest = self.root / 'index.html'
        self.assertEqual(gallery.main([str(self.root), str(dest)]), 0)
        self.assertTrue(dest.is_file())
        with self.assertRaisesRegex(ValueError, 'new HTML'):
            gallery.main([str(self.root), str(dest)])

    def test_tampered_clip_rejected(self):
        with (self.root / 'H001.mp4').open('ab') as f:
            f.write(b'tamper')
        with self.assertRaisesRegex(ValueError, 'MP4 hash mismatch'):
            gallery.build(self.root)

    def test_tampered_sidecar_rejected(self):
        self.change(self.sidecar, lambda d: d.update({'clip_sha256': 'a'*64}))
        with self.assertRaisesRegex(ValueError, 'invalid clip sidecar'):
            gallery.build(self.root)

    def test_sidecar_unsafe_claim_rejected(self):
        self.change(self.sidecar, lambda d: d.update({'video_evidence_verified': True}))
        with self.assertRaisesRegex(ValueError, 'invalid clip sidecar'):
            gallery.build(self.root)

    def test_manifest_unsafe_claim_rejected(self):
        self.change(self.manifest, lambda d: d.update({'automatic_hand_detection': True}))
        with self.assertRaisesRegex(ValueError, 'invalid clip manifest'):
            gallery.build(self.root)

    def test_manifest_path_traversal_rejected(self):
        self.change(self.manifest, lambda d: d['clips'][0].update({'file': '../H001.mp4'}))
        with self.assertRaisesRegex(ValueError, 'unsafe clip declaration'):
            gallery.build(self.root)

    def test_duplicate_hand_rejected(self):
        self.change(self.manifest, lambda d: d['clips'].append(copy.deepcopy(d['clips'][0])))
        with self.assertRaisesRegex(ValueError, 'repeated hand ID'):
            gallery.build(self.root)

    def test_html_escapes_human_text(self):
        self.change(self.sidecar, lambda d: d.update({'explanation': '<img src=x onerror=alert(1)> &'}))
        html = gallery.render(gallery.build(self.root))
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)

    def test_attached_conditional_math(self):
        self.attachments()
        result = gallery.build(self.root, 'attachments.json')
        self.assertEqual(result['clips'][0]['analysis']['equity'], .375)
        self.assertIn('37.50%', gallery.render(result))
        self.assertIn('não é nota da jogada', gallery.render(result).lower())

    def test_wrong_acknowledged_clip_hash_rejected(self):
        self.attachments()
        self.change(self.root/'H001.ack.json', lambda d: d.update({'source_clip_sha256': 'a'*64}))
        with self.assertRaisesRegex(ValueError, 'unbound'):
            gallery.build(self.root, 'attachments.json')

    def test_wrong_video_hash_rejected(self):
        self.attachments()
        self.change(self.root/'H001.ack.json', lambda d: d.update({'source_video_sha256_claim_from_binding': 'b'*64}))
        with self.assertRaisesRegex(ValueError, 'unbound'):
            gallery.build(self.root, 'attachments.json')

    def test_wrong_sensitivity_report_digest_rejected(self):
        self.attachments()
        self.change(self.root/'H001.ack.json', lambda d: d.update({'equity_result': {**d['equity_result'], 'equity': .4}}))
        with self.assertRaisesRegex(ValueError, 'unbound or overstated'):
            gallery.build(self.root, 'attachments.json')

    def test_sensitivity_action_grade_rejected(self):
        self.attachments()
        self.change(self.root/'H001.ev.json', lambda d: d.update({'action_observed_or_graded': True}))
        with self.assertRaisesRegex(ValueError, 'unbound or overstated'):
            gallery.build(self.root, 'attachments.json')

    def test_sensitivity_cards_mismatch_rejected(self):
        self.attachments()
        self.change(self.root/'H001.ev.json', lambda d: d.update({'hero_cards': ['2h']}))
        with self.assertRaisesRegex(ValueError, 'unbound or overstated'):
            gallery.build(self.root, 'attachments.json')

    def test_attachment_path_traversal_rejected(self):
        self.attachments()
        self.change(self.root/'attachments.json', lambda d: d['analyses']['H001'].update({'sensitivity': '../other.json'}))
        with self.assertRaisesRegex(ValueError, 'unsafe file name'):
            gallery.build(self.root, 'attachments.json')

    def test_unknown_hand_attachment_rejected(self):
        self.attachments()
        self.change(self.root/'attachments.json', lambda d: d['analyses'].update({'OTHER': d['analyses']['H001']}))
        with self.assertRaisesRegex(ValueError, 'invalid attachment index'):
            gallery.build(self.root, 'attachments.json')

    def test_symlink_mp4_rejected(self):
        video = self.root / 'H001.mp4'
        target = self.root / 'video.bin'
        video.rename(target)
        try:
            video.symlink_to(target)
        except OSError:
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'linked file'):
            gallery.build(self.root)


if __name__ == '__main__':
    unittest.main()
