"""Synthetic-only review packet integration tests; no real poker recognition."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_hand_review_packet import (build_hand_review_packet,
                                         export_hand_review_packet)
from activity_snapshot_chain import canonical_sha256
from test_activity_consistency_frame_review import changed
from test_activity_visual_timeline_crosswalk import alignment
from test_activity_ocr_timeline_review import sources as ocr_sources, align as ocr_align


class HandReviewPacketTests(unittest.TestCase):
    def test_unaligned_keeps_all_ocr_unassigned_and_no_frames(self):
        q, t = changed()
        o, _ = ocr_sources()
        out = build_hand_review_packet(q, t, ocr=o)
        self.assertEqual(out['counts']['hands'], 4)
        self.assertEqual(out['counts']['consistency_flags'], 1)
        self.assertEqual(out['counts']['frame_suggestions'], 0)
        self.assertEqual(out['counts']['ocr_candidates_unassigned'], 4)
        self.assertEqual(out['counts']['ocr_candidates_exact_pts_unique_hand'], 0)
        self.assertFalse(out['ready_for_equity_or_ev'])
        self.assertFalse(out['automatic_clip_selection_authorized'])

    def test_aligned_ocr_and_roi_four_tables_separated(self):
        q, t = changed()
        o, _ = ocr_sources()
        out = build_hand_review_packet(q, t, queue_alignment=alignment(q, t),
                                       ocr=o, ocr_alignment=ocr_align(o, t))
        self.assertEqual(out['counts']['frame_suggestions'], 1)
        self.assertEqual(out['counts']['ocr_candidates_exact_pts_unique_hand'], 4)
        self.assertEqual(out['counts']['ocr_candidates_unassigned'], 0)
        for index, hand in enumerate(out['hands'], 1):
            self.assertEqual(hand['table_id'], index)
            self.assertEqual(hand['ocr_exact_pts_review_candidates'][0]['table_id'], index)
            self.assertFalse(hand['hand_reconstruction_verified'])
        self.assertEqual(out['hands'][0]['consistency_flags_with_frame_suggestions'][0]
                         ['suggested_roi_frames'][0]['pixel_review_rank'], 1)

    def test_disagreement_is_review_hint_not_math_authority(self):
        q, t = changed()
        o, _ = ocr_sources()
        o['candidates'][0]['parsed_candidate'] = ['Qs', 'Js', '9h']
        out = build_hand_review_packet(q, t, ocr=o, ocr_alignment=ocr_align(o, t))
        self.assertIn('disagrees', out['hands'][0]['ocr_exact_pts_review_candidates'][0]['status'])
        self.assertFalse(out['strategic_error_established'])
        self.assertFalse(out['ready_for_equity_or_ev'])

    def test_ambiguous_ocr_does_not_join_any_hand(self):
        q, t = changed()
        o, _ = ocr_sources()
        # Duplicate the table/time span of another hand: exact matches become ambiguous.
        t['hands'][1]['table_id'] = 1
        out = build_hand_review_packet(q, t, ocr=o, ocr_alignment=ocr_align(o, t))
        self.assertEqual(out['counts']['ocr_candidates_unassigned'], 2)
        self.assertEqual(out['counts']['ocr_candidates_exact_pts_unique_hand'], 2)

    def test_budgets_preserve_counts_and_determinism(self):
        q, t = changed()
        o, _ = ocr_sources()
        for _ in range(3):
            o['candidates'].append(copy.deepcopy(o['candidates'][0]))
        original = copy.deepcopy((q, t, o))
        kwargs = dict(ocr=o, ocr_alignment=ocr_align(o, t), max_ocr_per_hand=1)
        a = build_hand_review_packet(q, t, **kwargs)
        self.assertEqual(a['counts']['ocr_candidates_assigned_omitted'], 3)
        self.assertEqual(a['counts']['ocr_candidates_exact_pts_unique_hand'], 7)
        self.assertEqual(a, build_hand_review_packet(q, t, **kwargs))
        self.assertEqual((q, t, o), original)

    def test_orphan_budget_preserves_total(self):
        q, t = changed()
        o, _ = ocr_sources()
        out = build_hand_review_packet(q, t, ocr=o, max_unassigned_ocr=1)
        self.assertEqual(len(out['unassigned_ocr_candidates']), 1)
        self.assertEqual(out['counts']['ocr_candidates_unassigned'], 4)
        self.assertEqual(out['counts']['ocr_candidates_unassigned_omitted'], 3)

    def test_reject_cross_recording_and_sha_mismatch(self):
        q, t = changed()
        o, _ = ocr_sources()
        o['recording_sha256'] = 'f'*64
        with self.assertRaises(ValueError):
            build_hand_review_packet(q, t, ocr=o)
        o, _ = ocr_sources()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_hand_review_packet(q, t, ocr=o, expected_ocr_sha256='0'*64)
        result = build_hand_review_packet(q, t, ocr=o,
                                          expected_ocr_sha256=canonical_sha256(o))
        self.assertEqual(result['source_ocr_report_sha256'], canonical_sha256(o))

    def test_invalid_inputs_and_unsafe_flags_rejected(self):
        q, t = changed()
        with self.assertRaises(ValueError):
            build_hand_review_packet(q, t, ocr_alignment={'x': 1})
        with self.assertRaises(ValueError):
            build_hand_review_packet(q, t, max_frames_per_flag=True)
        with self.assertRaises(ValueError):
            build_hand_review_packet(q, t, max_frames_per_flag=21)
        with self.assertRaises(ValueError):
            build_hand_review_packet(q, t, max_ocr_per_hand=0)
        with self.assertRaises(ValueError):
            build_hand_review_packet(q, t, max_unassigned_ocr=101)
        t['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build_hand_review_packet(q, t)

    def test_cli_json_and_no_overwrite(self):
        q, t = changed()
        o, _ = ocr_sources()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = {'queue.json': q, 'timeline.json': t, 'ocr.json': o,
                    'queue_align.json': alignment(q, t),
                    'ocr_align.json': ocr_align(o, t)}
            for name, value in data.items():
                (root/name).write_text(json.dumps(value), encoding='utf-8')
            output = root/'packet.json'
            cmd = [sys.executable, str(Path(__file__).with_name('activity_hand_review_packet.py')),
                   str(root/'queue.json'), str(root/'timeline.json'), str(output),
                   '--queue-alignment-json', str(root/'queue_align.json'),
                   '--ocr-json', str(root/'ocr.json'),
                   '--ocr-alignment-json', str(root/'ocr_align.json')]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(output.read_text())['counts']['frame_suggestions'], 1)
            with self.assertRaises(ValueError):
                export_hand_review_packet(root/'queue.json', root/'timeline.json', output)
            with self.assertRaises(ValueError):
                export_hand_review_packet(root/'queue.json', root/'timeline.json', root/'queue.json')
            alias = root/'alias.json'
            alias.symlink_to(root/'queue.json')
            with self.assertRaises(ValueError):
                export_hand_review_packet(alias, root/'timeline.json', root/'new.json')


if __name__ == '__main__':
    unittest.main()
