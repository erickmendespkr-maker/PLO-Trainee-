"""Synthetic, fail-closed tests for unverified OCR hand reconstruction."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_ocr_hand_reconstruction as rec

FIXTURE = Path(__file__).with_name('ledger_fixture.json')


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.ledger = json.loads(FIXTURE.read_text())
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def report(self):
        return rec.build(self.ledger, 'a' * 64)

    def add(self, field, slot, value, hand_id='H1', choice='accepted', correction=None):
        source = next(h for h in self.ledger['hands'] if h['hand_id'] == hand_id)
        row = {'observation_index': len(self.ledger['decisions']), 'hand_id': hand_id,
               'table_id': source['table_id'], 'field': field, 'slot': slot,
               'pts_seconds': 10, 'ocr_suggestion': value,
               'ocr_confidence_raw_uncalibrated': .99,
               'human_selection_unverified': choice,
               'corrected_text_unverified': correction,
               'frame_sha256': 'c' * 64, 'frame_pts_seconds': 10}
        self.ledger['decisions'].append(row)
        if field in ('hero_card', 'board_card') and choice == 'accepted' and len(value) == 2 and value[0] in rec.queue.RANKS and value[1] in rec.queue.SUITS:
            pairs = {(r['field'], r['slot']) for r in self.ledger['decisions']
                     if r['hand_id'] == hand_id and r['field'] in ('hero_card', 'board_card')
                     and r['human_selection_unverified'] == 'accepted'
                     and len(r['ocr_suggestion']) == 2 and r['ocr_suggestion'][0] in rec.queue.RANKS
                     and r['ocr_suggestion'][1] in rec.queue.SUITS}
            source['selected_card_slots_unverified'] = len(pairs)
        return row

    def test_demo_four_hands_blocked(self):
        r = self.report()
        self.assertEqual(r['hand_count'], 4)
        self.assertEqual(r['eligible_for_equity'], 0)
        self.assertTrue(all(not h['math_ready'] for h in r['hands']))

    def test_single_selected_card_has_slot(self):
        h = self.report()['hands'][0]
        self.assertEqual(h['card_candidates_unverified']['hero_card']['0'], ['As'])
        self.assertEqual(h['card_evidence_unverified'][0]['frame_sha256'],
                         self.ledger['decisions'][0]['frame_sha256'])
        self.assertIn('hero_card_count_unknown', h['review_flags'])

    def test_variant_plo5_incomplete(self):
        self.add('variant', None, 'PLO5')
        h = self.report()['hands'][0]
        self.assertEqual(h['expected_hero_cards_if_variant_correct'], 5)
        self.assertIn('incomplete_hero_cards', h['review_flags'])

    def test_variant_plo6_incomplete(self):
        self.add('variant', None, 'PLO6')
        self.assertEqual(self.report()['hands'][0]['expected_hero_cards_if_variant_correct'], 6)

    def test_conflicting_variant(self):
        self.add('variant', None, 'PLO5')
        self.add('variant', None, 'PLO6')
        self.assertIn('conflicting_variant_candidates', self.report()['hands'][0]['review_flags'])

    def test_bad_variant_not_assumed(self):
        self.add('variant', None, 'Holdem')
        self.assertIsNone(self.report()['hands'][0]['variant_candidate_unverified'])

    def test_repeated_card_cross_slots(self):
        self.add('hero_card', 1, 'As')
        self.assertIn('selected_card_repeated_across_slots', self.report()['hands'][0]['review_flags'])

    def test_conflicting_same_slot(self):
        self.add('hero_card', 0, 'Kd')
        self.assertIn('conflicting_selected_slot', self.report()['hands'][0]['review_flags'])

    def test_rejected_candidate_not_selected(self):
        self.add('hero_card', 1, 'Kd', choice='rejected')
        self.assertNotIn('1', self.report()['hands'][0]['card_candidates_unverified']['hero_card'])

    def test_correction_not_promoted(self):
        self.add('hero_card', 1, 'Kd', choice='unknown', correction='Qc')
        h = self.report()['hands'][0]
        self.assertEqual(h['corrections_not_accepted_as_evidence'][0]['candidate_text'], 'Qc')
        self.assertNotIn('1', h['card_candidates_unverified']['hero_card'])

    def test_board_gap(self):
        self.add('board_card', 3, 'Kd')
        self.assertIn('board_street_gap', self.report()['hands'][0]['review_flags'])

    def test_hero_slot_invalid_for_variant(self):
        self.add('variant', None, 'PLO5')
        self.add('hero_card', 5, 'Kd')
        self.assertIn('hero_slot_incompatible_with_variant', self.report()['hands'][0]['review_flags'])

    def test_accepted_action_is_unverified(self):
        self.add('action', None, 'call')
        h = self.report()['hands'][0]
        self.assertEqual(h['other_selected_candidates_unverified']['action'][0]['value'], 'call')
        self.assertFalse(h['eligible_for_equity'])

    def test_accepted_without_frame_rejected(self):
        self.ledger['decisions'][0]['frame_sha256'] = None
        self.ledger['decisions'][0]['frame_pts_seconds'] = None
        with self.assertRaisesRegex(ValueError, 'unbound observation'):
            self.report()

    def test_cross_table_rejected(self):
        self.ledger['decisions'][0]['table_id'] = 'T2'
        with self.assertRaisesRegex(ValueError, 'unbound observation'):
            self.report()

    def test_forged_math_ready_rejected(self):
        self.ledger['hands'][0]['math_ready'] = True
        with self.assertRaisesRegex(ValueError, 'hand record'):
            self.report()

    def test_forged_equity_rejected(self):
        self.ledger['eligible_for_equity'] = 1
        with self.assertRaisesRegex(ValueError, 'unsafe OCR'):
            self.report()

    def test_boolean_equity_rejected(self):
        self.ledger['eligible_for_equity'] = False
        with self.assertRaisesRegex(ValueError, 'unsafe OCR'):
            self.report()

    def test_missing_provenance_rejected(self):
        self.ledger['source_draft_sha256'] = 'not-hash'
        with self.assertRaisesRegex(ValueError, 'unsafe OCR'):
            self.report()

    def test_duplicate_index_rejected(self):
        self.ledger['decisions'][1]['observation_index'] = 0
        with self.assertRaisesRegex(ValueError, 'unbound observation'):
            self.report()

    def test_nonfinite_pts_rejected(self):
        self.ledger['decisions'][0]['pts_seconds'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'unbound observation'):
            self.report()

    def test_summary_mismatch_rejected(self):
        self.ledger['hands'][0]['selected_card_slots_unverified'] = 3
        with self.assertRaisesRegex(ValueError, 'disagree'):
            self.report()

    def test_duplicate_hand_rejected(self):
        self.ledger['hands'][1]['hand_id'] = 'H1'
        with self.assertRaisesRegex(ValueError, 'hand record'):
            self.report()

    def test_cli_new_output_and_no_overwrite(self):
        src, dst = self.root/'ledger.json', self.root/'reconstruction.json'
        src.write_text(json.dumps(self.ledger))
        self.assertEqual(rec.main([str(src), str(dst)]), 0)
        self.assertEqual(json.loads(dst.read_text())['eligible_for_equity'], 0)
        with self.assertRaisesRegex(ValueError, 'new distinct'):
            rec.main([str(src), str(dst)])

    def test_symlink_input_rejected(self):
        src, link, dst = self.root/'source.json', self.root/'alias.json', self.root/'out.json'
        src.write_text(json.dumps(self.ledger))
        link.symlink_to(src)
        with self.assertRaisesRegex(ValueError, 'invalid or oversized input'):
            rec.main([str(link), str(dst)])

    def test_duplicated_json_keys_rejected(self):
        src, dst = self.root/'ledger.json', self.root/'out.json'
        src.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            rec.main([str(src), str(dst)])

    def test_reconstruction_never_has_equity_input(self):
        self.add('variant', None, 'PLO5')
        for slot, card in enumerate(['Kd','Qh','Jc','Tc'], start=1):
            self.add('hero_card', slot, card)
        for slot, card in enumerate(['2c','3d','4h']):
            self.add('board_card', slot, card)
        self.add('action', None, 'call')
        self.add('pot', None, '10')
        h = self.report()['hands'][0]
        self.assertNotIn('incomplete_hero_cards', h['review_flags'])
        self.assertNotIn('incomplete_flop_board', h['review_flags'])
        self.assertFalse(h['math_ready'])
        self.assertNotIn('equity_input', h)


if __name__ == '__main__':
    unittest.main()
