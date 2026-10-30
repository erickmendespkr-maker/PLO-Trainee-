"""Synthetic-only tests for the offline geometry editor (not poker recognition)."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import offline_table_roi_editor as editor
import offline_table_roi_sampler as sampler
from test_offline_table_roi_sampler import template


class RoiEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.frame = self.root / 'frame.png'
        Image.new('RGB', (1280, 720), '#263244').save(self.frame)
        self.tpl = template()
        self.tpl_path = self.root / 'template.json'
        self.tpl_path.write_text(json.dumps(self.tpl), encoding='utf-8')
        self.out = self.root / 'editor.html'

    def tearDown(self):
        self.temp.cleanup()

    def test_self_contained_html_and_no_network(self):
        html = editor.create(self.frame, self.tpl)
        self.assertIn('data:image/png;base64,', html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn('Baixar template JSON revisado', html)
        self.assertIn('human', html)
        self.assertNotIn('http://', html)
        self.assertNotIn('https://', html)

    def test_cli_and_exclusive_output(self):
        self.assertEqual(editor.main([str(self.frame), str(self.tpl_path), str(self.out)]), 0)
        self.assertTrue(self.out.is_file())
        with self.assertRaisesRegex(ValueError, 'distinct new'):
            editor.main([str(self.frame), str(self.tpl_path), str(self.out)])

    def test_invalid_geometry_rejected(self):
        tpl = copy.deepcopy(self.tpl)
        tpl['tables'][0]['roi']['x'] = .7
        with self.assertRaises(ValueError):
            editor.create(self.frame, tpl)

    def test_tiny_field_rejected(self):
        tpl = copy.deepcopy(self.tpl)
        tpl['tables'][0]['fields'][0]['roi']['w'] = .0001
        with self.assertRaises(ValueError):
            editor.create(self.frame, tpl)

    def test_bad_png_rejected(self):
        self.frame.write_text('not a png')
        with self.assertRaises(Exception):
            editor.create(self.frame, self.tpl)

    def test_output_alias_rejected(self):
        with self.assertRaisesRegex(ValueError, 'distinct new'):
            editor.main([str(self.frame), str(self.tpl_path), str(self.tpl_path)])

    def test_output_symlink_rejected(self):
        self.out.symlink_to(self.frame)
        with self.assertRaisesRegex(ValueError, 'distinct new'):
            editor.main([str(self.frame), str(self.tpl_path), str(self.out)])

    def test_html_injection_escaped(self):
        tpl = copy.deepcopy(self.tpl)
        tpl['tables'][0]['table_id'] = '</script><script>alert(1)</script>'
        html = editor.create(self.frame, tpl)
        self.assertNotIn('</script><script>alert', html)
        self.assertIn('\\u003c/script>', html)

    def test_browser_move_and_download_template(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('Playwright unavailable')
        editor.main([str(self.frame), str(self.tpl_path), str(self.out)])
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path='/usr/bin/chromium',
                                        args=['--no-sandbox'])
            context = browser.new_context(accept_downloads=True, viewport={'width': 1700, 'height': 1100})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.set_content(self.out.read_text(encoding='utf-8'))
            page.wait_for_selector('#frame')
            self.assertEqual(page.locator('#table option').count(), 4)
            page.select_option('#table', '0')
            page.select_option('#field', '0')
            canvas = page.locator('#frame')
            rect = canvas.bounding_box()
            # Selected field in table T1: center of global rect, then shift 20 px right.
            r = self.tpl['tables'][0]['roi']
            f = self.tpl['tables'][0]['fields'][0]['roi']
            x = rect['x'] + rect['width'] * (r['x'] + r['w'] * (f['x'] + f['w'] / 2))
            y = rect['y'] + rect['height'] * (r['y'] + r['h'] * (f['y'] + f['h'] / 2))
            page.mouse.move(x,y); page.mouse.down(); page.mouse.move(x+20,y,steps=4); page.mouse.up()
            with page.expect_download() as download_info:
                page.locator('#download').click()
            download = download_info.value
            saved = self.root / 'edited.json'
            download.save_as(str(saved))
            edited = json.loads(saved.read_text())
            self.assertEqual(edited['status'], self.tpl['status'])
            self.assertGreater(edited['tables'][0]['fields'][0]['roi']['x'], f['x'])
            clips = {f'H{i}': {'table_id': t['table_id']} for i,t in enumerate(edited['tables'])}
            sampler.validate_template(edited, clips, 1280, 720)
            self.assertFalse(errors, errors)
            browser.close()


if __name__ == '__main__':
    unittest.main()
