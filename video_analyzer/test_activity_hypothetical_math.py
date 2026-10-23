"""Synthetic-only what-if arithmetic and fail-closed provenance tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_hypothetical_math import MODEL, digest, build_hypothetical_report, main
from activity_review_handoff import build_handoff
from activity_review_packet import build_review_packet
from activity_snapshot_chain import build_activity_snapshot_queue
from activity_scenario_worksheet import build_scenario_worksheet
from test_activity_snapshot_chain import fixture


class HypotheticalMathTests(unittest.TestCase):
    def setUp(self):
        self.queue = build_activity_snapshot_queue(fixture())
        draft = build_review_packet(self.queue)['template']
        draft['analysis_status'] = 'manual_review_draft_unverified_no_ev'
        fields = draft['entries'][0]['reviewed_fields']
        for name, value in {
            'hero_cards': ['As', 'Ks', '2d', '3c', '4h'],
            'board': ['Qs', 'Js', 'Ts', '9d', '8c'],
            'observed_action': 'call', 'pot_before_action': 100, 'call_amount': 25,
        }.items():
            fields[name].update(value=value, confidence=.9, source_timestamp=1,
                                source='synthetic frame reviewed', human_confirmed=True)
        self.worksheet = build_scenario_worksheet(build_handoff(self.queue, draft))
        self.request = {'schema_version': 1, 'worksheet_sha256': digest(self.worksheet),
                        'scenarios': [{
                            'table_id': self.worksheet['scenarios'][0]['table_id'],
                            'event_index': self.worksheet['scenarios'][0]['event_index'],
                            'hand_id': self.worksheet['scenarios'][0]['hand_id'],
                            'model_acknowledgement': MODEL, 'trials': 12, 'seed': 17,
                            'opponent_range': [{'cards': ['2c','3d','4c','5d','6h'], 'weight': 1}],
                        }]}

    def test_calculation_is_reproducible_but_never_authorized(self):
        a = build_hypothetical_report(self.worksheet, self.request)
        self.assertEqual(a, build_hypothetical_report(self.worksheet, self.request))
        self.assertFalse(a['ready_for_equity_or_ev'])
        self.assertFalse(a['authorized_for_clips'])
        self.assertEqual(len(a['results']), 1)
        result = a['results'][0]
        self.assertEqual(result['variant'], 'PLO5')
        self.assertEqual(result['equity'], 1)
        self.assertEqual(result['call_ev_vs_fold'], 100)
        self.assertEqual(result['call_ev_sampling_ci95'], [100, 100])
        self.assertFalse(result['authorized_for_clips'])

    def test_other_three_tables_remain_unreviewed(self):
        self.assertEqual(len(self.worksheet['scenarios']), 4)
        self.assertEqual(len(build_hypothetical_report(self.worksheet, self.request)['results']), 1)
        data = copy.deepcopy(self.request)
        data['scenarios'][0]['table_id'] = 2
        with self.assertRaises(ValueError): build_hypothetical_report(self.worksheet, data)

    def test_requires_explicit_model(self):
        data = copy.deepcopy(self.request)
        data['scenarios'][0]['model_acknowledgement'] = 'GTO'
        with self.assertRaisesRegex(ValueError, 'acknowledgement'):
            build_hypothetical_report(self.worksheet, data)

    def test_reject_unconfirmed_inputs(self):
        data = copy.deepcopy(self.worksheet)
        data['scenarios'][0]['unconfirmed_fields'] = ['board']
        request = copy.deepcopy(self.request); request['worksheet_sha256'] = digest(data)
        with self.assertRaisesRegex(ValueError, 'manually attested'):
            build_hypothetical_report(data, request)

    def test_reject_wrong_hash_and_preapproved_worksheet(self):
        data = copy.deepcopy(self.request); data['worksheet_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'bound'):
            build_hypothetical_report(self.worksheet, data)
        worksheet = copy.deepcopy(self.worksheet); worksheet['ready_for_equity_or_ev'] = True
        with self.assertRaisesRegex(ValueError, 'unverified'):
            build_hypothetical_report(worksheet, self.request)

    def test_reject_bad_ranges_and_duplicate_cards(self):
        for value in ([], 'random', [{}], [{'cards':['As']*5, 'weight':1}],
                      [{'cards':['2c','3d','4c','5d','6h'], 'weight':float('nan')}],
                      [{'cards':['2c','3d','4c','5d','6h'], 'weight':-1}]):
            data = copy.deepcopy(self.request); data['scenarios'][0]['opponent_range'] = value
            with self.subTest(value=str(value)), self.assertRaises((ValueError, TypeError)):
                build_hypothetical_report(self.worksheet, data)

    def test_reject_trials_and_seed(self):
        for key, value in [('trials', True), ('trials', 50001), ('trials', 0), ('seed', True)]:
            data = copy.deepcopy(self.request); data['scenarios'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_hypothetical_report(self.worksheet, data)

    def test_reject_duplicate_requests(self):
        data = copy.deepcopy(self.request); data['scenarios'].append(copy.deepcopy(data['scenarios'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            build_hypothetical_report(self.worksheet, data)

    def test_reject_raise_and_invalid_pot(self):
        for key, value in [('observed_action','raise'), ('pot_before_action',True), ('call_amount',0)]:
            worksheet = copy.deepcopy(self.worksheet)
            worksheet['scenarios'][0]['reviewed_visible_inputs'][key] = value
            data = copy.deepcopy(self.request); data['worksheet_sha256'] = digest(worksheet)
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_hypothetical_report(worksheet, data)

    def test_cli_new_file_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            w, r, out = [root / x for x in ('worksheet.json','request.json','report.json')]
            w.write_text(json.dumps(self.worksheet)); r.write_text(json.dumps(self.request))
            self.assertEqual(main([str(w), str(r), str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())['analysis_status'],
                             'hypothetical_math_only_not_video_verified')
            with self.assertRaises(ValueError): main([str(w), str(r), str(out)])
            with self.assertRaises(ValueError): main([str(w), str(r), str(w)])


if __name__ == '__main__':
    unittest.main()
