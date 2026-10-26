"""Synthetic offline tests for the bounded multi-hand review index."""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from offline_session_review_index import export_index, safe_name


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class SessionIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.media = Path(cls.tmp.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=10:duration=2',
                        '-an', '-c:v', 'mpeg4', '-y', str(cls.media)],
                       check=True, capture_output=True, timeout=30)
        cls.video = cls.media.read_bytes()
        cls.digest = hashlib.sha256(cls.video).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp_case = tempfile.TemporaryDirectory(dir=self.tmp.name)
        self.root = Path(self.tmp_case.name)
        self.manifest = self.root / 'session.json'
        self.target = self.root / 'session.html'
        self.entries = []
        self.add_hand(1, 'H1', 3.5)

    def tearDown(self):
        self.tmp_case.cleanup()

    def make_link(self, table, hand, start):
        return {
            'schema_version': 1,
            'status': 'manual_clip_linked_to_hypothetical_math_not_video_verified',
            'job_id': 'b'*32, 'table_id': table,
            'hand_label_human_assigned': hand,
            'source_recording_sha256': 'a'*64,
            'clip_mp4_sha256': self.digest,
            'input_json_sha256': {k: 'c'*64 for k in
                                  ('sidecar', 'audit', 'draft', 'worksheet', 'filled', 'math')},
            'clip_selection_seconds_human': [start, start + 2],
            'decision_timestamp_seconds_human': start + .5,
            'hand_interval_seconds_human_claimed': [start, start + 3],
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

    def add_hand(self, table, hand, start):
        stem = f't{table}_{hand}'
        clip = stem + '.mp4'
        link = stem + '.json'
        (self.root / clip).write_bytes(self.video)
        (self.root / link).write_text(json.dumps(self.make_link(table, hand, start)),
                                      encoding='utf-8')
        self.entries.append({'clip': clip, 'link': link})

    def write(self, label='Synthetic session'):
        self.manifest.write_text(json.dumps({'schema_version': 1,
                                             'session_label': label,
                                             'entries': self.entries}), encoding='utf-8')

    def build(self):
        self.write()
        return export_index(self.manifest, self.target)

    def test_real_synthetic_mp4_one_hand(self):
        result = self.build()
        self.assertEqual(result['hands'], 1)
        self.assertEqual(result['tables'], [1])
        doc = Tags()
        doc.feed(self.target.read_text())
        self.assertEqual(sum(tag == 'video' for tag, _ in doc.tags), 1)
        self.assertEqual(sum(tag == 'script' for tag, _ in doc.tags), 0)
        self.assertEqual(sum(tag == 'form' for tag, _ in doc.tags), 0)
        self.assertIn('não validad', self.target.read_text())

    def test_four_tables_and_chronological_order(self):
        for table, start in ((2, 15), (3, 11), (4, 9)):
            self.add_hand(table, f'H{table}', start)
        result = self.build()
        self.assertEqual(result['tables'], [1, 2, 3, 4])
        page = self.target.read_text()
        self.assertTrue(page.index('Mesa 1 ·') < page.index('Mesa 4 ·') <
                        page.index('Mesa 3 ·') < page.index('Mesa 2 ·'))

    def test_reject_fifth_table(self):
        self.add_hand(5, 'H5', 20)
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_mixed_source(self):
        self.add_hand(2, 'H2', 15)
        p = self.root / 't2_H2.json'
        d = json.loads(p.read_text())
        d['source_recording_sha256'] = 'f'*64
        p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_mixed_job(self):
        self.add_hand(2, 'H2', 15)
        p = self.root / 't2_H2.json'
        d = json.loads(p.read_text())
        d['job_id'] = 'f'*32
        p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_duplicate_hand(self):
        self.add_hand(1, 'H1', 10)
        # Repeated filenames are rejected, even if identities match.
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_duplicate_identity_different_files(self):
        self.add_hand(1, 'H2', 10)
        p = self.root / 't1_H2.json'
        d = json.loads(p.read_text())
        d['hand_label_human_assigned'] = 'H1'
        p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_corrupted_clip(self):
        (self.root / 't1_H1.mp4').write_bytes(self.video + b'changed')
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_unverified_claim(self):
        p = self.root / 't1_H1.json'
        d = json.loads(p.read_text())
        d['strategic_error_established'] = True
        p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_directory_traversal(self):
        self.entries[0]['clip'] = '../outside.mp4'
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_duplicate_json_keys(self):
        self.manifest.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
        with self.assertRaises(ValueError):
            export_index(self.manifest, self.target)

    def test_reject_nan(self):
        self.manifest.write_text('{"schema_version":NaN}', encoding='utf-8')
        with self.assertRaises(ValueError):
            export_index(self.manifest, self.target)

    def test_reject_overwrite(self):
        self.target.write_text('existing')
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(self.target.read_text(), 'existing')

    def test_reject_symlink_clip(self):
        clip = self.root / 't1_H1.mp4'
        clip.unlink()
        clip.symlink_to(self.media)
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_41_entries(self):
        self.entries *= 41
        with self.assertRaises(ValueError):
            self.build()

    def test_escapes_untrusted_text(self):
        p = self.root / 't1_H1.json'
        d = json.loads(p.read_text())
        d['hypothetical_math']['model_notes'] = '<script>alert(1)</script>'
        p.write_text(json.dumps(d))
        self.write('<img src=x onerror=alert(1)>')
        export_index(self.manifest, self.target)
        page = self.target.read_text()
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('&lt;img', page)
        doc = Tags()
        doc.feed(page)
        self.assertFalse(any(t in ('img', 'script') for t, _ in doc.tags))

    def test_filename_encoding(self):
        self.entries[0]['clip'] = 'clip sample.mp4'
        (self.root / 't1_H1.mp4').rename(self.root / 'clip sample.mp4')
        self.build()
        self.assertIn('clip%20sample.mp4', self.target.read_text())

    def test_reject_bad_optional_visual(self):
        visual = self.root / 'visual.json'
        visual.write_text('{}')
        self.entries[0]['visual'] = 'visual.json'
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_unknown_entry_keys(self):
        self.entries[0]['remote_url'] = 'https://example.com'
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_missing_clip(self):
        (self.root / 't1_H1.mp4').unlink()
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_empty_session(self):
        self.entries.clear()
        with self.assertRaises(ValueError):
            self.build()

    def test_reject_output_outside_manifest_folder(self):
        self.write()
        with self.assertRaises(ValueError):
            export_index(self.manifest, Path(self.tmp.name) / 'outside.html')

    def test_safe_name_contract(self):
        self.assertEqual(safe_name('clip 1.mp4', '.mp4'), 'clip 1.mp4')
        for name in ('../clip.mp4', 'clip/one.mp4', '.hidden.mp4', 'https://x.mp4',
                     'evil<script>.mp4', '', 'x.mov'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_name(name, '.mp4')


if __name__ == '__main__':
    unittest.main()
