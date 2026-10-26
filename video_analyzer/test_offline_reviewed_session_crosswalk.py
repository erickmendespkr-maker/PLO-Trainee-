"""Synthetic FFmpeg and review-chain tests for the offline clip ↔ hand crosswalk."""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from offline_hand_correction_overlay import build_overlay, digest
from offline_hand_independent_review import build_review
from offline_hand_reviewed_snapshot import build_snapshot
from offline_reviewed_session_crosswalk import export_crosswalk, load_crosswalk
from test_offline_hand_reviewed_snapshot import case


class HTMLTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class CrosswalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_dir = tempfile.TemporaryDirectory()
        cls.media = Path(cls.media_dir.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=10:duration=2',
                        '-an', '-c:v', 'mpeg4', '-y', str(cls.media)],
                       check=True, capture_output=True, timeout=30)
        cls.media_bytes = cls.media.read_bytes()
        cls.media_sha = hashlib.sha256(cls.media_bytes).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.media_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = [self.root / n for n in
                      ('session.json', 'draft.json', 'overlay.json', 'review.json',
                       'snapshot.json', 'crosswalk.html')]
        self.draft, self.overlay, self.review = case()
        self.snapshot = build_snapshot(self.draft, self.overlay, self.review)
        self.entries = []
        self.add_clip(1, 'h1', 0)

    def tearDown(self):
        self.tmp.cleanup()

    def link(self, table, hand, start):
        return {
            'schema_version': 1,
            'status': 'manual_clip_linked_to_hypothetical_math_not_video_verified',
            'job_id': self.draft['job_id'], 'table_id': table,
            'hand_label_human_assigned': hand,
            'source_recording_sha256': self.draft['source_sha256'],
            'clip_mp4_sha256': self.media_sha,
            'input_json_sha256': {k: 'c'*64 for k in
                                  ('sidecar', 'audit', 'draft', 'worksheet', 'filled', 'math')},
            'clip_selection_seconds_human': [start, start+2],
            'decision_timestamp_seconds_human': start+1,
            'hand_interval_seconds_human_claimed': [start, start+2],
            'frame_pts_audit_within_tolerance_observed': False,
            'hypothetical_math': {
                'action_assumed': 'call', 'variant': 'PLO5',
                'equity': .35, 'equity_sampling_ci95': [.2, .5],
                'ev_vs_fold_zero': 2.5, 'ev_sampling_ci95': [-20, 25],
                'monte_carlo_trials': 80, 'monte_carlo_seed': 12345,
                'opponent_range_combinations': 1,
                'model_notes': 'Synthetic range only',
                'model_limitations': 'Sampling CI only; no OCR confirmation.',
                'human_confidence_subjective': .8,
            },
            'clip_and_math_linked_by_manual_identifiers': True,
            'math_result_independently_recomputed': False,
            'hand_start_or_end_pts_verified': False,
            'hand_reconstruction_verified': False,
            'strategic_error_established': False,
            'automatic_clip_selection_authorized': False,
            'warning': 'Not independently verified against source video.'
        }

    def add_clip(self, table, hand, start):
        stem = f't{table}_{hand}'
        (self.root / (stem + '.mp4')).write_bytes(self.media_bytes)
        (self.root / (stem + '.json')).write_text(json.dumps(self.link(table, hand, start)))
        self.entries.append({'clip': stem + '.mp4', 'link': stem + '.json'})

    def write(self, label='Synthetic session'):
        self.paths[0].write_text(json.dumps({'schema_version': 1,
                                             'session_label': label,
                                             'entries': self.entries}))
        for p, value in zip(self.paths[1:5],
                            (self.draft, self.overlay, self.review, self.snapshot)):
            p.write_text(json.dumps(value))

    def run_export(self):
        self.write()
        return export_crosswalk(*self.paths)

    def rebuild(self):
        correction = self.overlay['corrections'][0]
        submission = {'schema_version': 1, 'job_id': self.draft['job_id'],
                      'source_draft_sha256': digest(self.draft), 'reviewer_label': 'analista',
                      'corrections': [{k: correction[k] for k in
                                       ('table_id', 'hand_label_human_assigned', 'field',
                                        'expected_value_sha256', 'proposed_value',
                                        'reason', 'confidence_subjective')}]}
        self.overlay = build_overlay(self.draft, submission)
        self.review = build_review(self.draft, self.overlay, {
            'schema_version': 1, 'job_id': self.draft['job_id'],
            'source_draft_sha256': digest(self.draft), 'overlay_sha256': digest(self.overlay),
            'reviewer_label': 'independent reviewer',
            'decisions': [{'correction_sha256': digest(self.overlay['corrections'][0]),
                           'decision': 'accept', 'reason': 'Checked manually'}]})
        self.snapshot = build_snapshot(self.draft, self.overlay, self.review)

    def test_valid_real_synthetic_mp4_and_chain(self):
        result = self.run_export()
        self.assertEqual((result['clips'], result['matched'], result['reviewed_without_clip']), (1, 1, 0))
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        doc = HTMLTags()
        doc.feed(self.paths[-1].read_text())
        self.assertEqual(sum(t == 'video' for t, _ in doc.tags), 1)
        self.assertFalse(any(t in ('script', 'iframe', 'form') for t, _ in doc.tags))
        self.assertIn('As', self.paths[-1].read_text())
        self.assertIn('não recalculados', self.paths[-1].read_text())

    def test_four_tables_and_unmatched_clips(self):
        for table in (2, 3, 4):
            self.add_clip(table, f'h{table}', table*3)
        result = self.run_export()
        self.assertEqual(result['clips'], 4)
        self.assertEqual(result['matched'], 1)
        self.assertIn('3 cortes sem revisão', self.paths[-1].read_text())

    def test_reviewed_hand_without_clip_is_listed(self):
        other = copy.deepcopy(self.draft['hands'][0])
        other['table_id'] = 2
        other['hand_label_human_assigned'] = 'h2'
        other['human_entry']['table_id'] = 2
        other['human_entry']['hand_label_human_assigned'] = 'h2'
        self.draft['hands'].append(other)
        self.rebuild()
        result = self.run_export()
        self.assertEqual(result['reviewed_without_clip'], 1)
        self.assertIn('Mãos revisadas sem corte', self.paths[-1].read_text())
        self.assertIn('Mesa 2 · h2', self.paths[-1].read_text())

    def test_human_interval_mismatch_is_warning_not_proof(self):
        entry = self.draft['hands'][0]['human_entry']
        entry['source_pts_start_seconds'] = 4
        entry['source_pts_end_seconds'] = 5
        self.rebuild()
        self.run_export()
        self.assertIn('Decisão fora do intervalo', self.paths[-1].read_text())
        self.assertIn('Corte sem sobreposição', self.paths[-1].read_text())

    def test_reject_wrong_source(self):
        link_path = self.root / 't1_h1.json'
        d = json.loads(link_path.read_text())
        d['source_recording_sha256'] = 'f'*64
        link_path.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, 'different jobs/recordings'):
            self.run_export()

    def test_reject_wrong_job(self):
        p = self.root / 't1_h1.json'
        d = json.loads(p.read_text()); d['job_id'] = 'f'*32
        p.write_text(json.dumps(d))
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_wrong_variant(self):
        p = self.root / 't1_h1.json'
        d = json.loads(p.read_text()); d['hypothetical_math']['variant'] = 'PLO6'
        p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, 'variant mismatch'): self.run_export()

    def test_reject_duplicate_hand(self):
        self.add_clip(2, 'h2', 4)
        p = self.root / 't2_h2.json'
        d = json.loads(p.read_text()); d['table_id'] = 1; d['hand_label_human_assigned'] = 'h1'
        p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, 'Repeated table/hand'): self.run_export()

    def test_reject_tampered_snapshot(self):
        self.snapshot['hands'][0]['human_entry_candidate']['hero_cards'] = ['As']*5
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_tampered_review(self):
        self.review['decisions'][0]['reason'] = 'different'
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_tampered_clip(self):
        (self.root / 't1_h1.mp4').write_bytes(self.media_bytes + b'tamper')
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_symlink_clip(self):
        p = self.root / 't1_h1.mp4'
        p.unlink(); p.symlink_to(self.media)
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_symlink_chain(self):
        self.write()
        p = self.paths[1]
        alias = self.root / 'alias.json'
        alias.symlink_to(p)
        with self.assertRaises(ValueError):
            export_crosswalk(self.paths[0], alias, *self.paths[2:])

    def test_reject_directory_traversal(self):
        self.entries[0]['clip'] = '../escape.mp4'
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_overwrite(self):
        self.paths[-1].write_text('keep me')
        with self.assertRaises(ValueError): self.run_export()
        self.assertEqual(self.paths[-1].read_text(), 'keep me')

    def test_reject_output_outside_session(self):
        self.write()
        with self.assertRaises(ValueError):
            export_crosswalk(*self.paths[:-1], Path(self.media_dir.name)/'outside.html')

    def test_reject_duplicate_json_keys(self):
        self.write()
        self.paths[0].write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): export_crosswalk(*self.paths)

    def test_reject_nan(self):
        self.write()
        self.paths[0].write_text('{"schema_version":NaN}')
        with self.assertRaises(ValueError): export_crosswalk(*self.paths)

    def test_escapes_untrusted_label_and_notes(self):
        p = self.root / 't1_h1.json'
        d = json.loads(p.read_text())
        d['hypothetical_math']['model_notes'] = '<script>alert(1)</script>'
        p.write_text(json.dumps(d))
        self.write('<img src=x onerror=alert(1)>')
        export_crosswalk(*self.paths)
        html = self.paths[-1].read_text()
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('&lt;img', html)
        doc = HTMLTags(); doc.feed(html)
        self.assertFalse(any(t in ('img', 'script') for t, _ in doc.tags))

    def test_no_41_entries(self):
        self.entries *= 41
        with self.assertRaises(ValueError): self.run_export()

    def test_duplicate_files_rejected(self):
        self.entries.append(dict(self.entries[0]))
        with self.assertRaises(ValueError): self.run_export()

    def test_deterministic_output(self):
        self.write()
        label, records, lookup, snapshot, hashes = load_crosswalk(*self.paths[:5])
        from offline_reviewed_session_crosswalk import render_crosswalk
        self.assertEqual(render_crosswalk(label, records, lookup, snapshot, hashes),
                         render_crosswalk(label, records, lookup, snapshot, hashes))


if __name__ == '__main__':
    unittest.main()
