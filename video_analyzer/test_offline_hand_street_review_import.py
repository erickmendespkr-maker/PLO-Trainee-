"""Synthetic contract tests: untrusted browser drafts never become equity inputs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_hand_street_review as review
import offline_hand_street_review_import as importer
from test_offline_hand_street_review import fixture


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reconstruction = self.root / 'reconstruction.json'
        self.worksheet = self.root / 'worksheet.json'
        self.draft = self.root / 'draft.json'
        self.target = self.root / 'ledger.json'
        self.source = fixture()
        self.rewrite()

    def rewrite(self):
        self.reconstruction.write_text(json.dumps(self.source))
        self.packet = review.worksheet(self.source, review.digest(self.reconstruction))
        self.worksheet.write_text(json.dumps(self.packet))
        self.edited = copy.deepcopy(self.packet)
        self.save_draft()

    def save_draft(self):
        self.draft.write_text(json.dumps(self.edited))

    def fields(self, hand=0):
        return self.edited['hands'][hand]['fields']

    def confirm(self, field, value, slot=None, hand=0):
        entry = next(f for f in self.fields(hand) if f['field'] == field and f['slot'] == slot)
        entry['review_status'] = 'confirmed_by_reviewer'
        entry['reviewer_value'] = value
        return entry

    def build(self):
        self.save_draft()
        return importer.build(self.reconstruction, self.worksheet, self.draft)

    def reject(self, msg):
        with self.assertRaisesRegex(ValueError, msg):
            self.build()

    def test_initial_worksheet_all_unreviewed(self):
        out = self.build()
        self.assertEqual(out['reviewer_declarations_unverified'], 0)
        self.assertEqual(out['eligible_for_equity'], 0)
        self.assertFalse(out['hands'][0]['math_ready'])

    def test_claimed_card_is_not_math_ready(self):
        self.confirm('hero_card', 'As', 0)
        out = self.build()
        self.assertEqual(out['reviewer_declarations_unverified'], 1)
        self.assertEqual(out['hands'][0]['fields'][0]['reviewer_value_unverified'], 'As')
        self.assertFalse(out['hands'][0]['eligible_for_equity'])
        self.assertTrue(out['reviewer_claims_not_authenticated'])

    def test_ocr_candidate_membership_not_proof(self):
        self.confirm('hero_card', 'As', 0)
        out = self.build()
        self.assertTrue(out['hands'][0]['fields'][0]['value_present_in_ocr_candidates'])
        self.assertTrue(out['original_video_cards_not_independently_verified'])

    def test_manual_correction_distinct_from_ocr(self):
        self.confirm('hero_card', 'Kd', 0)
        out = self.build()
        self.assertIn('reviewer_value_differs_from_ocr', out['hands'][0]['review_flags'])
        self.assertFalse(out['hands'][0]['fields'][0]['value_present_in_ocr_candidates'])

    def test_unreviewed_field_with_value_rejected(self):
        self.fields()[0]['reviewer_value'] = 'As'
        self.reject('non-confirmed')

    def test_rejected_field_with_value_rejected(self):
        self.fields()[0].update(review_status='rejected', reviewer_value='As')
        self.reject('non-confirmed')

    def test_unknown_field_with_value_rejected(self):
        self.fields()[0].update(review_status='unknown', reviewer_value='As')
        self.reject('non-confirmed')

    def test_rejected_with_null_value_valid(self):
        self.fields()[0]['review_status'] = 'rejected'
        self.assertEqual(self.build()['reviewer_declarations_unverified'], 0)

    def test_unknown_with_null_value_valid(self):
        self.fields()[0]['review_status'] = 'unknown'
        self.assertEqual(self.build()['reviewer_declarations_unverified'], 0)

    def test_invalid_status(self):
        self.fields()[0]['review_status'] = 'verified'
        self.reject('invalid review status')

    def test_status_boolean(self):
        self.fields()[0]['review_status'] = True
        self.reject('invalid review status')

    def test_missing_value_for_confirmation(self):
        self.fields()[0]['review_status'] = 'confirmed_by_reviewer'
        self.reject('invalid reviewer declaration')

    def test_invalid_card_text(self):
        self.confirm('hero_card', 'AX', 0)
        self.reject('invalid reviewer declaration')

    def test_invalid_card_case(self):
        self.confirm('hero_card', 'as', 0)
        self.reject('invalid reviewer declaration')

    def test_invalid_variant(self):
        self.confirm('variant', 'PLO4')
        self.reject('invalid reviewer declaration')

    def test_invalid_negative_pot(self):
        self.confirm('pot', '-10')
        self.reject('invalid reviewer declaration')

    def test_invalid_pot_scientific(self):
        self.confirm('pot', '1e6')
        self.reject('invalid reviewer declaration')

    def test_valid_pot_decimal(self):
        self.confirm('pot', '123.45')
        self.assertEqual(self.build()['reviewer_declarations_unverified'], 1)

    def test_invalid_action_control_char(self):
        self.confirm('action', 'call\nraise')
        self.reject('invalid reviewer declaration')

    def test_action_street_not_verified(self):
        self.confirm('action', 'call')
        self.assertIn('action_street_not_verified', self.build()['hands'][0]['review_flags'])

    def test_duplicate_card_claim(self):
        self.confirm('hero_card', 'As', 0)
        self.confirm('hero_card', 'As', 1)
        self.assertIn('duplicate_card_claim', self.build()['hands'][0]['review_flags'])

    def test_board_street_gap(self):
        self.confirm('board_card', 'Td', 3)
        self.assertIn('board_street_gap', self.build()['hands'][0]['review_flags'])

    def test_partial_flop(self):
        self.confirm('board_card', '2c', 0)
        self.assertIn('partial_flop_claim', self.build()['hands'][0]['review_flags'])

    def test_variant_plo5_incomplete(self):
        self.confirm('variant', 'PLO5')
        self.assertIn('hero_cards_incomplete', self.build()['hands'][0]['review_flags'])

    def test_variant_plo6_incomplete(self):
        self.confirm('variant', 'PLO6')
        self.assertIn('hero_cards_incomplete', self.build()['hands'][0]['review_flags'])

    def test_variant_slot_incompatible(self):
        self.source['hands'][0]['variant_candidate_unverified'] = None
        self.rewrite()
        self.confirm('variant', 'PLO5')
        self.confirm('hero_card', 'As', 5)
        self.assertIn('hero_slot_incompatible_with_variant', self.build()['hands'][0]['review_flags'])

    def test_reconstruction_modified_after_worksheet(self):
        self.source['hands'][0]['review_flags'].append('other')
        self.reconstruction.write_text(json.dumps(self.source))
        self.reject('worksheet does not match')

    def test_forged_worksheet_candidate(self):
        forged = copy.deepcopy(self.packet)
        forged['hands'][0]['fields'][0]['ocr_candidates_unverified'] = ['Kd']
        self.worksheet.write_text(json.dumps(forged))
        self.reject('worksheet does not match')

    def test_forged_worksheet_hash(self):
        forged = copy.deepcopy(self.packet)
        forged['source_reconstruction_sha256'] = 'f' * 64
        self.worksheet.write_text(json.dumps(forged))
        self.reject('worksheet does not match')

    def test_forged_draft_ocr(self):
        self.fields()[0]['ocr_candidates_unverified'] = ['Kd']
        self.reject('immutable OCR field')

    def test_forged_draft_street(self):
        self.fields()[0]['street'] = 'river'
        self.reject('immutable OCR field')

    def test_forged_draft_slot(self):
        self.fields()[0]['slot'] = 2
        self.reject('immutable OCR field')

    def test_forged_draft_hand_identity(self):
        self.edited['hands'][0]['hand_id'] = 'H2'
        self.reject('hand identity')

    def test_forged_draft_source_hash(self):
        self.edited['source_video_sha256_claim'] = 'f' * 64
        self.reject('provenance or metadata')

    def test_forged_math_ready(self):
        self.edited['hands'][0]['math_ready'] = True
        self.reject('hand identity or metadata')

    def test_forged_eligible_for_equity(self):
        self.edited['eligible_for_equity'] = 1
        self.reject('provenance or metadata')

    def test_forged_equity_flag(self):
        self.edited['equity_or_ev_calculated'] = True
        self.reject('provenance or metadata')

    def test_extra_draft_root_field(self):
        self.edited['math_ready'] = True
        self.reject('root fields mismatch')

    def test_extra_field_property(self):
        self.fields()[0]['math_ready'] = True
        self.reject('field keys changed')

    def test_missing_field(self):
        self.fields().pop()
        self.reject('field count changed')

    def test_reordered_fields(self):
        self.fields()[0], self.fields()[1] = self.fields()[1], self.fields()[0]
        self.reject('immutable OCR field')

    def test_duplicate_json_key(self):
        self.draft.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            importer.build(self.reconstruction, self.worksheet, self.draft)

    def test_nonfinite_json(self):
        self.draft.write_text('{"x":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'):
            importer.build(self.reconstruction, self.worksheet, self.draft)

    def test_symlink_draft(self):
        link = self.root/'link.json'
        link.symlink_to(self.draft)
        with self.assertRaisesRegex(ValueError, 'invalid or oversized'):
            importer.build(self.reconstruction, self.worksheet, link)

    def test_cli_output_and_no_overwrite(self):
        self.confirm('hero_card', 'As', 0)
        self.save_draft()
        self.assertEqual(importer.main([str(self.reconstruction), str(self.worksheet), str(self.draft), str(self.target)]), 0)
        out = json.loads(self.target.read_text())
        self.assertEqual(out['source_draft_sha256'], review.digest(self.draft))
        self.assertEqual(out['reviewer_declarations_unverified'], 1)
        self.assertEqual(out['eligible_for_equity'], 0)
        with self.assertRaisesRegex(ValueError, 'new distinct'):
            importer.main([str(self.reconstruction), str(self.worksheet), str(self.draft), str(self.target)])

    def test_cli_source_as_output_rejected(self):
        with self.assertRaisesRegex(ValueError, 'new distinct'):
            importer.main([str(self.reconstruction), str(self.worksheet), str(self.draft), str(self.draft)])

    def test_four_tables(self):
        for i in range(2, 5):
            hand = copy.deepcopy(self.source['hands'][0]); hand['hand_id'] = f'H{i}'; hand['table_id'] = f'T{i}'
            self.source['hands'].append(hand)
        self.source['hand_count'] = 4
        self.rewrite()
        out = self.build()
        self.assertEqual(out['hand_count'], 4)
        self.assertEqual(len({h['table_id'] for h in out['hands']}), 4)
        self.assertEqual(out['eligible_for_equity'], 0)

    def test_large_review_value(self):
        self.confirm('action', 'x' * 81)
        self.reject('invalid reviewer declaration')

    def test_incomplete_pot_stack_flags(self):
        out = self.build()
        self.assertIn('pot_not_confirmed', out['hands'][0]['review_flags'])
        self.assertIn('stack_not_confirmed', out['hands'][0]['review_flags'])

    def test_provenance_chains_preserved(self):
        out = self.build()
        self.assertEqual(out['source_ledger_sha256'], self.source['source_ledger_sha256'])
        self.assertEqual(out['source_video_sha256_claim'], self.source['source_video_sha256_claim'])
        self.assertEqual(out['source_reconstruction_sha256'], review.digest(self.reconstruction))
        self.assertEqual(out['source_worksheet_sha256'], review.digest(self.worksheet))


if __name__ == '__main__':
    unittest.main()
