"""Synthetic, local-only tests for static offline PLO review HTML (Cycle 113)."""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from offline_clip_review_page import (export_page, read_json, render, validate_link,
                                      validate_visual)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class ReviewPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.clip = cls.root / 'clip sample.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=10:duration=2',
                        '-an', '-c:v', 'mpeg4', '-y', str(cls.clip)],
                       check=True, capture_output=True, timeout=30)
        cls.clip_bytes = cls.clip.read_bytes()
        cls.clip_sha = sha_bytes(cls.clip_bytes)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.temp_case = tempfile.TemporaryDirectory(dir=self.root)
        self.base = Path(self.temp_case.name)
        self.clip_copy = self.base / self.clip.name
        self.clip_copy.write_bytes(self.clip_bytes)
        self.link = self.make_link()
        self.link_path = self.base / 'link.json'
        self.output = self.base / 'review.html'
        self.visual = self.make_visual()
        self.visual_path = self.base / 'visual.json'

    def tearDown(self):
        self.temp_case.cleanup()

    def make_link(self, variant='PLO5', table=1):
        return {
            'schema_version': 1,
            'status': 'manual_clip_linked_to_hypothetical_math_not_video_verified',
            'job_id': 'b'*32, 'table_id': table,
            'hand_label_human_assigned': 'H1',
            'source_recording_sha256': 'a'*64,
            'clip_mp4_sha256': self.clip_sha,
            'input_json_sha256': {name: 'c'*64 for name in
                                  ('sidecar', 'audit', 'draft', 'worksheet', 'filled', 'math')},
            'clip_selection_seconds_human': [3.5, 5.5],
            'decision_timestamp_seconds_human': 4.0,
            'hand_interval_seconds_human_claimed': [0, 8],
            'frame_pts_audit_within_tolerance_observed': True,
            'hypothetical_math': {
                'action_assumed': 'call', 'variant': variant,
                'equity': .35, 'equity_sampling_ci95': [.2, .5],
                'ev_vs_fold_zero': 2.5, 'ev_sampling_ci95': [-20.0, 25.0],
                'monte_carlo_trials': 80, 'monte_carlo_seed': 12345,
                'opponent_range_combinations': 1,
                'model_notes': 'Synthetic range only',
                'model_limitations': 'Heads-up all-in; no rake; sampling CI only.',
                'human_confidence_subjective': .8,
            },
            'clip_and_math_linked_by_manual_identifiers': True,
            'math_result_independently_recomputed': False,
            'hand_start_or_end_pts_verified': False,
            'hand_reconstruction_verified': False,
            'strategic_error_established': False,
            'automatic_clip_selection_authorized': False,
            'warning': 'Not independently verified against original video.'
        }

    def make_visual(self):
        return {
            'schema_version': 1,
            'status': 'sampled_visual_similarity_only_not_pts_or_hand_verified',
            'source_sha256': 'a'*64, 'clip_sha256': self.clip_sha,
            'selection_sha256': 'd'*64, 'table_id_human_selected': 1,
            'samples': [
                {'requested_clip_second': sec, 'clip_decoded_gray_sha256': 'e'*64,
                 'best_candidate': {'normalized_gray_mae': mae}}
                for sec, mae in ((.2, .01), (1, .02), (1.8, .03))
            ],
            'mean_best_normalized_gray_mae': .02,
            'actual_decoded_frame_pts_measured': False,
            'frame_exact_export_verified': False,
            'hand_start_or_end_pts_verified': False,
            'hand_reconstruction_verified': False,
            'strategic_error_established': False,
            'automatic_clip_selection_authorized': False,
        }

    def write(self, obj=None, visual=False):
        self.link_path.write_text(json.dumps(self.link if obj is None else obj), encoding='utf-8')
        if visual:
            self.visual_path.write_text(json.dumps(self.visual), encoding='utf-8')

    def run_export(self, visual=False):
        return export_page(self.clip_copy, self.link_path, self.output,
                           self.visual_path if visual else None)

    def test_real_mp4_generates_read_only_page(self):
        self.write()
        out = self.run_export()
        self.assertEqual(out['status'], 'offline_read_only_review_not_video_verified')
        self.assertFalse(out['visual_spot_check_included'])
        content = self.output.read_text()
        self.assertIn('clip%20sample.mp4', content)
        self.assertIn('PLO5', content)
        self.assertIn('80 simulações', content)
        self.assertIn('2.50 fichas', content)
        self.assertIn('Somente leitura', content)
        self.assertIn('não verificada no vídeo', content)
        self.assertEqual(self.clip_copy.read_bytes(), self.clip_bytes)
        doc = Elements()
        doc.feed(content)
        self.assertEqual(sum(tag == 'video' for tag, _ in doc.elements), 1)
        self.assertEqual(sum(tag == 'script' for tag, _ in doc.elements), 0)
        self.assertEqual(sum(tag == 'form' for tag, _ in doc.elements), 0)
        self.assertTrue(any(tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy'
                            for tag, attrs in doc.elements))

    def test_optional_visual_spot_check(self):
        self.write(visual=True)
        out = self.run_export(visual=True)
        self.assertTrue(out['visual_spot_check_included'])
        self.assertIn('0.020000', self.output.read_text())
        self.assertIn('sem prova de PTS exato', self.output.read_text())

    def test_four_tables_and_plo6(self):
        for table in range(1, 5):
            with self.subTest(table=table):
                link = self.make_link('PLO6', table)
                validate_link(link, self.clip_sha)
                self.assertIn(f'Mesa {table}', render(link, 'clip.mp4', link_sha='e'*64))

    def test_html_injection_escaped(self):
        self.link['hand_label_human_assigned'] = '<img src=x onerror=alert(1)>'
        # Limit remains valid; text must never become an element.
        self.link['hypothetical_math']['model_notes'] = '<script>alert(1)</script> & "quote"'
        self.write()
        self.run_export()
        text = self.output.read_text()
        self.assertNotIn('<script>', text)
        self.assertNotIn('<img', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn('&lt;img', text)
        doc = Elements(); doc.feed(text)
        self.assertFalse(any(tag in ('script', 'img') for tag, _ in doc.elements))

    def test_unsafe_filename_percent_encoded(self):
        new_name = 'clíp #1 & "a".mp4'
        renamed = self.base / new_name
        self.clip_copy.rename(renamed)
        self.write()
        export_page(renamed, self.link_path, self.output)
        text = self.output.read_text()
        self.assertIn('cl%C3%ADp%20%231%20%26%20%22a%22.mp4', text)
        self.assertNotIn('src="./clíp', text)

    def test_reject_clip_modified_after_manifest(self):
        self.write()
        self.clip_copy.write_bytes(self.clip_bytes + b'corrupt')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.run_export()
        self.assertFalse(self.output.exists())

    def test_reject_promoted_strategic_verdict(self):
        self.link['strategic_error_established'] = True
        self.write()
        with self.assertRaisesRegex(ValueError, 'verification'):
            self.run_export()

    def test_reject_automatic_selection(self):
        self.link['automatic_clip_selection_authorized'] = True
        self.write()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_recomputed_math_claim(self):
        self.link['math_result_independently_recomputed'] = True
        self.write()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_wrong_status(self):
        self.link['status'] = 'verified'
        self.write()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_missing_provenance_sha(self):
        self.link['input_json_sha256']['math'] = 'bad'
        self.write()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_decision_outside_clip(self):
        self.link['decision_timestamp_seconds_human'] = 6
        self.write()
        with self.assertRaisesRegex(ValueError, 'Decision outside'):
            self.run_export()

    def test_reject_nonfinite_equity(self):
        self.link['hypothetical_math']['equity'] = float('nan')
        self.write()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_bool_as_equity(self):
        self.link['hypothetical_math']['equity'] = True
        self.write()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_inverted_ci(self):
        self.link['hypothetical_math']['equity_sampling_ci95'] = [.9, .1]
        self.write()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_negative_trials(self):
        self.link['hypothetical_math']['monte_carlo_trials'] = -1
        self.write()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_duplicate_json_keys(self):
        self.link_path.write_text('{"status": "a", "status": "b"}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            self.run_export()

    def test_reject_visual_cross_table(self):
        self.visual['table_id_human_selected'] = 2
        self.write(visual=True)
        with self.assertRaisesRegex(ValueError, 'media/table'):
            self.run_export(visual=True)

    def test_reject_visual_wrong_clip_hash(self):
        self.visual['clip_sha256'] = '0'*64
        self.write(visual=True)
        with self.assertRaises(ValueError): self.run_export(visual=True)

    def test_reject_visual_false_frame_exact_promotion(self):
        self.visual['frame_exact_export_verified'] = True
        self.write(visual=True)
        with self.assertRaises(ValueError): self.run_export(visual=True)

    def test_reject_visual_mean_mismatch(self):
        self.visual['mean_best_normalized_gray_mae'] = .5
        self.write(visual=True)
        with self.assertRaisesRegex(ValueError, 'mean inconsistent'):
            self.run_export(visual=True)

    def test_reject_visual_out_of_clip_sample(self):
        self.visual['samples'][0]['requested_clip_second'] = 4
        self.write(visual=True)
        with self.assertRaises(ValueError): self.run_export(visual=True)

    def test_reject_symlink_clip(self):
        fake = self.base / 'fake.mp4'
        fake.symlink_to(self.clip_copy)
        self.write()
        with self.assertRaises(ValueError):
            export_page(fake, self.link_path, self.output)

    def test_reject_symlink_json(self):
        self.write()
        fake = self.base / 'fake.json'
        fake.symlink_to(self.link_path)
        with self.assertRaises(ValueError):
            export_page(self.clip_copy, fake, self.output)

    def test_reject_output_outside_clip_directory(self):
        self.write()
        with self.assertRaises(ValueError):
            export_page(self.clip_copy, self.link_path, self.root / 'outside.html')

    def test_reject_overwrite(self):
        self.write()
        self.run_export()
        original = self.output.read_bytes()
        with self.assertRaises(ValueError): self.run_export()
        self.assertEqual(self.output.read_bytes(), original)

    def test_reject_output_is_input(self):
        self.write()
        with self.assertRaises(ValueError):
            export_page(self.clip_copy, self.link_path, self.link_path)

    def test_reject_oversized_json(self):
        self.link_path.write_bytes(b' ' * (128 * 1024 + 1))
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_malformed_utf8(self):
        self.link_path.write_bytes(b'\xff')
        with self.assertRaises(ValueError): self.run_export()

    def test_cli_produces_page(self):
        self.write()
        module = Path(__file__).with_name('offline_clip_review_page.py')
        result = subprocess.run([sys.executable, str(module), str(self.clip_copy),
                                 str(self.link_path), str(self.output)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['clip_sha256'], self.clip_sha)
        self.assertTrue(self.output.exists())


if __name__ == '__main__':
    unittest.main()
