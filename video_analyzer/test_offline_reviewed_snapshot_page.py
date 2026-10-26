"""Synthetic tests for the offline reviewed-snapshot comparison page."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from offline_hand_correction_overlay import digest
from offline_hand_reviewed_snapshot import build_snapshot
from offline_reviewed_snapshot_page import export_page, render_page, validate_chain
from test_offline_hand_reviewed_snapshot import case, add_proposal


class ReviewedPageTests(unittest.TestCase):
    def setUp(self):
        self.draft, self.overlay, self.review = case()
        self.snapshot = build_snapshot(self.draft, self.overlay, self.review)

    def render(self):
        lookup, snap = validate_chain(self.draft, self.overlay, self.review, self.snapshot)
        return render_page(self.draft, snap, lookup)

    def test_original_and_candidate_side_by_side(self):
        page = self.render()
        self.assertIn('Original', page)
        self.assertIn('Candidato revisado', page)
        self.assertIn('As', page)
        self.assertIn('null', page)

    def test_not_math_ready(self):
        self.assertIn('Nenhuma mão está liberada para equity, EV', self.render())

    def test_csp_blocks_network(self):
        page = self.render()
        self.assertIn("default-src 'none'", page)
        self.assertNotIn('<script', page)
        self.assertNotIn('http://', page)

    def test_escape_untrusted_notes(self):
        self.draft['hands'][0]['human_entry']['notes'] = '<img src=x onerror=alert(1)>'
        self._rebuild()
        page = self.render()
        self.assertIn('&lt;img', page)
        self.assertNotIn('<img', page)

    def test_tampered_snapshot_rejected(self):
        self.snapshot['hands'][0]['human_entry_candidate']['hero_cards'] = ['2s'] * 5
        with self.assertRaisesRegex(ValueError, 'Snapshot differs'):
            self.render()

    def test_tampered_snapshot_gate_rejected(self):
        self.snapshot['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            self.render()

    def test_changed_review_rejected(self):
        self.review['decisions'][0]['reason'] = 'Other reviewer reason'
        with self.assertRaises(ValueError):
            self.render()

    def test_changed_overlay_rejected(self):
        self.overlay['counts']['pending'] = 123
        with self.assertRaises(ValueError):
            self.render()

    def test_noop_hand_visible(self):
        self.draft['hands'].append(copy.deepcopy(self.draft['hands'][0]))
        self.draft['hands'][1]['table_id'] = 2
        self.draft['hands'][1]['human_entry']['table_id'] = 2
        self._rebuild()
        page = self.render()
        self.assertIn('Mesa 2', page)
        self.assertIn('Nenhuma correção aceita', page)

    def test_rejected_correction_is_not_applied(self):
        self.review = add_proposal(self.draft, self.overlay, self.review, 'notes', 'Rejected', 'reject')
        self.snapshot = build_snapshot(self.draft, self.overlay, self.review)
        page = self.render()
        self.assertIn('1 rejeitada(s)', page)
        self.assertNotIn('Rejected', page)

    def test_file_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / p for p in ('draft.json', 'overlay.json', 'review.json', 'snapshot.json', 'review.html')]
            for path, value in zip(paths, (self.draft, self.overlay, self.review, self.snapshot)):
                path.write_text(json.dumps(value))
            result = export_page(*paths)
            self.assertEqual(result['hands'], 1)
            self.assertFalse(result['ready_for_equity_or_ev'])
            self.assertIn('Revisado', paths[-1].read_text())
            with self.assertRaises(ValueError): export_page(*paths)

    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / p for p in ('draft.json', 'overlay.json', 'review.json', 'snapshot.json', 'review.html')]
            for path, value in zip(paths, (self.draft, self.overlay, self.review, self.snapshot)):
                path.write_text(json.dumps(value))
            symlink = Path(tmp) / 'link.json'
            symlink.symlink_to(paths[0])
            with self.assertRaises(ValueError): export_page(symlink, *paths[1:])

    def test_reject_overlap_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / p for p in ('draft.json', 'overlay.json', 'review.json', 'snapshot.json')]
            for path, value in zip(paths, (self.draft, self.overlay, self.review, self.snapshot)):
                path.write_text(json.dumps(value))
            with self.assertRaises(ValueError): export_page(*paths, paths[0])

    def test_empty_hands_rejected(self):
        self.draft['hands'] = []
        self._rebuild()
        with self.assertRaises(ValueError):
            self.render()

    def test_deterministic_html(self):
        self.assertEqual(self.render(), self.render())

    def test_original_unchanged(self):
        original = copy.deepcopy(self.draft)
        self.render()
        self.assertEqual(self.draft, original)

    def _rebuild(self):
        # Rebind the proposal and independent review to the modified synthetic draft.
        from offline_hand_correction_overlay import build_overlay
        from offline_hand_independent_review import build_review
        from test_offline_hand_reviewed_snapshot import case
        if not self.draft['hands']:
            # Valid no-hands draft and no proposal are incompatible; use a
            # synthetic snapshot with no hands to exercise page's explicit gate.
            self.snapshot = {'hands': []}
            return
        correction = self.overlay['corrections'][0]
        submission = {'schema_version': 1, 'job_id': self.draft['job_id'],
                      'source_draft_sha256': digest(self.draft), 'reviewer_label': 'analista',
                      'corrections': [{k: correction[k] for k in ('table_id', 'hand_label_human_assigned',
                                     'field', 'expected_value_sha256', 'proposed_value',
                                     'reason', 'confidence_subjective')}]}
        self.overlay = build_overlay(self.draft, submission)
        self.review = build_review(self.draft, self.overlay, {
            'schema_version': 1, 'job_id': self.draft['job_id'],
            'source_draft_sha256': digest(self.draft), 'overlay_sha256': digest(self.overlay),
            'reviewer_label': 'independent reviewer',
            'decisions': [{'correction_sha256': digest(self.overlay['corrections'][0]),
                           'decision': 'accept', 'reason': 'Checked manually'}]})
        self.snapshot = build_snapshot(self.draft, self.overlay, self.review)


if __name__ == '__main__':
    unittest.main()
