"""Synthetic-only math preflight: no OCR or model authority is granted."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_hand_review_packet import build_hand_review_packet
from activity_math_readiness_triage import (build_math_readiness_triage,
                                            export_math_readiness_triage)
from activity_snapshot_chain import canonical_sha256
from test_activity_consistency_frame_review import changed
from test_activity_visual_timeline_crosswalk import alignment
from test_activity_ocr_timeline_review import sources as ocr_sources, align as ocr_align


def fixtures(aligned=False):
    q, t = changed()
    o, _ = ocr_sources()
    kw = {'ocr': o}
    if aligned:
        kw.update(queue_alignment=alignment(q, t), ocr_alignment=ocr_align(o, t))
    return build_hand_review_packet(q, t, **kw), t


class MathReadinessTriageTests(unittest.TestCase):
    def test_four_tables_call_tasks_blocked_and_no_future_borrowing(self):
        p, t = fixtures()
        out = build_math_readiness_triage(p, t)
        self.assertEqual(out['counts']['hands'], 4)
        self.assertEqual(out['counts']['decision_observations_total'], 4)
        self.assertEqual(len(out['tasks']), 4)
        self.assertEqual([r['table_id'] for r in out['tasks']], [1, 2, 3, 4])
        for task in out['tasks']:
            self.assertEqual(task['decision_pts_seconds'], 2)
            self.assertEqual(task['same_pts_field_status']['board'], 'missing_at_decision_pts')
            self.assertEqual(task['same_pts_field_status']['hero_cards'], 'missing_at_decision_pts')
            self.assertIn('missing_same_pts_board', task['review_blockers'])
            self.assertFalse(task['ready_for_equity_or_ev'])
            self.assertFalse(task['clip_selection_authorized'])
        self.assertFalse(out['automatic_clip_selection_authorized'])

    def test_aligned_ocr_is_not_decision_confirmation(self):
        p, t = fixtures(True)
        out = build_math_readiness_triage(p, t)
        self.assertEqual(out['tasks'][0]['ocr_candidates_in_hand_not_event_verified'], 1)
        self.assertIn('hand_timeline_consistency_requires_review', out['tasks'][0]['review_blockers'])
        self.assertFalse(out['tasks'][0]['model_inputs_extracted'])

    def test_same_pts_label_presence_never_authorizes_math(self):
        p, t = fixtures()
        t['hands'][0]['events'][2]['board_visible'] = ['Qs', 'Js', 'Ts']
        t['hands'][0]['events'][2]['field_evidence']['board'] = {
            'candidate_index': 900, 'decoded_source_pts': 2,
            'source_image': 'synthetic.png', 'reviewer_confidence_subjective': .8}
        q, _ = changed()
        p = build_hand_review_packet(q, t)
        out = build_math_readiness_triage(p, t)
        self.assertEqual(out['tasks'][0]['same_pts_field_status']['board'],
                         'human_label_with_same_pts_ocr_reference_not_verified')
        self.assertFalse(out['ready_for_equity_or_ev'])

    def test_missing_provenance_and_mismatched_pts_are_review_only(self):
        p, t = fixtures()
        t['hands'][0]['events'][2]['pot_observed'] = 30
        p['source_reviewed_timeline_sha256'] = canonical_sha256(t)
        out = build_math_readiness_triage(p, t)
        self.assertEqual(out['tasks'][0]['same_pts_field_status']['pot'],
                         'human_label_without_same_pts_ocr_reference')
        t['hands'][0]['events'][2]['field_evidence']['pot'] = {'decoded_source_pts': 3}
        p['source_reviewed_timeline_sha256'] = canonical_sha256(t)
        out = build_math_readiness_triage(p, t)
        self.assertEqual(out['tasks'][0]['same_pts_field_status']['pot'],
                         'ocr_reference_pts_mismatch_manual_review')

    def test_reject_packet_timeline_mismatch_and_sha(self):
        p, t = fixtures()
        t['hands'][0]['events'][2]['timestamp'] = 2.1
        with self.assertRaises(ValueError):
            build_math_readiness_triage(p, t)
        p, t = fixtures()
        with self.assertRaisesRegex(ValueError, 'Packet SHA-256 mismatch'):
            build_math_readiness_triage(p, t, expected_packet_sha256='0'*64)
        out = build_math_readiness_triage(p, t,
                                         expected_packet_sha256=canonical_sha256(p),
                                         expected_timeline_sha256=canonical_sha256(t))
        self.assertEqual(out['source_hand_review_packet_sha256'], canonical_sha256(p))

    def test_reject_promoted_packet_or_hand(self):
        p, t = fixtures()
        p['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build_math_readiness_triage(p, t)
        p, t = fixtures()
        p['hands'][0]['hand_reconstruction_verified'] = True
        with self.assertRaises(ValueError):
            build_math_readiness_triage(p, t)

    def test_reject_forged_flags_and_hand_identity(self):
        p, t = fixtures()
        p['hands'][0]['consistency_flags_with_frame_suggestions'] = []
        with self.assertRaisesRegex(ValueError, 'audit flags'):
            build_math_readiness_triage(p, t)
        p, t = fixtures()
        p['hands'][0]['table_id'] = 4
        with self.assertRaises(ValueError):
            build_math_readiness_triage(p, t)

    def test_budget_determinism_and_no_mutation(self):
        p, t = fixtures()
        original = copy.deepcopy((p, t))
        a = build_math_readiness_triage(p, t, max_tasks=2)
        self.assertEqual(a['counts']['tasks_omitted_by_budget'], 2)
        self.assertEqual(a, build_math_readiness_triage(p, t, max_tasks=2))
        self.assertEqual((p, t), original)
        for bad in (0, True, 5001, 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                build_math_readiness_triage(p, t, max_tasks=bad)

    def test_raise_requires_additional_hypotheses(self):
        p, t = fixtures()
        t['hands'][0]['events'][2]['action_human_annotated_not_ocr_verified'] = 'raise'
        p['source_reviewed_timeline_sha256'] = canonical_sha256(t)
        out = build_math_readiness_triage(p, t)
        self.assertIn('raise_size_fold_equity_and_response_model_not_supplied',
                      out['tasks'][0]['review_blockers'])

    def test_plo6_variant_and_private_card_count_mismatch_are_blocked(self):
        q, t = changed()
        event = t['hands'][0]['events'][2]
        event['variant_human_annotated'] = 'PLO6'
        event['hero_cards_visible'] = ['As', 'Ks', '2d', '3c', '4h', '5d']
        packet = build_hand_review_packet(q, t)
        report = build_math_readiness_triage(packet, t)
        self.assertNotIn('hero_card_count_variant_mismatch', report['tasks'][0]['review_blockers'])
        event['hero_cards_visible'] = ['As', 'Ks', '2d', '3c', '4h']
        packet = build_hand_review_packet(q, t)
        report = build_math_readiness_triage(packet, t)
        self.assertIn('hero_card_count_variant_mismatch', report['tasks'][0]['review_blockers'])
        self.assertFalse(report['tasks'][0]['ready_for_equity_or_ev'])

    def test_cli_roundtrip_no_overwrite_or_symlink(self):
        p, t = fixtures()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pp, tp, output = root/'packet.json', root/'timeline.json', root/'result.json'
            pp.write_text(json.dumps(p), encoding='utf-8')
            tp.write_text(json.dumps(t), encoding='utf-8')
            cmd = [sys.executable, str(Path(__file__).with_name('activity_math_readiness_triage.py')),
                   str(pp), str(tp), str(output)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(output.read_text())['counts']['tasks_returned'], 4)
            with self.assertRaises(ValueError):
                export_math_readiness_triage(pp, tp, output)
            with self.assertRaises(ValueError):
                export_math_readiness_triage(pp, tp, pp)
            alias = root/'alias.json'
            alias.symlink_to(pp)
            with self.assertRaises(ValueError):
                export_math_readiness_triage(alias, tp, root/'another.json')


if __name__ == '__main__':
    unittest.main()
