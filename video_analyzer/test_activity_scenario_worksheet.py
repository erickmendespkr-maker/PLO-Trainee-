"""Synthetic-only checks for a fail-closed mathematical review worksheet."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_review_handoff import build_handoff
from activity_review_packet import build_review_packet
from activity_snapshot_chain import build_activity_snapshot_queue
from activity_scenario_worksheet import build_scenario_worksheet, main
from test_activity_snapshot_chain import fixture


class ScenarioWorksheetTests(unittest.TestCase):
    def setUp(self):
        self.queue = build_activity_snapshot_queue(fixture())
        draft = build_review_packet(self.queue)['template']
        draft['analysis_status'] = 'manual_review_draft_unverified_no_ev'
        self.handoff = build_handoff(self.queue, draft)

    def test_four_tables_and_no_automatic_analysis(self):
        result = build_scenario_worksheet(self.handoff)
        self.assertEqual(len(result['scenarios']), 4)
        self.assertEqual({d['table_id'] for d in result['scenarios']}, {1, 2, 3, 4})
        self.assertFalse(result['ready_for_equity_or_ev'])
        for decision in result['scenarios']:
            self.assertFalse(decision['ready_for_equity_or_ev'])
            self.assertIsNone(decision['opponent_range'])
            self.assertIsNone(decision['fold_probability'])
            self.assertEqual(len(decision['unconfirmed_fields']), 5)

    def test_confirmed_fields_preserved_but_not_approved(self):
        draft = build_review_packet(self.queue)['template']
        draft['analysis_status'] = 'manual_review_draft_unverified_no_ev'
        draft['entries'][0]['reviewed_fields']['hero_cards'].update(
            value=['As', 'Ks', '2d', '3c', '4h'], confidence=.9,
            source_timestamp=1, source='manual check', human_confirmed=True)
        report = build_scenario_worksheet(build_handoff(self.queue, draft))
        decision = report['scenarios'][0]
        self.assertEqual(decision['reviewed_visible_inputs']['hero_cards'], ['As', 'Ks', '2d', '3c', '4h'])
        self.assertNotIn('hero_cards', decision['unconfirmed_fields'])
        self.assertFalse(decision['ready_for_equity_or_ev'])

    def test_reject_preapproved_or_preset_ranges(self):
        for key, value in [('ready_for_equity_or_ev', True), ('source_visual_content_verified', True)]:
            payload = copy.deepcopy(self.handoff); payload[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_scenario_worksheet(payload)
        for key, value in [('ready_for_equity_or_ev', True), ('opponent_range', []),
                           ('model_assumptions', {}), ('fold_probability', 0.3)]:
            payload = copy.deepcopy(self.handoff); payload['decisions'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_scenario_worksheet(payload)

    def test_reject_unconfirmed_promoted_input(self):
        payload = copy.deepcopy(self.handoff)
        payload['decisions'][0]['model_inputs']['hero_cards'] = ['As'] * 5
        with self.assertRaisesRegex(ValueError, 'Unconfirmed'):
            build_scenario_worksheet(payload)

    def test_reject_identity_and_count_tampering(self):
        for key, value in [('table_id', 5), ('event_index', True), ('hand_id', ''),
                           ('confirmed_field_count', 2)]:
            payload = copy.deepcopy(self.handoff); payload['decisions'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_scenario_worksheet(payload)

    def test_reject_duplicate_event(self):
        payload = copy.deepcopy(self.handoff)
        payload['decisions'][1]['table_id'] = payload['decisions'][0]['table_id']
        payload['decisions'][1]['event_index'] = payload['decisions'][0]['event_index']
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            build_scenario_worksheet(payload)

    def test_digests_are_bound_to_input(self):
        a = build_scenario_worksheet(self.handoff)
        payload = copy.deepcopy(self.handoff)
        payload['decisions'][0]['blockers'].append('extra_review_required')
        b = build_scenario_worksheet(payload)
        self.assertNotEqual(a['source_handoff_sha256'], b['source_handoff_sha256'])
        self.assertEqual(a['source_queue_sha256'], b['source_queue_sha256'])

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/'handoff.json', Path(tmp)/'worksheet.json'
            src.write_text(json.dumps(self.handoff), encoding='utf-8')
            self.assertEqual(main([str(src), str(dst)]), 0)
            self.assertEqual(len(json.loads(dst.read_text())['scenarios']), 4)
            with self.assertRaises(ValueError): main([str(src), str(dst)])
            with self.assertRaises(ValueError): main([str(src), str(src)])


if __name__ == '__main__':
    unittest.main()
