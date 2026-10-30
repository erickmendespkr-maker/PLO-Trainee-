"""Synthetic, deterministic tests for reviewed-clip attachment discovery."""
import json
from pathlib import Path
import tempfile
import unittest

import offline_gallery_attachment_index as adapter
import offline_reviewed_clip_gallery as gallery


class AttachmentIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'H001.mp4').write_bytes(b'synthetic clip bytes')
        self.source_sha = 'a' * 64
        self.clip_sha = gallery.sha(self.root / 'H001.mp4')
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
            'explanation': 'Revisão sintética sem observação real.'})

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding='utf-8')

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
            'equity_result': {'variant': 'PLO5', 'equity': 0.375,
                              'hero_cards': ['As', 'Ks', 'Qh', 'Jh', 'Tc'],
                              'board_cards': ['2c', '3d', '4h']}}
        self.write('H001.ack.json', report)
        self.write('H001.ev.json', {
            'schema_version': 1,
            'analysis_status': 'offline_hypothetical_ev_sensitivity_not_an_action_grade',
            'source_acknowledged_report_sha256': gallery.sha(self.root/'H001.ack.json'),
            'source_clip_sha256': self.clip_sha, 'source_hand_id': 'H001',
            'variant': 'PLO5', 'hero_cards': report['equity_result']['hero_cards'],
            'board_cards': report['equity_result']['board_cards'],
            'action_observed_or_graded': False,
            'range_models_are_reviewer_assumptions': True,
            'fold_probabilities_are_assumptions': True,
            'confidence_intervals_cover_sampling_only': True,
            'hypotheses': [{'label': 'synthetic'}]})

    def test_empty_is_explicit_no_analysis(self):
        self.assertEqual(adapter.build(self.root)['analyses'], {})

    def test_attaches_matching_pair(self):
        self.attach()
        index = adapter.build(self.root)
        self.assertEqual(index['analyses']['H001']['sensitivity'], 'H001.ev.json')
        self.assertEqual(adapter.main([str(self.root), str(self.root/'auto.json')]), 0)
        result = gallery.build(self.root, 'auto.json')
        self.assertEqual(result['clips'][0]['analysis']['equity'], .375)
        self.assertFalse(result['action_graded'])

    def test_no_overwrite(self):
        self.attach()
        path = self.root/'auto.json'
        adapter.main([str(self.root), str(path)])
        with self.assertRaisesRegex(ValueError, 'new JSON'):
            adapter.main([str(self.root), str(path)])

    def test_missing_sensitivity_fails_closed(self):
        self.attach()
        (self.root/'H001.ev.json').unlink()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            adapter.build(self.root)

    def test_mismatched_clip_fails_closed(self):
        self.attach()
        p = self.root/'H001.ack.json'
        report = json.loads(p.read_text())
        report['source_clip_sha256'] = 'f' * 64
        self.write('H001.ack.json', report)
        with self.assertRaisesRegex(ValueError, 'unbound'):
            adapter.build(self.root)

    def test_modified_ev_hash_fails_closed(self):
        self.attach()
        p = self.root/'H001.ack.json'
        report = json.loads(p.read_text())
        report['equity_result']['equity'] = .25
        self.write('H001.ack.json', report)
        with self.assertRaisesRegex(ValueError, 'unbound'):
            adapter.build(self.root)

    def test_symlink_rejected(self):
        self.attach()
        (self.root/'H001.ev.json').unlink()
        (self.root/'H001.ev.json').symlink_to(self.root/'H001.ack.json')
        with self.assertRaisesRegex(ValueError, 'linked'):
            adapter.build(self.root)

    def test_clip_tampering_rejected(self):
        self.attach()
        with (self.root/'H001.mp4').open('ab') as f:
            f.write(b'altered')
        with self.assertRaisesRegex(ValueError, 'MP4 hash'):
            adapter.build(self.root)

    def test_unsafe_claim_rejected(self):
        self.attach()
        p = self.root/'H001.ev.json'
        ev = json.loads(p.read_text())
        ev['action_observed_or_graded'] = True
        self.write('H001.ev.json', ev)
        with self.assertRaisesRegex(ValueError, 'unbound'):
            adapter.build(self.root)


if __name__ == '__main__':
    unittest.main()
