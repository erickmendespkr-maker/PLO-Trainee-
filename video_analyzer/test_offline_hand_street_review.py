"""Synthetic tests for the offline OCR reconstruction review UI (no video)."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_hand_street_review as review


def fixture(variant='PLO5'):
    return {
        'schema_version': 1,
        'status': 'offline_ocr_hand_reconstruction_unverified_not_math_ready',
        'source_ledger_sha256': 'a' * 64,
        'source_video_sha256_claim': 'b' * 64,
        'hand_count': 1, 'eligible_for_equity': 0,
        'equity_or_ev_calculated': False, 'human_review_required': True,
        'original_video_cards_not_independently_verified': True,
        'hands': [{
            'hand_id': 'H1', 'table_id': 'T1', 'math_ready': False,
            'eligible_for_equity': False, 'variant_candidate_unverified': variant,
            'review_flags': ['incomplete_flop_board'],
            'card_candidates_unverified': {'hero_card': {'0': ['As']},
                                           'board_card': {'0': ['2c'], '3': ['Td']}},
            'other_selected_candidates_unverified': {
                'variant': [{'value': 'PLO5', 'pts_seconds': 10}],
                'action': [{'value': 'call', 'pts_seconds': 11}],
                'pot': [], 'stack': []}
        }]
    }


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.source = fixture()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def packet(self):
        return review.worksheet(self.source, 'c' * 64)

    def test_plo5_has_five_hero_slots(self):
        f = self.packet()['hands'][0]['fields']
        self.assertEqual(len([x for x in f if x['field'] == 'hero_card']), 5)

    def test_plo6_has_six_hero_slots(self):
        self.source['hands'][0]['variant_candidate_unverified'] = 'PLO6'
        f = self.packet()['hands'][0]['fields']
        self.assertEqual(len([x for x in f if x['field'] == 'hero_card']), 6)

    def test_unknown_variant_keeps_six_slots(self):
        self.source['hands'][0]['variant_candidate_unverified'] = None
        self.assertEqual(sum(f['field'] == 'hero_card' for f in self.packet()['hands'][0]['fields']), 6)

    def test_street_assignment(self):
        fields = self.packet()['hands'][0]['fields']
        by_slot = {f['slot']: f['street'] for f in fields if f['field'] == 'board_card'}
        self.assertEqual(by_slot, {0:'flop',1:'flop',2:'flop',3:'turn',4:'river'})

    def test_actions_have_unknown_street(self):
        f = self.packet()['hands'][0]['fields']
        self.assertEqual(next(x for x in f if x['field'] == 'action')['street'], 'unknown')

    def test_never_math_ready(self):
        p = self.packet()
        self.assertEqual(p['eligible_for_equity'], 0)
        self.assertFalse(p['hands'][0]['math_ready'])
        self.assertFalse(p['equity_or_ev_calculated'])

    def test_initial_review_status_is_unreviewed(self):
        self.assertTrue(all(f['review_status'] == 'unreviewed' and f['reviewer_value'] is None
                            for f in self.packet()['hands'][0]['fields']))

    def test_source_sha_preserved(self):
        self.assertEqual(self.packet()['source_reconstruction_sha256'], 'c' * 64)

    def test_candidate_not_promoted(self):
        f = self.packet()['hands'][0]['fields'][0]
        self.assertEqual(f['ocr_candidates_unverified'], ['As'])
        self.assertIsNone(f['reviewer_value'])

    def test_multiple_tables(self):
        for n in range(2, 5):
            h = copy.deepcopy(self.source['hands'][0]); h['hand_id'] = 'H' + str(n); h['table_id'] = 'T' + str(n)
            self.source['hands'].append(h)
        self.source['hand_count'] = 4
        self.assertEqual(self.packet()['hand_count'], 4)

    def test_more_than_four_tables_rejected(self):
        for n in range(2, 6):
            h = copy.deepcopy(self.source['hands'][0]); h['hand_id'] = 'H' + str(n); h['table_id'] = 'T' + str(n)
            self.source['hands'].append(h)
        self.source['hand_count'] = 5
        with self.assertRaisesRegex(ValueError, 'four tables'): self.packet()

    def test_duplicate_hand_rejected(self):
        self.source['hands'].append(copy.deepcopy(self.source['hands'][0]))
        self.source['hand_count'] = 2
        with self.assertRaisesRegex(ValueError, 'invalid reconstruction hand'): self.packet()

    def test_forged_math_ready_rejected(self):
        self.source['hands'][0]['math_ready'] = True
        with self.assertRaisesRegex(ValueError, 'invalid reconstruction hand'): self.packet()

    def test_forged_equity_rejected(self):
        self.source['eligible_for_equity'] = 1
        with self.assertRaisesRegex(ValueError, 'unsafe reconstruction'): self.packet()

    def test_boolean_equity_rejected(self):
        self.source['eligible_for_equity'] = False
        with self.assertRaisesRegex(ValueError, 'unsafe reconstruction'): self.packet()

    def test_invalid_card_rejected(self):
        self.source['hands'][0]['card_candidates_unverified']['hero_card']['0'] = ['AX']
        with self.assertRaisesRegex(ValueError, 'invalid card candidate'): self.packet()

    def test_invalid_slot_rejected(self):
        self.source['hands'][0]['card_candidates_unverified']['hero_card']['99'] = ['Kd']
        with self.assertRaisesRegex(ValueError, 'invalid card slots|invalid card candidate'): self.packet()

    def test_bad_sha_rejected(self):
        self.source['source_ledger_sha256'] = 'not-a-hash'
        with self.assertRaisesRegex(ValueError, 'unsafe reconstruction'): self.packet()

    def test_html_escapes_script_termination(self):
        self.source['hands'][0]['review_flags'] = ['</script><img src=x onerror=alert(1)>']
        rendered = review.render(self.packet())
        self.assertNotIn('</script><img', rendered)
        self.assertIn('\\u003c/script\\u003e', rendered)

    def test_html_has_export_and_no_network(self):
        html = review.render(self.packet())
        self.assertIn('id="export"', html)
        self.assertIn('type="application/json"', html)
        self.assertNotIn('fetch(', html)
        self.assertNotIn('https://', html)

    def test_cli_generates_files_and_refuses_overwrite(self):
        source, html, packet = (self.root/x for x in ('source.json','review.html','worksheet.json'))
        source.write_text(json.dumps(self.source))
        self.assertEqual(review.main([str(source), str(html), str(packet)]), 0)
        self.assertEqual(json.loads(packet.read_text())['eligible_for_equity'], 0)
        self.assertIn('Revisão offline', html.read_text())
        with self.assertRaisesRegex(ValueError, 'new, distinct'): review.main([str(source), str(html), str(packet)])

    def test_duplicate_json_key_rejected(self):
        source = self.root/'source.json'; source.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'): review.read(source)

    def test_symlink_input_rejected(self):
        source = self.root/'source.json'; source.write_text(json.dumps(self.source))
        link = self.root/'link.json'; link.symlink_to(source)
        with self.assertRaisesRegex(ValueError, 'invalid or oversized'): review.read(link)

    def test_nonfinite_json_rejected(self):
        source = self.root/'source.json'; source.write_text('{"x":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'): review.read(source)

    def test_same_output_path_rejected(self):
        source = self.root/'source.json'; source.write_text(json.dumps(self.source))
        with self.assertRaisesRegex(ValueError, 'new, distinct'):
            review.main([str(source), str(self.root/'same.html'), str(self.root/'same.html')])


if __name__ == '__main__':
    unittest.main()
