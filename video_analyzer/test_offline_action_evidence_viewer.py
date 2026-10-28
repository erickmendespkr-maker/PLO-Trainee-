"""Synthetic, offline evidence-viewer tests. No real poker or live access."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from offline_action_evidence_viewer import build, sha


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\x11\x22\x33')) + chunk(b'IEND', b''))


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ocr_dir = self.root / 'ocr'; self.ocr_dir.mkdir()
        self.png = self.ocr_dir / 'roi_000.png'; self.png.write_bytes(png())
        self.ocr_path = self.ocr_dir / 'roi_ocr_proposals.json'
        self.review_path = self.root / 'review.json'
        self.draft_path = self.root / 'draft.json'
        self.timeline_path = self.root / 'timeline.json'
        self.output = self.root / 'output'
        self.ocr = {'schema_version': 1, 'analysis_status': 'offline_refined_roi_ocr_proposals_only',
                    'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
                    'proposals': [{'table_id': 1, 'field': 'action', 'frame_file': 'refine_000_000.jpg',
                                   'source_frame_sha256': 'a' * 64, 'decoded_source_pts_seconds': 4.0,
                                   'roi_png': 'roi_000.png', 'roi_png_sha256': sha(self.png),
                                   'raw_ocr_text': 'CALL', 'parsed_candidate': None}]}
        self.review = {'analysis_status': 'offline_human_reviewed_ocr_observations_only',
                       'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
                       'observations': [{'proposal_index': 0, 'table_id': 1, 'field': 'action',
                                         'frame_file': 'refine_000_000.jpg',
                                         'source_frame_sha256': 'a' * 64,
                                         'decoded_source_pts_seconds': 4.0,
                                         'roi_png': 'roi_000.png', 'roi_png_sha256': sha(self.png),
                                         'raw_ocr_text': 'CALL', 'decision': 'confirmed',
                                         'normalized_value': 'call'}]}
        self.drafts = {'analysis_status': 'offline_reviewed_hand_drafts_only',
                       'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
                       'source_boundaries_sha256': 'b' * 64,
                       'hands': [{'hand_id': 'H1', 'table_id': 1, 'variant': 'PLO5',
                                  'start_seconds': 0, 'end_seconds': 10,
                                  'observation_indices': [0], 'unresolved_indices': [],
                                  'reviewed_fields': {'action': [{'proposal_index': 0,
                                                                  'timestamp_seconds': 4.0,
                                                                  'value': 'call', 'review': 'confirmed'}]}}]}
        self.timeline = {'schema_version': 1, 'analysis_status': 'offline_action_bet_evidence_only',
                         'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
                         'source_boundaries_sha256': 'b' * 64,
                         'hands': [{'hand_id': 'H1', 'table_id': 1, 'variant': 'PLO5',
                                    'start_seconds': 0, 'end_seconds': 10,
                                    'ready_for_equity_or_ev': False,
                                    'actor_and_betting_sequence_verified': False,
                                    'events': [{'proposal_index': 0, 'timestamp_seconds': 4.0,
                                                'field': 'action', 'value': 'call', 'review': 'confirmed',
                                                'board_phase_evidence': 'street_unknown'}]}]}
        self.save()

    def save(self):
        self.ocr_path.write_text(json.dumps(self.ocr), 'utf-8')
        self.review['source_roi_ocr_report_sha256'] = sha(self.ocr_path)
        self.review_path.write_text(json.dumps(self.review), 'utf-8')
        self.drafts['source_reviewed_report_sha256'] = sha(self.review_path)
        self.drafts['source_roi_ocr_report_sha256'] = sha(self.ocr_path)
        self.draft_path.write_text(json.dumps(self.drafts), 'utf-8')
        self.timeline['source_reviewed_report_sha256'] = sha(self.review_path)
        self.timeline['source_hand_drafts_sha256'] = sha(self.draft_path)
        self.timeline_path.write_text(json.dumps(self.timeline), 'utf-8')

    def run_build(self):
        return build(self.ocr_dir, self.review_path, self.draft_path, self.timeline_path, self.output)

    def fails(self):
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            self.run_build()
        self.assertFalse(self.output.exists())

    def test_browser_renders_events(self):
        try:
            import shutil
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('playwright unavailable')
        if not shutil.which('chromium'):
            self.skipTest('chromium unavailable')
        self.run_build()
        markup = (self.output / 'index.html').read_text('utf-8')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True,
                executable_path=shutil.which('chromium'), args=['--no-sandbox'])
            try:
                page = browser.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.set_content(markup)
                self.assertEqual(page.locator('section').count(), 1)
                self.assertEqual(page.locator('article').count(), 1)
                self.assertEqual(page.locator('article strong').inner_text(), 'action · call')
                self.assertFalse(errors)
            finally:
                browser.close()

    def test_valid_evidence_and_html(self):
        result = self.run_build()
        self.assertEqual(result['hands'][0]['events'][0]['roi_png'], 'assets/roi_000.png')
        self.assertEqual(sha(self.output / 'assets/roi_000.png'), sha(self.png))
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertIn('OCR bruto', (self.output / 'index.html').read_text())
        self.assertEqual(json.loads((self.output / 'action_roi_report.json').read_text()), result)

    def test_no_overwrite(self):
        self.run_build()
        with self.assertRaises(ValueError): self.run_build()

    def test_no_original_modification(self):
        original = {p: sha(p) for p in (self.png, self.ocr_path, self.review_path,
                                        self.draft_path, self.timeline_path)}
        self.run_build()
        self.assertEqual(original, {p: sha(p) for p in original})

    def test_missing_roi(self):
        self.png.unlink(); self.fails()

    def test_tampered_roi(self):
        self.png.write_bytes(png() + b'x'); self.fails()

    def test_symlink_roi(self):
        other = self.root / 'outside.png'; other.write_bytes(png())
        self.png.unlink(); self.png.symlink_to(other); self.fails()

    def test_roi_path_traversal(self):
        self.ocr['proposals'][0]['roi_png'] = '../outside.png'; self.save(); self.fails()

    def test_tampered_reviewed_value(self):
        self.review['observations'][0]['normalized_value'] = 'raise'; self.save(); self.fails()

    def test_forged_timeline_value(self):
        self.timeline['hands'][0]['events'][0]['value'] = 'raise'; self.save(); self.fails()

    def test_forged_timeline_timestamp(self):
        self.timeline['hands'][0]['events'][0]['timestamp_seconds'] = 5; self.save(); self.fails()

    def test_forged_draft_timestamp(self):
        self.drafts['hands'][0]['reviewed_fields']['action'][0]['timestamp_seconds'] = 5
        self.save(); self.fails()

    def test_wrong_table(self):
        self.timeline['hands'][0]['table_id'] = 2; self.save(); self.fails()

    def test_false_ev_flag(self):
        self.timeline['ready_for_equity_or_ev'] = True; self.save(); self.fails()

    def test_false_actor_verified(self):
        self.timeline['hands'][0]['actor_and_betting_sequence_verified'] = True
        self.save(); self.fails()

    def test_duplicate_json_keys(self):
        self.ocr_path.write_text('{"schema_version":1,"schema_version":1}')
        self.fails()

    def test_nan_json(self):
        self.timeline_path.write_text('{"x":NaN}')
        self.fails()

    def test_symlink_source(self):
        link = self.root / 'link.json'; link.symlink_to(self.timeline_path)
        with self.assertRaises(ValueError):
            build(self.ocr_dir, self.review_path, self.draft_path, link, self.output)

    def test_output_inside_ocr(self):
        with self.assertRaises(ValueError):
            build(self.ocr_dir, self.review_path, self.draft_path,
                  self.timeline_path, self.ocr_dir / 'unsafe')

    def test_xss_raw_ocr_escaped(self):
        self.ocr['proposals'][0]['raw_ocr_text'] = '</script><script>alert(1)</script>'
        self.review['observations'][0]['raw_ocr_text'] = '</script><script>alert(1)</script>'
        self.save()
        self.run_build()
        page = (self.output / 'index.html').read_text()
        self.assertNotIn('</script><script>alert(1)</script>', page)
        self.assertIn('\\u003c/script>', page)

    def test_four_tables(self):
        for i in (2, 3, 4):
            h = copy.deepcopy(self.drafts['hands'][0]); h['hand_id'] = f'H{i}'
            h['table_id'] = i; h['observation_indices'] = []; h['reviewed_fields'] = {}
            self.drafts['hands'].append(h)
            t = copy.deepcopy(self.timeline['hands'][0]); t['hand_id'] = f'H{i}'
            t['table_id'] = i; t['events'] = []
            self.timeline['hands'].append(t)
        self.save()
        self.assertEqual(len(self.run_build()['hands']), 4)

    def test_missing_timeline_event(self):
        self.timeline['hands'][0]['events'] = []; self.save(); self.fails()

    def test_ocr_timestamp_mismatch(self):
        self.ocr['proposals'][0]['decoded_source_pts_seconds'] = 3
        self.save(); self.fails()

    def test_rejected_observation_cannot_be_event(self):
        self.review['observations'][0]['decision'] = 'rejected'
        self.review['observations'][0]['normalized_value'] = None
        self.save(); self.fails()


if __name__ == '__main__': unittest.main()
