"""Synthetic-only tests: worksheet never authenticates poker observations."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_math_readiness_triage import build_math_readiness_triage
from activity_math_review_handoff import (build_math_review_handoff,
                                         export_math_review_handoff)
from activity_snapshot_chain import canonical_sha256
from test_activity_math_readiness_triage import fixtures


class MathReviewHandoffTests(unittest.TestCase):
    def sources(self):
        packet, timeline = fixtures()
        return build_math_readiness_triage(packet, timeline), packet, timeline

    def test_four_tables_time_local_and_no_authority(self):
        triage, packet, timeline = self.sources()
        result = build_math_review_handoff(triage, packet, timeline)
        self.assertEqual(result['counts']['review_tasks'], 4)
        self.assertEqual([r['table_id'] for r in result['review_tasks']], [1, 2, 3, 4])
        for row in result['review_tasks']:
            self.assertEqual(row['decision_pts_seconds'], 2)
            self.assertEqual(row['review_interval_observed_pts_not_hand_boundaries'], [0, 4])
            self.assertEqual(row['same_pts_field_status']['board'], 'missing_at_decision_pts')
            self.assertIsNone(row['human_review_fields_to_complete']['opponent_range_assumption'])
            self.assertFalse(row['ready_for_equity_or_ev'])
            self.assertFalse(row['reviewer_approved_for_manual_clip'])
            self.assertFalse(row['automatic_clip_selection_authorized'])
        self.assertFalse(result['strategic_error_established'])

    def test_source_hashes_and_no_mutation(self):
        triage, packet, timeline = self.sources()
        original = copy.deepcopy((triage, packet, timeline))
        result = build_math_review_handoff(
            triage, packet, timeline,
            expected_triage_sha256=canonical_sha256(triage),
            expected_packet_sha256=canonical_sha256(packet),
            expected_timeline_sha256=canonical_sha256(timeline))
        self.assertEqual(result, build_math_review_handoff(triage, packet, timeline))
        self.assertEqual(result['source_triage_sha256'], canonical_sha256(triage))
        self.assertEqual((triage, packet, timeline), original)

    def test_reject_tampered_pts_blockers_and_permissions(self):
        triage, packet, timeline = self.sources()
        for path, value in [(['tasks', 0, 'decision_pts_seconds'], 3),
                            (['tasks', 0, 'review_blockers'], []),
                            (['tasks', 0, 'ready_for_equity_or_ev'], True),
                            (['automatic_clip_selection_authorized'], True),
                            (['counts', 'tasks_omitted_by_budget'], 99)]:
            altered = copy.deepcopy(triage)
            target = altered
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_math_review_handoff(altered, packet, timeline)

    def test_reject_changed_packet_or_timeline(self):
        triage, packet, timeline = self.sources()
        timeline['hands'][0]['events'][2]['timestamp'] = 2.25
        with self.assertRaises(ValueError):
            build_math_review_handoff(triage, packet, timeline)
        triage, packet, timeline = self.sources()
        packet['hands'][0]['hand_reconstruction_verified'] = True
        with self.assertRaises(ValueError):
            build_math_review_handoff(triage, packet, timeline)

    def test_budget_preserves_omissions_and_empty_case(self):
        packet, timeline = fixtures()
        triage = build_math_readiness_triage(packet, timeline, max_tasks=2)
        result = build_math_review_handoff(triage, packet, timeline)
        self.assertEqual(result['counts'], {'review_tasks': 2, 'omitted_due_to_upstream_budget': 2})
        for hand in timeline['hands']:
            for event in hand['events']:
                if event['action_human_annotated_not_ocr_verified'] in ('fold', 'call', 'check', 'bet', 'raise'):
                    event['action_human_annotated_not_ocr_verified'] = None
        # No longer a valid human packet; rebuild its source identity and use
        # the original validated packet only to test normal budget behavior.
        with self.assertRaises(ValueError):
            build_math_review_handoff(triage, packet, timeline)

    def test_window_clamps_to_observed_pts(self):
        triage, packet, timeline = self.sources()
        result = build_math_review_handoff(triage, packet, timeline,
                                           seconds_before=0.5, seconds_after=0.25)
        self.assertEqual(result['review_tasks'][0]['review_interval_observed_pts_not_hand_boundaries'],
                         [1.5, 2.25])
        for value in (-1, True, float('nan'), float('inf'), 31, '5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_math_review_handoff(triage, packet, timeline, seconds_after=value)

    def test_cli_export_and_no_overwrite_or_symlink(self):
        triage, packet, timeline = self.sources()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = [root / x for x in ('triage.json', 'packet.json', 'timeline.json')]
            output = root / 'worksheet.json'
            for path, data in zip(inputs, (triage, packet, timeline)):
                path.write_text(json.dumps(data), encoding='utf-8')
            cmd = [sys.executable, str(Path(__file__).with_name('activity_math_review_handoff.py')),
                   *map(str, inputs), str(output)]
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(output.read_text())['counts']['review_tasks'], 4)
            with self.assertRaises(ValueError):
                export_math_review_handoff(*inputs, output)
            with self.assertRaises(ValueError):
                export_math_review_handoff(*inputs, inputs[0])
            alias = root / 'alias.json'
            alias.symlink_to(inputs[0])
            with self.assertRaises(ValueError):
                export_math_review_handoff(alias, inputs[1], inputs[2], root / 'next.json')


if __name__ == '__main__':
    unittest.main()
