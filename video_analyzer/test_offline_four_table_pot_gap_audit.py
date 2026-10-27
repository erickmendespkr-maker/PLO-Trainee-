"""Synthetic, fail-closed tests for conditional pot arithmetic and provenance."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from offline_four_table_betting_review import make_template, review
from offline_four_table_pot_gap_audit import template, audit
from test_offline_four_table_betting_review import fixture


class PotGapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.audit_file = self.root / 'audit.json'
        self.manual_actions = self.root / 'actions.json'
        self.reviewed = self.root / 'reviewed.json'
        self.manifest = self.root / 'pot-manifest.json'
        self.output = self.root / 'report.json'
        self.audit_file.write_text(json.dumps(fixture()), encoding='utf-8')
        act = make_template(self.audit_file, self.manual_actions)
        act['reviewer_confirmed_offline'] = True
        for item, street, value in zip(act['hands'][0]['actions'],
                                       ('preflop', 'flop', 'turn', 'river'),
                                       ('20.00', None, '45.50', None)):
            item.update(actor='hero', street=street, amount_contributed=value,
                        reviewer_note='Synthetic frame review', human_confirmed=True)
        self.manual_actions.write_text(json.dumps(act), encoding='utf-8')
        review(self.audit_file, self.manual_actions, self.reviewed)
        self.data = template(self.reviewed, self.manifest)
        self.data['reviewer_confirmed_offline'] = True
        self.hand = self.data['hands'][0]
        self.hand['reviewer_notes'] = 'Synthetic manual audit, not verified.'

    def save(self):
        self.manifest.write_text(json.dumps(self.data), encoding='utf-8')

    def run_audit(self, **kwargs):
        self.save()
        return audit(self.reviewed, self.manifest, self.output, **kwargs)

    def rejected(self):
        with self.assertRaises((ValueError, TypeError)):
            self.run_audit()
        self.assertFalse(self.output.exists())

    def test_template_is_unconfirmed(self):
        raw = template(self.reviewed, self.root / 'fresh.json')
        self.assertFalse(raw['reviewer_confirmed_offline'])
        self.assertIsNone(raw['hands'][0]['starting_pot'])
        self.assertFalse(raw['hands'][0]['complete_action_coverage_confirmed'])

    def test_minimal_report_blocks_equity(self):
        r = self.run_audit()
        self.assertFalse(r['ready_for_equity_or_ev'])
        self.assertFalse(r['automatic_clip_selection_authorized'])
        self.assertFalse(r['hands'][0]['pot_accounting_reconciled'])
        self.assertEqual(r['hands'][0]['reviewed_action_contributions'], '65.50')
        self.assertIsNone(r['hands'][0]['conditional_pot_estimate'])
        self.assertEqual(json.loads(self.output.read_text()), r)

    def test_provenance(self):
        r = self.run_audit()
        self.assertEqual(r['source_betting_review_sha256'], hashlib.sha256(self.reviewed.read_bytes()).hexdigest())
        self.assertEqual(r['source_manual_manifest_sha256'], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.assertFalse(r['recording_hash_checked_in_this_run'])

    def test_conditional_arithmetic_equal_still_blocked(self):
        self.hand.update(seat_count=6, starting_pot='0', rake='0', observed_final_pot='85.50',
                         side_pots_declared=False)
        self.hand['forced_contributions'] = [
            {'actor': 'seat_2', 'kind': 'big_blind', 'amount': '20', 'reviewer_note': 'Manual blind'}]
        r = self.run_audit()
        h = r['hands'][0]
        self.assertEqual(h['conditional_pot_estimate'], '85.50')
        self.assertEqual(h['conditional_difference'], '0.00')
        self.assertIn('action_coverage_incomplete', h['blockers'])
        self.assertFalse(h['ready_for_equity_or_ev'])

    def test_conditional_discrepancy_flag(self):
        self.hand.update(starting_pot='0', rake='0', observed_final_pot='70')
        r = self.run_audit()['hands'][0]
        self.assertEqual(r['conditional_difference'], '-4.50')
        self.assertIn('conditional_pot_discrepancy', r['blockers'])

    def test_manual_unobserved_marked_hypothesis(self):
        self.hand['unobserved_contributions'] = [
            {'actor': 'seat_2', 'street': 'turn', 'amount': '20', 'reviewer_note': 'Missing OCR'}]
        r = self.run_audit()['hands'][0]
        self.assertEqual(r['manual_unobserved_contributions'], '20')
        self.assertIn('unobserved_contributions_human_hypotheses', r['blockers'])

    def test_valid_refund_bounded_by_actor_street(self):
        self.hand['returned_uncalled_bets'] = [
            {'actor': 'hero', 'street': 'turn', 'amount': '15', 'reviewer_note': 'Uncalled'}]
        r = self.run_audit()['hands'][0]
        self.assertEqual(r['manual_returned_uncalled_bets'], '15')

    def test_refund_exceeds_actor_contribution(self):
        self.hand['returned_uncalled_bets'] = [
            {'actor': 'hero', 'street': 'turn', 'amount': '46', 'reviewer_note': 'Too high'}]
        self.rejected()

    def test_refund_wrong_street(self):
        self.hand['returned_uncalled_bets'] = [
            {'actor': 'hero', 'street': 'river', 'amount': '1', 'reviewer_note': 'No river bet'}]
        self.rejected()

    def test_rake_exceeds_pot(self):
        self.hand.update(starting_pot='0', rake='100')
        self.rejected()

    def test_duplicate_forced_kind(self):
        entry = {'actor': 'hero', 'kind': 'ante', 'amount': '1', 'reviewer_note': 'Synthetic'}
        self.hand['forced_contributions'] = [entry, copy.deepcopy(entry)]
        self.rejected()

    def test_same_actor_ante_and_blind_allowed(self):
        self.hand['forced_contributions'] = [
            {'actor': 'hero', 'kind': 'ante', 'amount': '1', 'reviewer_note': 'Ante'},
            {'actor': 'hero', 'kind': 'big_blind', 'amount': '2', 'reviewer_note': 'Blind'}]
        self.assertEqual(self.run_audit()['hands'][0]['manual_forced_contributions'], '3')

    def test_seat_out_of_range(self):
        self.hand['seat_count'] = 2
        self.hand['forced_contributions'] = [
            {'actor': 'seat_3', 'kind': 'ante', 'amount': '1', 'reviewer_note': 'Bad seat'}]
        self.rejected()

    def test_seat_count_boolean_rejected(self):
        self.hand['seat_count'] = True
        self.rejected()

    def test_negative_amount_rejected(self):
        self.hand['starting_pot'] = '-1'
        self.rejected()

    def test_extra_precision_rejected(self):
        self.hand['observed_final_pot'] = '1.001'
        self.rejected()

    def test_numeric_amount_rejected(self):
        self.hand['starting_pot'] = 20
        self.rejected()

    def test_missing_attestation(self):
        self.data['reviewer_confirmed_offline'] = False
        self.rejected()

    def test_claim_complete_action_coverage_rejected(self):
        self.hand['complete_action_coverage_confirmed'] = True
        self.rejected()

    def test_unknown_field_rejected(self):
        self.hand['equity'] = 1
        self.rejected()

    def test_swapped_table_rejected(self):
        self.hand['table_id'] = 4
        self.rejected()

    def test_hash_mismatch_rejected(self):
        self.data['source_betting_review_sha256'] = 'b' * 64
        self.rejected()

    def test_existing_output_preserved(self):
        self.output.write_text('existing', encoding='utf-8')
        with self.assertRaises(ValueError): self.run_audit()
        self.assertEqual(self.output.read_text(), 'existing')

    def test_duplicate_json_keys_rejected(self):
        self.manifest.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): audit(self.reviewed, self.manifest, self.output)

    def test_symlink_manifest_rejected(self):
        self.save()
        target = self.root / 'target.json'
        self.manifest.rename(target)
        self.manifest.symlink_to(target)
        with self.assertRaises(ValueError): audit(self.reviewed, self.manifest, self.output)

    def test_recording_hash_mismatch(self):
        self.save()
        recording = self.root / 'video.mp4'
        recording.write_bytes(b'fake')
        with self.assertRaises(ValueError): audit(self.reviewed, self.manifest, self.output, recording_path=recording)

    def test_recording_hash_checked(self):
        recording = self.root / 'video.mp4'
        recording.write_bytes(b'fake')
        data = json.loads(self.reviewed.read_text())
        data['recording_sha256'] = hashlib.sha256(recording.read_bytes()).hexdigest()
        self.reviewed.write_text(json.dumps(data))
        self.data['source_betting_review_sha256'] = hashlib.sha256(self.reviewed.read_bytes()).hexdigest()
        r = self.run_audit(recording_path=recording)
        self.assertTrue(r['recording_hash_checked_in_this_run'])

    def test_upstream_totals_tampering_rejected(self):
        data = json.loads(self.reviewed.read_text())
        data['hands'][0]['human_assigned_contributions_by_street']['turn'] = '100'
        self.reviewed.write_text(json.dumps(data))
        self.data['source_betting_review_sha256'] = hashlib.sha256(self.reviewed.read_bytes()).hexdigest()
        self.rejected()

    def test_upstream_equity_promotion_rejected(self):
        data = json.loads(self.reviewed.read_text())
        data['ready_for_equity_or_ev'] = True
        self.reviewed.write_text(json.dumps(data))
        self.data['source_betting_review_sha256'] = hashlib.sha256(self.reviewed.read_bytes()).hexdigest()
        self.rejected()

    def test_side_pots_flagged(self):
        self.hand['side_pots_declared'] = True
        self.assertIn('side_pot_distribution_unverified', self.run_audit()['hands'][0]['blockers'])

    def test_missing_manual_note(self):
        self.hand['reviewer_notes'] = ' '
        self.rejected()

    def test_manual_entry_missing_note(self):
        self.hand['forced_contributions'] = [
            {'actor': 'hero', 'kind': 'ante', 'amount': '1', 'reviewer_note': ''}]
        self.rejected()

    def test_invalid_forced_kind(self):
        self.hand['forced_contributions'] = [
            {'actor': 'hero', 'kind': 'side_pot', 'amount': '1', 'reviewer_note': 'Invalid'}]
        self.rejected()

    def test_false_numeric_injection(self):
        self.hand['observed_final_pot'] = True
        self.rejected()

    def test_unverified_side_pot_even_when_no_side_pots(self):
        self.hand['side_pots_declared'] = False
        self.assertFalse(self.run_audit()['hands'][0]['pot_accounting_reconciled'])


if __name__ == '__main__':
    unittest.main()
