"""Synthetic consistency regression; never verifies real poker events."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_reviewed_hand_timeline import build_reviewed_hand_timeline
from activity_snapshot_chain import canonical_sha256
from activity_timeline_consistency_audit import (build_timeline_consistency_audit,
                                                 write_timeline_consistency_audit)
from test_activity_reviewed_hand_timeline import fixture


def sample():
    return build_reviewed_hand_timeline(fixture())


class TimelineConsistencyAuditTests(unittest.TestCase):
    def test_four_tables_clean_and_no_math_authority(self):
        result = build_timeline_consistency_audit(sample())
        self.assertEqual(result['counts']['hands'], 4)
        self.assertEqual(result['counts']['audit_flags'], 0)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['automatic_clip_selection_authorized'])

    def test_board_regression_and_changed_prefix(self):
        t = sample()
        e = t['hands'][0]['events'][3]
        e['board_visible'] = ['Qs', 'Js', '9h']
        flags = build_timeline_consistency_audit(t)['hands'][0]['audit_flags']
        self.assertIn('board_visible_prefix_changed', [f['kind'] for f in flags])
        e['board_visible'] = ['Qs', 'Js', 'Ts', '9d']
        t['hands'][0]['events'].append(copy.deepcopy(e))
        t['hands'][0]['events'][-1]['timestamp'] = 4
        t['hands'][0]['events'][-1]['board_visible'] = ['Qs', 'Js', 'Ts']
        flags = build_timeline_consistency_audit(t)['hands'][0]['audit_flags']
        self.assertIn('board_card_count_regressed', [f['kind'] for f in flags])

    def test_hero_change_and_board_collision(self):
        t = sample()
        e = t['hands'][0]['events'][3]
        e['hero_cards_visible'] = ['Ah', 'Ks', '2d', '3c', '4h']
        e['board_visible'] = ['Qs', 'Js', 'Ts', 'Ah']
        kinds = [f['kind'] for f in build_timeline_consistency_audit(t)['hands'][0]['audit_flags']]
        self.assertIn('hero_cards_changed', kinds)
        self.assertIn('visible_board_hero_collision', kinds)

    def test_pot_drop_is_only_review_hint(self):
        t = sample()
        t['hands'][0]['events'][3]['pot_observed'] = 10
        flags = build_timeline_consistency_audit(t)['hands'][0]['audit_flags']
        self.assertEqual([f['kind'] for f in flags], ['pot_value_decreased_review_ui_or_payout'])
        self.assertTrue(flags[0]['requires_manual_review'])

    def test_same_pts_board_and_pot_conflicts(self):
        t = sample()
        e = t['hands'][0]['events'][3]
        e['timestamp'] = 1
        e['pot_observed'] = 10
        t['hands'][0]['events'][1]['pot_observed'] = 20
        kinds = [f['kind'] for f in build_timeline_consistency_audit(t)['hands'][0]['audit_flags']]
        self.assertIn('same_pts_conflicting_board', kinds)
        self.assertIn('non_monotonic_observation_pts', kinds)

    def test_unchanged_observations_not_filled_from_future(self):
        t = sample()
        result = build_timeline_consistency_audit(t)
        self.assertEqual(result['counts']['audit_flags'], 0)
        self.assertIsNone(t['hands'][0]['events'][2]['board_visible'])

    def test_reject_tamper_and_unsafe_authority(self):
        t = sample()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_timeline_consistency_audit(t, expected_timeline_sha256='0'*64)
        self.assertEqual(build_timeline_consistency_audit(t,
            expected_timeline_sha256=canonical_sha256(t))['counts']['hands'], 4)
        t['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build_timeline_consistency_audit(t)

    def test_reject_invalid_data_and_bad_tolerance(self):
        for field, value in [('table_id', True), ('first_observed_pts', -1),
                             ('human_review_required', False)]:
            t = sample()
            t['hands'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_timeline_consistency_audit(t)
        t = sample()
        t['hands'][0]['events'][1]['board_visible'] = ['As']*3
        with self.assertRaises(ValueError):
            build_timeline_consistency_audit(t)
        with self.assertRaises(ValueError):
            build_timeline_consistency_audit(sample(), pot_drop_tolerance=float('nan'))

    def test_no_input_mutation(self):
        t = sample()
        before = copy.deepcopy(t)
        build_timeline_consistency_audit(t)
        self.assertEqual(t, before)

    def test_json_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src, dst = d/'timeline.json', d/'audit.json'
            src.write_text(json.dumps(sample()), encoding='utf-8')
            cmd = [sys.executable, str(Path(__file__).with_name('activity_timeline_consistency_audit.py')),
                   str(src), str(dst)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(dst.read_text())['counts']['hands'], 4)
            with self.assertRaises(ValueError):
                write_timeline_consistency_audit(src, dst)


if __name__ == '__main__':
    unittest.main()
