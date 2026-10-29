"""Optional real Chromium smoke test: HTML loaded in memory (not file://)."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from offline_ev_assumptions_form import render, validate_assumptions


@unittest.skipUnless(importlib.util.find_spec('playwright') and shutil.which('chromium'),
                     'Playwright/Chromium unavailable')
class ChromiumSmoke(unittest.TestCase):
    def test_export_two_ranges_and_reject_invalid_grid(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True,
                                         executable_path=shutil.which('chromium'),
                                         args=['--no-sandbox', '--disable-dev-shm-usage'])
            try:
                page = browser.new_page(accept_downloads=True)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.set_content(render(), wait_until='load')
                self.assertEqual(page.locator('.hypothesis').count(), 1)
                self.assertTrue(page.locator('.call-combos-wrap').first.is_hidden())
                page.locator('#ack').check()
                page.locator('#add').click()
                self.assertEqual(page.locator('.hypothesis').count(), 2)
                second = page.locator('.hypothesis').nth(1)
                second.locator('.name').fill('range alternativo')
                second.locator('.call-kind').select_option('weighted_combos')
                self.assertTrue(second.locator('.call-combos-wrap').is_visible())
                second.locator('.call-combos').fill(json.dumps([{
                    'cards': ['7c', '8d', '9h', 'Ts', 'Jd', 'Qc'], 'weight': 1}]))
                with page.expect_download(timeout=15000) as info:
                    page.locator('#export').click()
                with tempfile.TemporaryDirectory() as tmp:
                    output = Path(tmp)/'assumptions.json'
                    info.value.save_as(output)
                    data = json.loads(output.read_text())
                    self.assertEqual(len(data['hypotheses']), 2)
                    self.assertEqual(data['hypotheses'][1]['call_model']['kind'],
                                     'weighted_combos')
                    self.assertEqual(validate_assumptions(data)['hypotheses'], 2)
                page.locator('#grid').fill('0.5, 0.2')
                page.locator('#export').click()
                self.assertIn('ordem crescente', page.locator('#message').inner_text())
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
