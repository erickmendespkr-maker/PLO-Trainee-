"""Offline synthetic tests for manual clip <-> hypothetical math provenance."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from offline_manual_clip_export import export_clip
from offline_clip_frame_pts_audit import build_audit
from offline_clip_math_provenance import build_link, export_link, canonical_sha, load


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()


class ClipMathProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.source = cls.base / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=8',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-y', str(cls.source)], check=True)
        cls.source_sha = hashlib.sha256(cls.source.read_bytes()).hexdigest()
        cls.selection = {
            'schema_version': 1, 'recording_sha256': cls.source_sha,
            'table_id': 1, 'start_seconds': 3.5, 'end_seconds': 5.5,
            'human_selected': True, 'explanation': 'Somente revisão humana sintética.',
            'reviewer_confidence': .7, 'crop': None,
        }
        cls.sel_path = cls.base / 'selection.json'
        cls.sel_path.write_bytes(encode(cls.selection))
        cls.clip_path = cls.base / 'clip.mp4'
        cls.sidecar = export_clip(cls.source, cls.sel_path, cls.clip_path)
        cls.audit = build_audit(cls.source, cls.selection)
        cls.clip_sha = hashlib.sha256(cls.clip_path.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def make_inputs(self, variant='PLO5', table=1):
        hero = ['As', 'Kh', 'Qd', 'Jc', 'Ts'] + (['9h'] if variant == 'PLO6' else [])
        entry = {
            'table_id': table, 'hand_label_human_assigned': 'H1',
            'variant': variant, 'hero_cards': hero,
            'board_by_street': {'flop': ['2c', '3d', '4h'], 'turn': '5s', 'river': '6c'},
            'actions': [
                {'street': 'preflop', 'actor': 'hero', 'action': 'call',
                 'amount': 20, 'source_pts_seconds': 1},
                {'street': 'flop', 'actor': 'villain_1', 'action': 'bet',
                 'amount': 50, 'source_pts_seconds': 3},
                {'street': 'flop', 'actor': 'hero', 'action': 'call',
                 'amount': 50, 'source_pts_seconds': 4},
            ],
            'pot_before_decision': 100, 'call_amount': 50, 'effective_stack': 300,
            'source_pts_start_seconds': 0, 'source_pts_end_seconds': 8,
            'source_pts_checked_by_human': True, 'reviewer_attestation': True,
            'opponent_range_notes': 'Synthetic hypothetical range',
            'notes': 'Not poker footage', 'confidence_subjective': .7,
        }
        row = {'table_id': table, 'hand_label_human_assigned': 'H1',
               'source_nominal_interval_seconds': [0, 8],
               'source_image_sha256s': ['a'*64], 'human_entry': entry,
               'status': 'structurally_complete_human_draft_unverified',
               'hand_reconstruction_verified': False,
               'ready_for_equity_or_ev': False,
               'automatic_clip_selection_authorized': False}
        draft = {'schema_version': 1,
                 'analysis_status': 'human_entered_hand_history_drafts_no_math',
                 'job_id': 'b'*32, 'source_sha256': self.source_sha,
                 'source_checklist_sha256': 'd'*64,
                 'timestamp_semantics': 'human_claimed_pts_not_independently_verified',
                 'hands': [row],
                 'counts': {'hands': 1, 'structurally_complete_unverified': 1, 'math_ready': 0},
                 'requires_source_video_reaudit': True,
                 'hand_start_or_end_pts_verified': False,
                 'hand_reconstruction_verified': False, 'ready_for_equity_or_ev': False,
                 'automatic_clip_selection_authorized': False}
        worksheet = {'schema_version': 1,
                     'analysis_status': 'manual_hypothetical_math_review_not_video_verified',
                     'job_id': draft['job_id'], 'recording_sha256_unverified': self.source_sha,
                     'source_draft_sha256': hashlib.sha256(encode(draft)).hexdigest(),
                     'tasks': [{
                         'table_id': table, 'hand_label_human_assigned': 'H1',
                         'source_human_entry_sha256': canonical_sha(entry),
                         'source_nominal_interval_seconds': [0, 8],
                         'source_status': row['status'],
                         'manual_scenario_draft': {'timestamp': None, 'human_confirmed': False},
                         'hand_reconstruction_verified': False,
                         'ready_for_equity_or_ev': False,
                         'automatic_clip_selection_authorized': False}],
                     'counts': {'hands': 1, 'hypothetical_calculations': 0},
                     'ready_for_equity_or_ev': False, 'hand_reconstruction_verified': False,
                     'automatic_clip_selection_authorized': False}
        filled = copy.deepcopy(worksheet)
        def field(value):
            return {'value': value, 'confidence': .8, 'source_timestamp': 4,
                    'source': 'independent_manual_video_review', 'human_confirmed': True}
        filled['tasks'][0]['manual_scenario_draft'] = {
            'timestamp': 4, 'human_confirmed': True, 'observation_confidence': .8,
            'reviewed_fields': {
                'hero_cards': field(hero), 'board': field(['2c', '3d', '4h']),
                'observed_action': field('call'), 'pot_before_action': field(100),
                'call_amount': field(50)},
            'call_range': [{'cards': ['9c', '9d', '8h', '7s', '6d'], 'weight': 1.0}],
            'fold_probability': None, 'monte_carlo_trials': 80,
            'monte_carlo_seed': 12345, 'model_notes': 'Synthetic range',
            'model_assumptions': {'heads_up': True, 'all_in_no_future_betting': True,
                                  'no_rake': True, 'no_side_pots': True, 'no_icm': True,
                                  'hero_extra_chips': None, 'villain_extra_chips_if_called': None},
        }
        result = {'table_id': table, 'hand_label_human_assigned': 'H1',
                  'source_human_entry_sha256': canonical_sha(entry),
                  'status': 'hypothetical_only_not_video_verified', 'variant': variant,
                  'observed_action_assumed': 'call', 'equity': .35,
                  'equity_sampling_ci95': [.2, .5], 'ev_vs_fold_zero': 2.5,
                  'ev_sampling_ci95': [-20.0, 25.0], 'trials': 80,
                  'seed': 12345, 'wins': 28, 'ties': 0, 'losses': 52,
                  'opponent_range_combinations': 1,
                  'model_notes': 'Synthetic range',
                  'model_limitations': 'Monte Carlo CI only, not range or model uncertainty.',
                  'human_confidence_subjective': .8,
                  'hand_reconstruction_verified': False,
                  'strategic_error_established': False,
                  'automatic_clip_selection_authorized': False}
        math = {'schema_version': 1,
                'analysis_status': 'hypothetical_math_from_unverified_hand_drafts',
                'job_id': draft['job_id'],
                'source_draft_sha256': hashlib.sha256(encode(draft)).hexdigest(),
                'source_worksheet_sha256': canonical_sha(worksheet),
                'source_filled_worksheet_sha256': canonical_sha(filled),
                'results': [result],
                'counts': {'total': 1, 'hypothetical': 1, 'blocked': 0, 'skipped': 0},
                'ready_for_equity_or_ev': False, 'hand_reconstruction_verified': False,
                'strategic_error_established': False,
                'automatic_clip_selection_authorized': False}
        sidecar = copy.deepcopy(self.sidecar)
        sidecar['selection']['table_id'] = table
        audit = copy.deepcopy(self.audit)
        audit['table_id_human_selected'] = table
        audit['selection_sha256'] = canonical_sha(sidecar['selection'])
        return [sidecar, audit, draft, worksheet, filled, math]

    def build(self, objects, *, table=1, label='H1'):
        names = ('sidecar', 'audit', 'draft', 'worksheet', 'filled', 'math')
        hashes = {n: hashlib.sha256(encode(o)).hexdigest() for n, o in zip(names, objects)}
        from offline_manual_clip_export import probe
        return build_link(probe(self.source), probe(self.clip_path), *objects,
                          table, label, source_sha=self.source_sha,
                          clip_sha=self.clip_sha, file_shas=hashes)

    def test_synthetic_end_to_end_published_shapes(self):
        objects = self.make_inputs()
        result = self.build(objects)
        self.assertEqual(result['status'], 'manual_clip_linked_to_hypothetical_math_not_video_verified')
        self.assertEqual(result['decision_timestamp_seconds_human'], 4)
        self.assertEqual(result['hypothetical_math']['monte_carlo_seed'], 12345)
        self.assertEqual(result['clip_mp4_sha256'], self.clip_sha)
        self.assertFalse(result['math_result_independently_recomputed'])
        self.assertFalse(result['strategic_error_established'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['hand_reconstruction_verified'])
        self.assertFalse(result['hand_start_or_end_pts_verified'])

    def test_real_file_export_and_no_overwrite(self):
        objs = self.make_inputs()
        names = ('sidecar', 'audit', 'draft', 'worksheet', 'filled', 'math')
        paths = []
        for name, obj in zip(names, objs):
            p = self.base / f'persist_{name}.json'
            p.write_bytes(encode(obj))
            paths.append(p)
        target = self.base / 'linked_provenance.json'
        result = export_link(self.source, self.clip_path, *paths, 1, 'H1', target)
        self.assertEqual(json.loads(target.read_text()), result)
        with self.assertRaises(ValueError):
            export_link(self.source, self.clip_path, *paths, 1, 'H1', target)

    def test_plo6_and_four_manual_tables(self):
        for table in (1, 2, 3, 4):
            with self.subTest(table=table):
                objs = self.make_inputs(variant='PLO6', table=table)
                self.assertEqual(self.build(objs, table=table)['hypothetical_math']['variant'], 'PLO6')

    def test_reject_cross_table_identity(self):
        with self.assertRaisesRegex(ValueError, 'identity|table'):
            self.build(self.make_inputs(), table=2)

    def test_reject_missing_hand(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.build(self.make_inputs(), label='other')

    def test_reject_modified_math_source_hash(self):
        objs = self.make_inputs()
        objs[5]['source_draft_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'Math result provenance'):
            self.build(objs)

    def test_reject_math_automation_promotion(self):
        objs = self.make_inputs()
        objs[5]['results'][0]['automatic_clip_selection_authorized'] = True
        with self.assertRaisesRegex(ValueError, 'authorization'):
            self.build(objs)

    def test_reject_decision_outside_clip(self):
        objs = self.make_inputs()
        form = objs[4]['tasks'][0]['manual_scenario_draft']
        form['timestamp'] = 7
        for field in form['reviewed_fields'].values():
            field['source_timestamp'] = 7
        objs[5]['source_filled_worksheet_sha256'] = canonical_sha(objs[4])
        with self.assertRaisesRegex(ValueError, 'Decision not in|Clip does not contain'):
            self.build(objs)

    def test_reject_protected_filled_metadata_change(self):
        objs = self.make_inputs()
        objs[4]['tasks'][0]['table_id'] = 2
        objs[5]['source_filled_worksheet_sha256'] = canonical_sha(objs[4])
        with self.assertRaisesRegex(ValueError, 'protected metadata'):
            self.build(objs)

    def test_reject_math_seed_mismatch(self):
        objs = self.make_inputs()
        objs[5]['results'][0]['seed'] = 99
        with self.assertRaisesRegex(ValueError, 'parameters'):
            self.build(objs)

    def test_reject_reviewed_cards_mismatch(self):
        objs = self.make_inputs()
        objs[4]['tasks'][0]['manual_scenario_draft']['reviewed_fields']['hero_cards']['value'] = ['2d']
        objs[5]['source_filled_worksheet_sha256'] = canonical_sha(objs[4])
        with self.assertRaisesRegex(ValueError, 'contradicts'):
            self.build(objs)

    def test_reject_clip_digest_mismatch(self):
        objs = self.make_inputs()
        objs[0]['output_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.build(objs)

    def test_reject_audit_selection_mismatch(self):
        objs = self.make_inputs()
        objs[1]['selection_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'PTS audit provenance'):
            self.build(objs)

    def test_reject_audit_claiming_hand_verified(self):
        objs = self.make_inputs()
        objs[1]['hand_start_or_end_pts_verified'] = True
        with self.assertRaisesRegex(ValueError, 'authorization'):
            self.build(objs)

    def test_reject_invalid_sampling_ci(self):
        objs = self.make_inputs()
        objs[5]['results'][0]['equity_sampling_ci95'] = [0.9, 0.2]
        with self.assertRaisesRegex(ValueError, 'sampling interval'):
            self.build(objs)

    def test_reject_invalid_monte_carlo_outcomes(self):
        objs = self.make_inputs()
        objs[5]['results'][0]['wins'] = 81
        with self.assertRaisesRegex(ValueError, 'outcomes'):
            self.build(objs)

    def test_reject_clip_not_overlapping_hand(self):
        objs = self.make_inputs()
        objs[2]['hands'][0]['human_entry']['source_pts_start_seconds'] = 6
        objs[2]['hands'][0]['human_entry']['source_pts_end_seconds'] = 8
        with self.assertRaises(ValueError):
            self.build(objs)

    def test_duplicate_json_keys_blocked(self):
        p = self.base / 'duplicate_keys.json'
        p.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            load(p)

    def test_symlink_json_blocked(self):
        p = self.base / 'symlink.json'
        p.symlink_to(self.sel_path)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            load(p)

    def test_no_input_output_overlap(self):
        paths = [self.base / f'overlap_{n}.json' for n in ('sidecar', 'audit', 'draft', 'worksheet', 'filled', 'math')]
        for p, obj in zip(paths, self.make_inputs()):
            p.write_bytes(encode(obj))
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            export_link(self.source, self.clip_path, *paths, 1, 'H1', paths[-1])


if __name__ == '__main__':
    unittest.main()
