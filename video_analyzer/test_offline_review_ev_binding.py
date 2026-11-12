import json
from pathlib import Path
import tempfile
import unittest
from offline_review_ev_binding import bind, strict_read


def fixture():
    review = dict(schema_version=1, hand_id='h1', table_id=2,
                  source_video_sha256='a'*64, start_seconds=10, end_seconds=24,
                  action='call', pot_bb=150., call_bb=50.)
    gate = dict(schema_version=1, hand_id='h1', table_id=2,
                source_video_sha256='a'*64, analysis_status='READY_FOR_CONDITIONAL_MODEL',
                missing_or_unconfirmed=[], source_hand_reconstruction_verified=False,
                strategic_error_established=False, gto_solution=False)
    rows = []
    for rid, q in [('wide', .3), ('tight', .2)]:
        lo, hi = q-.01, q+.01
        rows.append(dict(range_id=rid, equity=q, equity_interval_conditional=[lo,hi],
                         ev_call_bb=q*200-50, ev_interval_conditional_bb=[lo*200-50,hi*200-50],
                         conditional_label=('positive_under_interval' if q>.25 else 'negative_under_interval'),
                         range_is_user_assumption=True, range_uncertainty_included_in_interval=False))
    ev = dict(schema_version=1, analysis_status='hypothetical_weighted_range_ev_not_video_verified',
              scenario_id='hypothesis1', pot_before_call_bb=150., call_cost_bb=50.,
              break_even_equity=.25, range_results=rows, range_sensitive=True,
              source_hand_reconstruction_verified=False, strategic_error_established=False,
              automatic_clip_selection_authorized=False, gto_solution=False,
              range_uncertainty_included_in_interval=False)
    return review, gate, ev


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.r, self.g, self.e = fixture()

    def ok(self):
        return bind(self.r, self.g, self.e)

    def bad(self):
        with self.assertRaises(ValueError):
            self.ok()

    def test_ready_conditional_not_verdict(self):
        x = self.ok()
        self.assertEqual(x['analysis_status'], 'CONDITIONAL_MODEL_REVIEW_ONLY')
        self.assertFalse(x['strategic_error_established'])
        self.assertTrue(x['range_sensitive'])
        self.assertEqual(len(x['review_record_sha256']), 64)

    def test_unconfirmed_evidence_blocks_model(self):
        self.g['analysis_status'] = 'INSUFFICIENT_DATA'
        self.g['missing_or_unconfirmed'] = ['board_cards']
        self.assertEqual(self.ok()['analysis_status'], 'INSUFFICIENT_DATA')

    def test_gate_missing_status_mismatch(self):
        self.g['missing_or_unconfirmed'] = ['pot']
        self.bad()

    def test_hand_mismatch(self):
        self.g['hand_id'] = 'other'
        self.bad()

    def test_table_mismatch(self):
        self.g['table_id'] = 3
        self.bad()

    def test_video_hash_mismatch(self):
        self.g['source_video_sha256'] = 'b'*64
        self.bad()

    def test_invalid_time(self):
        self.r['end_seconds'] = 10
        self.bad()

    def test_boolean_time(self):
        self.r['start_seconds'] = True
        self.bad()

    def test_boolean_table(self):
        self.r['table_id'] = True
        self.bad()

    def test_wrong_action(self):
        self.r['action'] = 'raise'
        self.bad()

    def test_wrong_pot(self):
        self.r['pot_bb'] = 152
        self.bad()

    def test_wrong_call(self):
        self.r['call_bb'] = 49
        self.bad()

    def test_wrong_odds(self):
        self.e['break_even_equity'] = .5
        self.bad()

    def test_wrong_ev(self):
        self.e['range_results'][0]['ev_call_bb'] = 100
        self.bad()

    def test_wrong_ev_bounds(self):
        self.e['range_results'][0]['ev_interval_conditional_bb'][0] = 100
        self.bad()

    def test_wrong_equity_interval(self):
        self.e['range_results'][0]['equity_interval_conditional'] = [.01,.02]
        self.bad()

    def test_wrong_label(self):
        self.e['range_results'][0]['conditional_label'] = 'negative_under_interval'
        self.bad()

    def test_duplicate_ranges(self):
        self.e['range_results'][1]['range_id'] = 'wide'
        self.bad()

    def test_promoted_gto(self):
        self.e['gto_solution'] = True
        self.bad()

    def test_promoted_video(self):
        self.g['source_hand_reconstruction_verified'] = True
        self.bad()

    def test_promoted_verdict(self):
        self.e['strategic_error_established'] = True
        self.bad()

    def test_promoted_clip_selection(self):
        self.e['automatic_clip_selection_authorized'] = True
        self.bad()

    def test_false_range_sensitivity(self):
        self.e['range_sensitive'] = False
        self.bad()

    def test_range_uncertainty_flag(self):
        self.e['range_results'][0]['range_uncertainty_included_in_interval'] = True
        self.bad()

    def test_tolerance(self):
        self.r['pot_bb'] = 150.005
        self.ok()

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'x.json'
            p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):
                strict_read(p)

    def test_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'x.json'
            p.write_text('{"a":NaN}')
            with self.assertRaises(ValueError):
                strict_read(p)

    def test_digest_determinism(self):
        self.assertEqual(self.ok(), self.ok())


if __name__ == '__main__':
    unittest.main()
