"""Synthetic and prior-cycle fixture tests for fail-closed math intake."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from hand_math_intake import build, export, validate_history


FIXTURE = Path(__file__).resolve().parents[2] / 'cycle94_demo_synthetic.zip'


class MathIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reproducible standalone fixture shaped like the upstream bridge.
        cls.original = {
            'schema_version': 1,
            'analysis_status': 'visual_verdicts_linked_to_unverified_hand_history_no_math',
            **{name: 'a' * 64 for name in (
                'recording_sha256', 'source_navigation_sha256',
                'source_review_sha256', 'source_gallery_sha256',
                'source_visual_verdicts_sha256')},
            'requires_manual_review': True,
            **{name: False for name in (
                'hand_boundaries_verified', 'cards_or_actions_verified',
                'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
                'strategic_error_established')},
            'entries': [],
            'counts': {'spans': 4, 'annotations': 4, 'pending': 1,
                       'confirmed_visual': 1, 'rejected_visual': 1,
                       'uncertain': 0, 'unreviewable': 1},
        }
        for table, verdict in enumerate(('pending', 'confirmed_visual',
                                         'rejected_visual', 'unreviewable'), 1):
            cls.original['entries'].append({
                'entry_id': f'table_{table}_span_0', 'table_id': table,
                'start_human_seconds': 1.0, 'end_human_seconds': 3.0,
                'contains_unresolved_interior_candidates': table == 2,
                'hand_reconstruction_verified': False,
                'ready_for_equity_or_ev': False,
                'annotations': [{
                    'kind': 'field', 'item': 'variant', 'claimed_value': 'PLO5',
                    'source_kind': 'manual_video_review',
                    'requested_pts_seconds': 1.1 if table != 4 else None,
                    'still_sha256': 'b' * 64 if table != 4 else None,
                    'visual_verdict': verdict,
                    'evidence_status': ('human_still_review_only_not_hand_verified'
                                        if verdict == 'confirmed_visual'
                                        else 'not_visually_confirmed'),
                    'ready_for_equity_or_ev': False,
                }],
            })

    def setUp(self):
        self.source = copy.deepcopy(self.original)

    def test_four_tables_blocked_and_empty_scenarios(self):
        result = build(self.source, 'f' * 64)
        self.assertEqual(len(result['tasks']), 4)
        self.assertEqual(result['counts']['math_ready'], 0)
        self.assertTrue(all(not t['ready_for_equity_or_ev'] for t in result['tasks']))
        self.assertTrue(all(t['manual_scenario_draft']['call_range'] == []
                            for t in result['tasks']))
        self.assertTrue(all(t['manual_scenario_draft']['reviewed_fields']['hero_cards']['value'] is None
                            for t in result['tasks']))

    def test_confirmed_visual_still_requires_attestation(self):
        result = build(self.source, 'f' * 64)
        self.assertIn('independent_complete_hand_and_decision_attestation_required',
                      result['tasks'][1]['blocking_reasons'])
        self.assertIn('possible_unresolved_hand_boundary', result['tasks'][1]['blocking_reasons'])

    def test_no_claimed_values_promoted(self):
        self.source['entries'][0]['annotations'][0]['claimed_value'] = ['As', 'Kd', 'Qc']
        task = build(self.source, 'f' * 64)['tasks'][0]
        self.assertNotIn('claimed_value', task['source_annotations'][0])
        self.assertIsNone(task['manual_scenario_draft']['reviewed_fields']['board']['value'])

    def test_tampered_authority_flags_rejected(self):
        for flag in ('ready_for_equity_or_ev', 'cards_or_actions_verified',
                     'automatic_clip_selection_authorized'):
            altered = copy.deepcopy(self.source)
            altered[flag] = True
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                build(altered, 'f' * 64)

    def test_entry_authority_rejected(self):
        self.source['entries'][0]['hand_reconstruction_verified'] = True
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_annotation_authority_rejected(self):
        self.source['entries'][0]['annotations'][0]['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_bad_digest_rejected(self):
        self.source['source_gallery_sha256'] = 'not-a-sha'
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_duplicate_span_rejected(self):
        self.source['entries'][1]['entry_id'] = self.source['entries'][0]['entry_id']
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_duplicate_annotation_rejected(self):
        self.source['entries'][0]['annotations'] *= 2
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_bad_table_rejected(self):
        self.source['entries'][0]['table_id'] = True
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_invalid_timestamp_rejected(self):
        for value in (float('nan'), float('inf'), -1, True, 3.0):
            self.source['entries'][0]['start_human_seconds'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                build(self.source, 'f' * 64)

    def test_forged_counts_rejected(self):
        self.source['counts']['confirmed_visual'] = 2
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_contradictory_verdict_rejected(self):
        self.source['entries'][0]['annotations'][0]['evidence_status'] = 'human_still_review_only_not_hand_verified'
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_confirmed_missing_still_rejected(self):
        self.source['entries'][1]['annotations'][0]['still_sha256'] = None
        with self.assertRaises(ValueError):
            build(self.source, 'f' * 64)

    def test_export_immutable_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'source.json', Path(tmp) / 'out.json'
            src.write_text(json.dumps(self.source), encoding='utf-8')
            result = export(src, dst)
            self.assertEqual(result['source_visual_history_sha256'],
                             hashlib.sha256(src.read_bytes()).hexdigest())
            self.assertEqual(json.loads(dst.read_text()), result)
            with self.assertRaises(ValueError):
                export(src, dst)
            with self.assertRaises(ValueError):
                export(src, src)

    def test_reject_symlink_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, link, dst = (Path(tmp) / name for name in ('src.json', 'link.json', 'out.json'))
            src.write_text(json.dumps(self.source))
            link.symlink_to(src)
            with self.assertRaises(ValueError):
                export(link, dst)

    def test_reject_nonstandard_nan_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / 'src.json', Path(tmp) / 'out.json'
            src.write_text(json.dumps(self.source).replace('1.0', 'NaN', 1))
            with self.assertRaises(ValueError):
                export(src, dst)


if __name__ == '__main__':
    unittest.main()
