"""Synthetic tests: handoff must not promote OCR or manual edits to EV facts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_review_handoff import build_handoff, write_handoff, main
from activity_review_packet import build_review_packet
from activity_snapshot_chain import build_activity_snapshot_queue
from test_activity_snapshot_chain import fixture


class ReviewHandoffTests(unittest.TestCase):
    def setUp(self):
        self.queue = build_activity_snapshot_queue(fixture())
        self.draft = build_review_packet(self.queue)['template']
        self.draft['analysis_status'] = 'manual_review_draft_unverified_no_ev'

    def confirm(self, field, value, entry=0, pts=1):
        self.draft['entries'][entry]['reviewed_fields'][field].update(
            value=value, confidence=.87, source_timestamp=pts,
            source='manual frame check', human_confirmed=True)

    def test_four_tables_all_blocked(self):
        report = build_handoff(self.queue, self.draft)
        self.assertEqual(report['summary'], {'total_decisions': 4,
            'all_fields_human_attested': 0, 'ev_authorized': 0})
        self.assertEqual({d['table_id'] for d in report['decisions']}, {1, 2, 3, 4})
        self.assertTrue(all(not d['ready_for_equity_or_ev'] for d in report['decisions']))

    def test_unconfirmed_ocr_values_never_promoted(self):
        self.draft['entries'][0]['reviewed_fields']['hero_cards']['value'] = ['As','Ks','2d','3c','4h']
        decision = build_handoff(self.queue, self.draft)['decisions'][0]
        self.assertIsNone(decision['model_inputs']['hero_cards'])
        self.assertIn('field_not_human_confirmed:hero_cards', decision['blockers'])

    def test_confirmed_field_retains_timestamp_confidence_and_provenance(self):
        self.confirm('hero_cards', ['As','Ks','2d','3c','4h'])
        decision = build_handoff(self.queue, self.draft)['decisions'][0]
        self.assertEqual(decision['model_inputs']['hero_cards'], ['As','Ks','2d','3c','4h'])
        self.assertEqual(decision['minimum_attested_field_confidence'], .87)
        self.assertEqual(decision['human_attested_fields']['hero_cards']['source_timestamp'], 1)
        self.assertFalse(decision['human_attested_fields']['hero_cards']['video_verified'])
        self.assertIsNone(decision['model_inputs']['board'])

    def test_all_fields_attested_still_blocked(self):
        self.confirm('hero_cards', ['As','Ks','2d','3c','4h'])
        self.confirm('board', ['Qs','Jd','Tc'])
        self.confirm('observed_action', 'call')
        self.confirm('pot_before_action', 20)
        self.confirm('call_amount', 5)
        report = build_handoff(self.queue, self.draft)
        self.assertEqual(report['summary']['all_fields_human_attested'], 1)
        self.assertEqual(report['summary']['ev_authorized'], 0)
        decision = report['decisions'][0]
        self.assertEqual(decision['confirmed_field_count'], 5)
        self.assertFalse(decision['ready_for_equity_or_ev'])
        self.assertIsNone(decision['opponent_range'])
        self.assertIsNone(decision['fold_probability'])
        self.assertIn('opponent_range_not_supplied_or_validated', decision['blockers'])

    def test_reject_future_timestamp(self):
        self.confirm('hero_cards', ['As','Ks','2d','3c','4h'], pts=999)
        with self.assertRaises(ValueError): build_handoff(self.queue, self.draft)

    def test_reject_replayed_queue(self):
        other = copy.deepcopy(self.queue)
        other['tasks'][0]['hand_id'] = 'different'
        with self.assertRaises(ValueError): build_handoff(other, self.draft)

    def test_reject_attempt_to_enable_ev(self):
        self.draft['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError): build_handoff(self.queue, self.draft)

    def test_reject_duplicate_cards(self):
        self.confirm('hero_cards', ['As','Ks','2d','3c','4h'])
        self.confirm('board', ['As','Jd','Tc'])
        with self.assertRaises(ValueError): build_handoff(self.queue, self.draft)

    def test_reject_extra_unexpected_field(self):
        self.draft['entries'][0]['reviewed_fields']['new_field'] = {}
        with self.assertRaises(ValueError): build_handoff(self.queue, self.draft)

    def test_digest_changes_on_edit(self):
        first = build_handoff(self.queue, self.draft)
        self.draft['entries'][0]['reviewer_notes'] = 'check video again'
        second = build_handoff(self.queue, self.draft)
        self.assertNotEqual(first['source_draft_sha256'], second['source_draft_sha256'])
        self.assertEqual(first['source_queue_sha256'], second['source_queue_sha256'])

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            queue, draft, out = (root / p for p in ('queue.json','draft.json','handoff.json'))
            queue.write_text(json.dumps(self.queue))
            draft.write_text(json.dumps(self.draft))
            self.assertEqual(main([str(queue), str(draft), str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())['summary']['total_decisions'], 4)
            with self.assertRaises(ValueError): write_handoff(queue, draft, out)
            with self.assertRaises(ValueError): write_handoff(queue, draft, queue)

    def test_invalid_draft_creates_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            queue, draft, out = (root / p for p in ('queue.json','draft.json','handoff.json'))
            queue.write_text(json.dumps(self.queue))
            self.draft['entries'][0]['human_confirmed'] = True
            draft.write_text(json.dumps(self.draft))
            with self.assertRaises(ValueError): write_handoff(queue, draft, out)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
