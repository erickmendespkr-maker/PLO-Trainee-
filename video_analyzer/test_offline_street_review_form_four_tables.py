"""Four-table offline HTML -> downloaded review JSON -> Python validator integration."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import offline_ev_table_crop as media
import offline_street_evidence as street
import offline_street_human_review as human
import offline_street_review_form as form


class FourTableBrowserReview(unittest.TestCase):
    @unittest.skipUnless(shutil.which('chromium') and shutil.which('ffmpeg'),
                         'Chromium or FFmpeg unavailable')
    def test_four_tables_download_and_validate(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory(prefix='plo_four_table_form_') as folder:
            root = Path(folder)
            video = root / 'recorded.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                            '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=8',
                            '-t', '5', '-an', '-c:v', 'mpeg4', str(video)],
                           check=True, timeout=30, capture_output=True)
            hands = []
            for n in range(1, 5):
                hands.append({'table_id': f'T{n}', 'hand_id': f'H{n}',
                              'start_seconds': 0.1, 'end_seconds': 4.8,
                              'events': [
                                  {'timestamp_seconds': 0.2, 'street': 'preflop',
                                   'kind': 'hero_cards', 'value': ['AS', 'KH', 'QD', 'JC', 'TS'],
                                   'origin': 'manual_claim', 'confidence': 0.4},
                                  {'timestamp_seconds': 1.5, 'street': 'flop',
                                   'kind': 'board', 'value': ['2C', '3D', '4H'],
                                   'origin': 'ocr_proposal', 'confidence': 0.6}]})
            obs = root / 'observations.json'
            obs.write_text(json.dumps({'schema_version': 1,
                         'status': 'offline_unverified_street_observations',
                         'source_video_sha256': media.digest(video),
                         'variant': 'PLO5', 'hands': hands}), encoding='utf-8')
            ledger = root / 'street'; ledger.mkdir()
            street.export(video, obs, ledger)
            output = root / 'form'; output.mkdir()
            html = form.export(video, obs, ledger, output).read_text(encoding='utf-8')
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=shutil.which('chromium'),
                                            headless=True, args=['--no-sandbox'])
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                page.set_content(html)
                self.assertEqual(page.locator('.event').count(), 8)
                self.assertIn('0 de 8', page.locator('#progress').inner_text())
                page.locator('#reviewer').fill('four_table_review')
                for select in page.locator('.event select').all():
                    select.select_option('confirm')
                self.assertIn('8 de 8', page.locator('#progress').inner_text())
                with page.expect_download() as dl:
                    page.locator('#export').click()
                review = root / 'manual_review.json'
                dl.value.save_as(review)
                browser.close()
            reviewed = root / 'reviewed'; reviewed.mkdir()
            result = human.export(video, obs, ledger, review, reviewed)
            self.assertEqual(len(result['hands']), 4)
            self.assertEqual(sum(len(h['events']) for h in result['hands']), 8)
            self.assertFalse(result['automatic_ocr_math_authorization'])
            self.assertTrue(all(not h['automatic_math_authorization'] for h in result['hands']))


if __name__ == '__main__':
    unittest.main()
