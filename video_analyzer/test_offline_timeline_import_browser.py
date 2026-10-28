"""Offline browser -> JSON import -> hand draft round-trip with synthetic video."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_reviewed_hand_drafts import build as build_drafts
from offline_hand_timeline_review import build as build_timeline
from offline_boundary_annotation_import import build as import_boundaries


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False) + '\n', encoding='utf8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BrowserIntegration(unittest.TestCase):
    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('playwright not installed')
        if not shutil.which('ffmpeg') or not shutil.which('chromium'):
            self.skipTest('FFmpeg or Chromium unavailable')
        self.playwright = sync_playwright
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reviewed = self.root/'reviewed.json'
        write(self.reviewed, {'schema_version': 1,
              'analysis_status': 'offline_human_reviewed_ocr_observations_only',
              'source_roi_ocr_report_sha256': 'a'*64,
              'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
              'observations': [{'proposal_index': 0, 'table_id': 1,
                 'decoded_source_pts_seconds': 2, 'field': 'pot',
                 'decision': 'confirmed', 'normalized_value': '125.00',
                 'source_frame_sha256': 'b'*64, 'roi_png_sha256': 'c'*64}]})
        boundaries = self.root/'boundaries.json'
        write(boundaries, {'schema_version': 1, 'reviewed_report_sha256': sha(self.reviewed),
              'hands': [{'hand_id': 'H1', 'table_id': 1, 'variant': 'PLO5',
                         'start_seconds': 0, 'end_seconds': 6, 'note': 'Synthetic'}]})
        build_drafts(self.reviewed, boundaries, self.root/'drafts')
        self.drafts = self.root/'drafts'/'hand_drafts.json'
        build_timeline(self.drafts, self.root/'timeline')
        self.html = (self.root/'timeline'/'hand_timeline_review.html').read_text('utf8')
        self.video = self.root/'synthetic.mp4'
        p = subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                            'color=c=blue:s=160x90:r=2','-t','8',
                            '-c:v','libx264','-pix_fmt','yuv420p','-y',str(self.video)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def browser(self):
        pw = self.playwright().start()
        self.addCleanup(pw.stop)
        browser = pw.chromium.launch(headless=True, executable_path=shutil.which('chromium'),
                                     args=['--no-sandbox'])
        self.addCleanup(browser.close)
        page = browser.new_page(accept_downloads=True)
        page.set_content(self.html)
        return page

    def test_synthetic_video_and_export_import_rebuild(self):
        page = self.browser()
        page.locator('#file').set_input_files(str(self.video))
        page.wait_for_timeout(500)
        self.assertGreaterEqual(page.locator("video").evaluate("v => v.readyState"), 1)
        page.locator('section button').first.click()
        page.locator('input[type=number]').first.fill('1')
        page.locator('select').select_option('corrected')
        page.locator('textarea').fill('Reviewed recorded clip; synthetic correction')
        with page.expect_download() as info:
            page.locator('#export').click()
        annotations = self.root/'annotations.json'
        info.value.save_as(annotations)
        output, audit = import_boundaries(self.drafts, annotations, self.reviewed, self.root/'imported')
        self.assertEqual(output['hands'][0]['start_seconds'], 1)
        self.assertTrue(audit['annotations'][0]['changed'])
        rebuilt = build_drafts(self.reviewed, self.root/'imported'/'revised_boundaries.json',
                               self.root/'rebuilt')
        self.assertEqual(rebuilt['hands'][0]['start_seconds'], 1)
        self.assertFalse(rebuilt['ready_for_equity_or_ev'])
        self.assertFalse(rebuilt['hands_reconstructed'])

    def test_pending_edit_blocked_in_browser(self):
        page = self.browser()
        page.locator('input[type=number]').first.fill('1')
        alerts = []
        page.on('dialog', lambda dialog: (alerts.append(dialog.message), dialog.dismiss()))
        page.locator('#export').click()
        self.assertTrue(alerts)
        self.assertIn('Corrigir', alerts[0])

    def test_corrected_without_change_blocked_in_browser(self):
        page = self.browser()
        page.locator('select').select_option('corrected')
        page.locator('textarea').fill('Explanation')
        alerts = []
        page.on('dialog', lambda dialog: (alerts.append(dialog.message), dialog.dismiss()))
        page.locator('#export').click()
        self.assertTrue(alerts)
        self.assertIn('somente quando houver alteração', alerts[0])


if __name__ == '__main__':
    unittest.main()
