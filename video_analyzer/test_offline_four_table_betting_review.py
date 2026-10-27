"""Offline synthetic tests for conservative manual action-review boundary."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_four_table_betting_review import make_template, review

H = 'a' * 64


def fixture():
    return {
        'schema_version': 1, 'analysis_status': 'offline_action_street_candidates_only',
        'source_hand_candidates_sha256': H, 'recording_sha256': H,
        'recording_hash_checked_in_this_run': False,
        'hands': [{
            'hand_id': 'hand1', 'table_id': 1, 'declared_game_type': 'PLO5',
            'board_snapshots': [], 'observed_amounts': [], 'review_flags': [],
            'observed_action_labels': [
                {'source_observation_index': 1, 'pts_seconds': 2.0, 'action_label': 'call',
                 'street_candidate': None, 'actor': None, 'amount': None,
                 'action_sequence_confirmed': False},
                {'source_observation_index': 4, 'pts_seconds': 6.0, 'action_label': 'check',
                 'street_candidate': 'flop_candidate', 'actor': None, 'amount': None,
                 'action_sequence_confirmed': False},
                {'source_observation_index': 6, 'pts_seconds': 9.0, 'action_label': 'bet',
                 'street_candidate': 'turn_candidate', 'actor': None, 'amount': None,
                 'action_sequence_confirmed': False},
                {'source_observation_index': 8, 'pts_seconds': 12.0, 'action_label': 'fold',
                 'street_candidate': 'river_candidate', 'actor': None, 'amount': None,
                 'action_sequence_confirmed': False}],
            'action_history_complete': False, 'opponent_ranges_known': False,
            'ready_for_equity_or_ev': False,
            'status': 'street_candidates_only_requires_human_action_reconstruction'}],
        'complete_hand_reconstructed': False, 'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False, 'warning': 'synthetic'}


class BettingReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audit = self.root / 'audit.json'
        self.manifest = self.root / 'review.json'
        self.output = self.root / 'result.json'
        self.data = fixture()
        self.audit.write_text(json.dumps(self.data), encoding='utf-8')
        self.template = make_template(self.audit, self.manifest)
        self.template['reviewer_confirmed_offline'] = True
        for action, street, amount in zip(self.template['hands'][0]['actions'],
                                          ('preflop', 'flop', 'turn', 'river'),
                                          ('20.00', None, '45.50', None)):
            action.update(actor='hero', street=street, amount_contributed=amount,
                          reviewer_note='Checked against synthetic frame', human_confirmed=True)

    def write(self):
        self.manifest.write_text(json.dumps(self.template), encoding='utf-8')

    def run_review(self, **kwargs):
        self.write()
        return review(self.audit, self.manifest, self.output, **kwargs)

    def invalid(self):
        with self.assertRaises(ValueError):
            self.run_review()
        self.assertFalse(self.output.exists())

    def test_template_unconfirmed(self):
        template = make_template(self.audit, self.root / 'blank.json')
        self.assertFalse(template['reviewer_confirmed_offline'])
        self.assertFalse(template['hands'][0]['actions'][0]['human_confirmed'])
        self.assertIsNone(template['hands'][0]['actions'][0]['actor'])

    def test_review_keeps_math_blocked(self):
        result = self.run_review()
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['complete_hand_reconstructed'])
        self.assertEqual(result['hands'][0]['human_assigned_contributions_by_street']['turn'], '45.50')
        self.assertEqual(json.loads(self.output.read_text()), result)

    def test_provenance(self):
        result = self.run_review()
        self.assertEqual(result['source_action_audit_sha256'], hashlib.sha256(self.audit.read_bytes()).hexdigest())
        self.assertEqual(result['source_human_review_sha256'], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.assertFalse(result['recording_hash_checked_in_this_run'])

    def test_manual_only_street_flag(self):
        result = self.run_review()
        self.assertIn('street_supported_only_by_human_review',
                      [x['code'] for x in result['hands'][0]['review_flags']])

    def test_audit_visual_flags_preserved_as_warning(self):
        self.data['hands'][0]['review_flags'].append({'code': 'board_changed_not_prefix', 'pts_seconds': 3.0})
        self.audit.write_text(json.dumps(self.data))
        self.template['source_action_audit_sha256'] = hashlib.sha256(self.audit.read_bytes()).hexdigest()
        result = self.run_review()
        self.assertIn('upstream_visual_review_flags_remain',
                      [x['code'] for x in result['hands'][0]['review_flags']])

    def test_missing_confirmation(self):
        self.template['hands'][0]['actions'][0]['human_confirmed'] = False
        self.invalid()

    def test_missing_reviewer_attestation(self):
        self.template['reviewer_confirmed_offline'] = False
        self.invalid()

    def test_actor_invalid(self):
        self.template['hands'][0]['actions'][0]['actor'] = 'opponent'; self.invalid()

    def test_reviewer_note_required(self):
        self.template['hands'][0]['actions'][0]['reviewer_note'] = ' '; self.invalid()

    def test_mismatched_audit_hash(self):
        self.template['source_action_audit_sha256'] = 'b' * 64; self.invalid()

    def test_reviewed_street_conflict(self):
        self.template['hands'][0]['actions'][1]['street'] = 'turn'; self.invalid()

    def test_street_reversal(self):
        self.template['hands'][0]['actions'][0]['street'] = 'river'; self.invalid()

    def test_fold_cannot_contribute(self):
        self.template['hands'][0]['actions'][3]['amount_contributed'] = '1'; self.invalid()

    def test_check_cannot_contribute(self):
        self.template['hands'][0]['actions'][1]['amount_contributed'] = '1'; self.invalid()

    def test_bet_must_contribute(self):
        self.template['hands'][0]['actions'][2]['amount_contributed'] = None; self.invalid()

    def test_zero_call_rejected(self):
        self.template['hands'][0]['actions'][0]['amount_contributed'] = '0'; self.invalid()

    def test_negative_bet_rejected(self):
        self.template['hands'][0]['actions'][2]['amount_contributed'] = '-1'; self.invalid()

    def test_excessive_decimal_places_rejected(self):
        self.template['hands'][0]['actions'][2]['amount_contributed'] = '1.001'; self.invalid()

    def test_swapped_action_ids_rejected(self):
        a = self.template['hands'][0]['actions']
        a[0]['source_observation_index'], a[1]['source_observation_index'] = a[1]['source_observation_index'], a[0]['source_observation_index']
        self.invalid()

    def test_action_omission_rejected(self):
        self.template['hands'][0]['actions'].pop(); self.invalid()

    def test_full_history_claim_rejected(self):
        self.template['hands'][0]['complete_action_sequence_claimed'] = True; self.invalid()

    def test_unknown_field_rejected(self):
        self.template['hands'][0]['actions'][0]['equity'] = 1; self.invalid()

    def test_bad_table_rejected(self):
        self.template['hands'][0]['table_id'] = 2; self.invalid()

    def test_existing_output_preserved(self):
        self.output.write_text('keep')
        with self.assertRaises(ValueError): self.run_review()
        self.assertEqual(self.output.read_text(), 'keep')

    def test_symlink_manifest_rejected(self):
        self.write()
        other = self.root / 'other.json'
        self.manifest.rename(other)
        self.manifest.symlink_to(other)
        with self.assertRaises(ValueError): review(self.audit, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_json_key_rejected(self):
        self.manifest.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): review(self.audit, self.manifest, self.output)

    def test_recording_hash_mismatch(self):
        video = self.root / 'recording.mp4'
        video.write_bytes(b'video')
        with self.assertRaises(ValueError): self.run_review(recording_path=video)

    def test_recording_hash_checked(self):
        video = self.root / 'recording.mp4'
        video.write_bytes(b'video')
        self.data['recording_sha256'] = hashlib.sha256(video.read_bytes()).hexdigest()
        self.audit.write_text(json.dumps(self.data))
        self.template['source_action_audit_sha256'] = hashlib.sha256(self.audit.read_bytes()).hexdigest()
        self.assertTrue(self.run_review(recording_path=video)['recording_hash_checked_in_this_run'])

    def test_second_table_kept_separate(self):
        h2 = copy.deepcopy(self.data['hands'][0])
        h2['hand_id'] = 'hand2'; h2['table_id'] = 2
        for a in h2['observed_action_labels']:
            a['source_observation_index'] += 12
        self.data['hands'].append(h2)
        self.audit.write_text(json.dumps(self.data))
        t = make_template(self.audit, self.root / 'two.json')
        second = copy.deepcopy(self.template['hands'][0])
        second['hand_id'] = 'hand2'; second['table_id'] = 2
        for a in second['actions']:
            a['source_observation_index'] += 12
        self.template['hands'].append(second)
        self.template['source_action_audit_sha256'] = hashlib.sha256(self.audit.read_bytes()).hexdigest()
        result = self.run_review()
        self.assertEqual([h['table_id'] for h in result['hands']], [1, 2])

    def test_upstream_math_promotion_rejected(self):
        self.data['ready_for_equity_or_ev'] = True
        self.audit.write_text(json.dumps(self.data))
        self.template['source_action_audit_sha256'] = hashlib.sha256(self.audit.read_bytes()).hexdigest()
        self.invalid()

    def test_upstream_actor_injection_rejected(self):
        self.data['hands'][0]['observed_action_labels'][0]['actor'] = 'hero'
        self.audit.write_text(json.dumps(self.data))
        self.template['source_action_audit_sha256'] = hashlib.sha256(self.audit.read_bytes()).hexdigest()
        self.invalid()

    def test_boolean_source_index_rejected(self):
        self.data['hands'][0]['observed_action_labels'][0]['source_observation_index'] = True
        self.audit.write_text(json.dumps(self.data))
        self.template['source_action_audit_sha256'] = hashlib.sha256(self.audit.read_bytes()).hexdigest()
        self.invalid()


if __name__ == '__main__':
    unittest.main()
