"""Offline browser-to-FFmpeg smoke test; requires Playwright, Chromium and FFmpeg.

Run: python -m unittest -v test_offline_visual_review_ui_smoke
No poker integration, network access, or GitHub Actions.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import offline_four_table_visual_timeline as core
import offline_manual_roi_review as review
import offline_visual_review_contract as contract
import offline_review_plan_clip_bridge as bridge

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(sync_playwright and shutil.which('chromium') and
                     shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'Requires Chromium, Playwright and FFmpeg')
class OfflineReviewSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'four_tables.mp4'
        filters = ','.join(
            f"drawbox=x={x}:y={y}:w=160:h=96:color=white:t=fill:enable='gte(t,{t})'"
            for x, y, t in [(0, 0, 2), (160, 0, 4), (0, 96, 6), (160, 96, 8)])
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'color=c=black:s=320x192:r=5:d=12',
                        '-vf', filters, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-preset', 'ultrafast', '-an', str(cls.video)],
                       check=True, capture_output=True, timeout=30)
        cls.rois = cls.root / 'rois.json'
        cls.rois.write_text(json.dumps({'schema_version': 1, 'tables': [
            {'table_id': f'table_{i+1}', 'normalized_rect': r}
            for i, r in enumerate(([0, 0, .5, .5], [.5, 0, .5, .5],
                                   [0, .5, .5, .5], [.5, .5, .5, .5]))]}))
        cls.timeline = cls.root / 'timeline.json'
        review.main(['analyze', str(cls.video), str(cls.rois), str(cls.timeline)])
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=shutil.which('chromium'),
                                             headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(accept_downloads=True)
        self.page = self.context.new_page()
        self.page.set_content((HERE / 'offline_visual_review_ui.html').read_text(encoding='utf-8'))

    def tearDown(self):
        self.context.close()

    def download(self, selector):
        with self.page.expect_download() as event:
            self.page.locator(selector).click()
        return json.loads(event.value.path().read_text(encoding='utf-8'))

    def test_no_remote_assets(self):
        self.assertEqual(0, self.page.locator('script[src],link[href],iframe,form').count())

    def test_human_review_to_mp4(self):
        self.page.locator('#videoFile').set_input_files(str(self.video))
        self.page.wait_for_function("document.querySelector('#video').readyState >= 1")
        self.page.locator('#timelineFile').set_input_files(str(self.timeline))
        self.page.wait_for_function("document.querySelectorAll('.candidate').length === 4")
        card = self.page.locator('.candidate').first
        card.locator('select').select_option('confirmed_hand')
        card.locator('input[aria-label^="ID da mão"]').fill('H001')
        card.locator('input[aria-label^="Início"]').fill('1.2')
        card.locator('input[aria-label^="Fim"]').fill('3.4')
        card.locator('textarea').fill('Corte escolhido manualmente; nenhuma ação inferida.')
        decisions = self.download('#exportReviews')
        explanations = self.download('#exportExplanations')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dp, ep, pp = (root / name for name in ('decisions.json', 'explanations.json', 'plan.json'))
            dp.write_text(json.dumps(decisions))
            ep.write_text(json.dumps(explanations))
            plan = contract.validate_bundle(self.video, self.rois, self.timeline, dp)
            pp.write_text(json.dumps(plan))
            result = bridge.export_bundle(self.video, pp, self.timeline, ep, root / 'clips')
            self.assertEqual(1, len(result['clips']))
            self.assertEqual(core.sha256_file(root / 'clips' / 'H001.mp4'),
                             result['clips'][0]['clip_sha256'])
            self.assertFalse(result['equity_or_ev_calculated'])
            self.assertFalse(result['automatic_hand_detection'])


if __name__ == '__main__':
    unittest.main()
