"""Synthetic-only tests for standalone human visual review form."""
import base64
import copy
import hashlib
import html
import json
import re
from pathlib import Path
import shutil
import tempfile
import unittest

from hand_action_review_form import export, render
from hand_action_visual_verdicts import build_template, verified_gallery, validate
from hand_action_review_gallery import export as export_gallery
import test_hand_action_review_gallery as gallery_tests


class OfflineFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gallery_tests.GalleryTests.setUpClass()
        cls.video = gallery_tests.GalleryTests.video
        cls.fixture = gallery_tests.GalleryTests(methodName='test_four_tables_gallery_and_html')
        cls.fixture.video = cls.video
        gallery_tests.GalleryTests.setUp(cls.fixture)
        export_gallery(cls.video, cls.fixture.nav_path, cls.fixture.review_path,
                       cls.fixture.stills, cls.fixture.gallery,
                       regions_json=cls.fixture.regions)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()
        gallery_tests.GalleryTests.tearDownClass()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copytree(self.fixture.root, self.root, dirs_exist_ok=True)
        self.nav = self.root / 'navigation.json'
        self.review = self.root / 'review.json'
        self.regions = self.root / 'regions.json'
        self.stills = self.root / 'stills'
        self.gallery = self.root / 'gallery'
        self.output = self.root / 'visual_review_form.html'
        self.kw = {'regions_json': self.regions}
        self.gallery_data, self.digest = verified_gallery(
            self.video, self.nav, self.review, self.stills, self.gallery, self.regions)
        self.template = build_template(self.gallery_data, self.digest)

    def test_four_tables_html_is_standalone_and_no_math(self):
        result = export(self.video, self.nav, self.review, self.stills,
                        self.gallery, self.output, **self.kw)
        self.assertEqual(result['rows'], 24)
        self.assertEqual(result['eligible'], 8)
        page = self.output.read_text()
        self.assertIn('Content-Security-Policy', page)
        self.assertIn("connect-src 'none'", html.unescape(page))
        self.assertIn('Exportar JSON de revisão', page)
        self.assertIn('Nenhum dado é enviado pela internet', page)
        self.assertIn('source_gallery_sha256', page)
        self.assertIn('ready_for_equity_or_ev', page)
        self.assertFalse(self.template['ready_for_equity_or_ev'])

    def test_csp_sha_matches_embedded_script(self):
        export(self.video, self.nav, self.review, self.stills,
               self.gallery, self.output, **self.kw)
        page = self.output.read_text()
        script = re.search(r'<script>([\s\S]*?)</script>', page).group(1)
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        self.assertIn("script-src 'sha256-" + digest + "'", html.unescape(page))
        self.assertEqual(page.count('<script>'), 1)
        self.assertNotIn('<script src=', page)

    def test_png_change_rejected_before_html_creation(self):
        png = next(self.stills.glob('*.png'))
        png.write_bytes(b'forged')
        with self.assertRaises(ValueError):
            export(self.video, self.nav, self.review, self.stills,
                   self.gallery, self.output, **self.kw)
        self.assertFalse(self.output.exists())

    def test_refuses_overwrite_or_write_inside_evidence(self):
        export(self.video, self.nav, self.review, self.stills,
               self.gallery, self.output, **self.kw)
        with self.assertRaises(ValueError):
            export(self.video, self.nav, self.review, self.stills,
                   self.gallery, self.output, **self.kw)
        with self.assertRaises(ValueError):
            export(self.video, self.nav, self.review, self.stills,
                   self.gallery, self.stills / 'oops.html', **self.kw)
        with self.assertRaises(ValueError):
            export(self.video, self.nav, self.review, self.stills,
                   self.gallery, self.root / 'wrong.json', **self.kw)

    def test_tampered_source_rejected_without_writing_html(self):
        obj = json.loads((self.gallery / 'review_gallery.json').read_text())
        obj['entries'][0]['links'][0]['status'] = 'forged_verified'
        (self.gallery / 'review_gallery.json').write_text(json.dumps(obj))
        with self.assertRaises(ValueError):
            export(self.video, self.nav, self.review, self.stills,
                   self.gallery, self.output, **self.kw)
        self.assertFalse(self.output.exists())

    def test_html_escapes_untrusted_script_delimiters(self):
        gallery = copy.deepcopy(self.gallery_data)
        gallery['entries'][0]['links'][0]['value'] = '</script><img src=x onerror=alert(1)>&'
        page = render(self.template, gallery, self.digest, self.stills, self.output)
        self.assertNotIn('</script><img', page)
        self.assertNotIn('<img src=x', page)
        self.assertIn('\\u003c/script\\u003e', page)

    def test_forged_template_is_rejected(self):
        fake = copy.deepcopy(self.template)
        fake['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            render(fake, self.gallery_data, self.digest, self.stills, self.output)

    def test_js_integer_pts_round_trip_is_accepted_without_changing_value(self):
        edited = json.loads(json.dumps(self.template))
        row = next(r for r in edited['rows'] if r['requested_pts_seconds'] == 2.0)
        row['requested_pts_seconds'] = 2  # Browser JSON.stringify(2.0) -> 2.
        self.assertEqual(validate(self.gallery_data, self.digest, edited)['counts']['pending'], 8)

    def test_changed_or_boolean_pts_is_rejected(self):
        for value in (2.1, True, '2.0', None):
            with self.subTest(value=value):
                edited = copy.deepcopy(self.template)
                row = next(r for r in edited['rows'] if r['requested_pts_seconds'] == 2.0)
                row['requested_pts_seconds'] = value
                with self.assertRaises(ValueError):
                    validate(self.gallery_data, self.digest, edited)

    def test_unsafe_image_filename_rejected(self):
        gallery = copy.deepcopy(self.gallery_data)
        link = next(l for e in gallery['entries'] for l in e['links'] if l['frame'])
        link['frame']['filename'] = '../../evil.png'
        with self.assertRaisesRegex(ValueError, 'Unsafe image'):
            render(self.template, gallery, self.digest, self.stills, self.output)

    def test_exported_template_is_validatable_without_review(self):
        result = validate(self.gallery_data, self.digest, copy.deepcopy(self.template))
        self.assertEqual(result['counts']['pending'], 8)
        self.assertEqual(result['counts']['unreviewable'], 16)
        self.assertFalse(result['automatic_clip_selection_authorized'])


if __name__ == '__main__':
    unittest.main()
