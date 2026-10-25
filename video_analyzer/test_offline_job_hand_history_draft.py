"""Synthetic-only tests for manual hand-history draft validation (no math)."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from offline_job_hand_history_draft import (build_drafts, digest, export_drafts,
                                            validate_checklist)

FIXTURE = Path(__file__).parent / 'demo' / 'synthetic_reconstruction_checklist.json'


def checklist():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def hand(variant='PLO5'):
    return {
        'table_id': 1, 'hand_label_human_assigned': 'H1',
        'variant': variant,
        'hero_cards': ['As', 'Kh', 'Qd', 'Jc', 'Ts'] + (['9h'] if variant == 'PLO6' else []),
        'board_by_street': {'flop': ['2c', '3d', '4h'], 'turn': '5s', 'river': '6c'},
        'actions': [
            {'street': 'preflop', 'actor': 'hero', 'action': 'call',
             'amount': 20, 'source_pts_seconds': 1.0},
            {'street': 'flop', 'actor': 'villain_1', 'action': 'bet',
             'amount': 50, 'source_pts_seconds': 3.0},
            {'street': 'flop', 'actor': 'hero', 'action': 'fold',
             'amount': 0, 'source_pts_seconds': 4.0},
        ],
        'pot_before_decision': 100, 'call_amount': 50, 'effective_stack': 300,
        'source_pts_start_seconds': 0.0, 'source_pts_end_seconds': 10.0,
        'source_pts_checked_by_human': True, 'reviewer_attestation': True,
        'opponent_range_notes': 'Hipótese declarada, sem validação estatística',
        'notes': 'Fixture sintética, sem vídeo real', 'confidence_subjective': 0.75,
    }


def submission(source, entry=None):
    return {'schema_version': 1, 'job_id': source['job_id'],
            'source_checklist_sha256': digest(source),
            'hands': [hand() if entry is None else entry]}


class DraftTests(unittest.TestCase):
    def test_plo5_draft_never_authorized(self):
        source = checklist()
        result = build_drafts(source, submission(source))
        self.assertEqual(result['counts']['structurally_complete_unverified'], 1)
        self.assertEqual(result['counts']['math_ready'], 0)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['hands'][0]['hand_reconstruction_verified'])

    def test_plo6_supported(self):
        source = checklist()
        result = build_drafts(source, submission(source, hand('PLO6')))
        self.assertEqual(result['hands'][0]['human_entry']['variant'], 'PLO6')

    def test_incomplete_hand_kept(self):
        source, entry = checklist(), hand()
        entry['hero_cards'] = None
        entry['board_by_street'] = {'flop': None, 'turn': None, 'river': None}
        entry['actions'] = []
        entry['source_pts_start_seconds'] = None
        entry['source_pts_end_seconds'] = None
        entry['source_pts_checked_by_human'] = False
        result = build_drafts(source, submission(source, entry))
        self.assertEqual(result['counts']['structurally_complete_unverified'], 0)
        self.assertIn('incomplete', result['hands'][0]['status'])

    def test_empty_checklist(self):
        source = checklist()
        source['tasks'] = []
        source['counts']['hands_to_review'] = 0
        result = build_drafts(source, {'schema_version': 1, 'job_id': source['job_id'],
                                      'source_checklist_sha256': digest(source), 'hands': []})
        self.assertEqual(result['counts']['hands'], 0)

    def test_four_tables_isolated(self):
        source = checklist()
        source['tasks'] = []
        entries = []
        for table in (4, 2, 1, 3):
            task = copy.deepcopy(checklist()['tasks'][0])
            task['table_id'] = table
            source['tasks'].append(task)
            entry = hand()
            entry['table_id'] = table
            entries.append(entry)
        source['counts']['hands_to_review'] = 4
        result = build_drafts(source, {'schema_version': 1, 'job_id': source['job_id'],
                                      'source_checklist_sha256': digest(source), 'hands': entries})
        self.assertEqual([h['table_id'] for h in result['hands']], [1, 2, 3, 4])

    def reject(self, change, message=None):
        source, entry = checklist(), hand()
        change(source, entry)
        with self.assertRaisesRegex(ValueError, message or '.'):
            build_drafts(source, submission(source, entry))

    def test_duplicate_card(self):
        self.reject(lambda s, h: h['hero_cards'].__setitem__(0, '2c'), 'Duplicate visible')

    def test_wrong_plo_count(self):
        self.reject(lambda s, h: h['hero_cards'].pop(), 'card list')

    def test_invalid_card_suit(self):
        self.reject(lambda s, h: h['hero_cards'].__setitem__(0, 'Ax'), 'card list')

    def test_invalid_variant(self):
        self.reject(lambda s, h: h.__setitem__('variant', 'NLHE'), 'variant')

    def test_turn_without_flop(self):
        self.reject(lambda s, h: h['board_by_street'].__setitem__('flop', None), 'Turn without flop')

    def test_river_without_turn(self):
        self.reject(lambda s, h: h['board_by_street'].__setitem__('turn', None), 'River without turn')

    def test_duplicate_board_card(self):
        self.reject(lambda s, h: h['board_by_street'].__setitem__('river', '2c'), 'Duplicate visible')

    def test_nan_amount(self):
        self.reject(lambda s, h: h.__setitem__('call_amount', float('nan')), 'chip amount')

    def test_bool_amount(self):
        self.reject(lambda s, h: h.__setitem__('call_amount', True), 'chip amount')

    def test_negative_amount(self):
        self.reject(lambda s, h: h['actions'][0].__setitem__('amount', -1), 'action amount')

    def test_fold_must_be_zero(self):
        self.reject(lambda s, h: h['actions'][2].__setitem__('amount', 10), 'action amount')

    def test_nonmonotonic_action_time(self):
        self.reject(lambda s, h: h['actions'][2].__setitem__('source_pts_seconds', 2), 'Nonmonotonic')

    def test_nonmonotonic_street(self):
        self.reject(lambda s, h: h['actions'][2].__setitem__('street', 'preflop'), 'Nonmonotonic')

    def test_action_outside_pts(self):
        self.reject(lambda s, h: h['actions'][0].__setitem__('source_pts_seconds', 12), 'action PTS')

    def test_missing_pts_for_claimed_check(self):
        def mutate(s, h):
            h['source_pts_start_seconds'] = None
            h['source_pts_end_seconds'] = None
        self.reject(mutate, 'PTS attestation')

    def test_pts_malformed(self):
        self.reject(lambda s, h: h.__setitem__('source_pts_end_seconds', 0), 'PTS interval')

    def test_reject_unknown_field(self):
        self.reject(lambda s, h: h.__setitem__('ready_for_equity_or_ev', True), 'hand fields')

    def test_reject_cross_table(self):
        self.reject(lambda s, h: h.__setitem__('table_id', 2), 'submitted hand')

    def test_reject_promoted_upstream_math(self):
        self.reject(lambda s, h: s.__setitem__('ready_for_equity_or_ev', True), 'authorization')

    def test_reject_populated_checklist(self):
        self.reject(lambda s, h: s['tasks'][0]['manual_reconstruction_template'].__setitem__('variant', 'PLO5'), 'populated')

    def test_reject_bad_count(self):
        self.reject(lambda s, h: s['counts'].__setitem__('hands_to_review', 999), 'counts')

    def test_reject_bad_submission_digest(self):
        source = checklist()
        data = submission(source)
        data['source_checklist_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'match'):
            build_drafts(source, data)

    def test_reject_duplicate_submitted_hand(self):
        source = checklist()
        data = submission(source)
        data['hands'].append(hand())
        with self.assertRaisesRegex(ValueError, 'count'):
            build_drafts(source, data)

    def test_export_no_overwrite(self):
        source = checklist()
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            a, b, out = [folder / name for name in ('checklist', 'submission', 'output')]
            a.write_text(json.dumps(source))
            b.write_text(json.dumps(submission(source)))
            result = export_drafts(a, b, out)
            self.assertEqual(json.loads(out.read_text())['counts'], result['counts'])
            with self.assertRaises(FileExistsError):
                export_drafts(a, b, out)

    def test_export_rejects_symlink(self):
        source = checklist()
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            a, b, link, out = [folder / n for n in ('checklist', 'submission', 'link', 'out')]
            a.write_text(json.dumps(source))
            b.write_text(json.dumps(submission(source)))
            link.symlink_to(a)
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                export_drafts(link, b, out)
            with self.assertRaisesRegex(ValueError, 'overlap'):
                export_drafts(a, b, link)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            a, b, out = [folder / n for n in ('checklist', 'submission', 'out')]
            a.write_text('{"schema_version":1,"schema_version":1}')
            b.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
                export_drafts(a, b, out)

    def test_source_change_during_validation(self):
        source = checklist()
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            a, b, out = [folder / n for n in ('checklist', 'submission', 'out')]
            a.write_text(json.dumps(source))
            b.write_text(json.dumps(submission(source)))
            original = build_drafts
            def mutate(c, s):
                a.write_text('{}')
                return original(c, s)
            with patch('offline_job_hand_history_draft.build_drafts', side_effect=mutate):
                with self.assertRaisesRegex(ValueError, 'changed'):
                    export_drafts(a, b, out)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
