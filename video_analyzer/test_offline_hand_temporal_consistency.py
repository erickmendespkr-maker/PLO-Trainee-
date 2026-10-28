"""Synthetic regression tests for offline hand temporal warnings."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_hand_temporal_consistency import inspect, run


def hand():
    return {'hand_id':'H1','table_id':1,'variant':'PLO5','boundary_origin':'manual_unverified',
            'ready_for_equity_or_ev':False,'start_seconds':0,'end_seconds':20,
            'unresolved_indices':[],'reviewed_fields':{'hero_cards':[
                {'value':'As Ks Qs Js Ts','timestamp_seconds':1,'review':'confirmed'}],
                'board':[{'value':'2h 3h 4h','timestamp_seconds':3,'review':'confirmed'},
                         {'value':'2h 3h 4h 5h','timestamp_seconds':8,'review':'corrected'}]}}


def doc():
    return {'schema_version':1,'analysis_status':'offline_reviewed_hand_drafts_only',
            'hands_reconstructed':False,'ready_for_equity_or_ev':False,'hands':[hand()]}


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.data=doc()

    def warnings(self):
        return inspect(self.data)['hands'][0]['warnings']

    def test_valid_progression(self):
        self.assertEqual(self.warnings(),[])
        self.assertFalse(inspect(self.data)['ready_for_equity_or_ev'])

    def test_board_regression(self):
        self.data['hands'][0]['reviewed_fields']['board'][1]['value']='2h 3h'
        self.assertIn('board_regressed',self.warnings())

    def test_nonprefix(self):
        self.data['hands'][0]['reviewed_fields']['board'][1]['value']='2h 3h 4s 5h'
        self.assertIn('board_nonprefix_change',self.warnings())

    def test_missing_street(self):
        self.data['hands'][0]['reviewed_fields']['board'][1]['value']='2h 3h 4h 5h 6h'
        self.assertIn('missing_intermediate_street',self.warnings())

    def test_hero_board_collision(self):
        self.data['hands'][0]['reviewed_fields']['board'][0]['value']='As 3h 4h'
        self.assertIn('hero_board_collision',self.warnings())

    def test_partial_board(self):
        self.data['hands'][0]['reviewed_fields']['board'][0]['value']='2h 3h'
        self.assertIn('partial_board',self.warnings())

    def test_unresolved(self):
        self.data['hands'][0]['unresolved_indices']=[8]
        self.assertIn('unresolved_ocr',self.warnings())

    def test_reject_wrong_hero_count(self):
        self.data['hands'][0]['variant']='PLO6'
        with self.assertRaisesRegex(ValueError,'invalid cards'):inspect(self.data)

    def test_reject_out_of_bounds_pts(self):
        self.data['hands'][0]['reviewed_fields']['board'][1]['timestamp_seconds']=25
        with self.assertRaisesRegex(ValueError,'invalid reviewed event'):inspect(self.data)

    def test_reject_fake_ev_ready(self):
        self.data['ready_for_equity_or_ev']=True
        with self.assertRaisesRegex(ValueError,'provenance'):inspect(self.data)

    def test_reject_duplicate_hand(self):
        self.data['hands'].append(copy.deepcopy(self.data['hands'][0]))
        with self.assertRaisesRegex(ValueError,'invalid hand'):inspect(self.data)

    def test_cli_and_sha(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.json';out=Path(d)/'result.json'
            p.write_text(json.dumps(self.data))
            result=run(p,out)
            self.assertTrue(out.exists())
            self.assertEqual(json.loads(out.read_text()),result)
            with self.assertRaisesRegex(ValueError,'unsafe'):run(p,out)


if __name__=='__main__':unittest.main()
