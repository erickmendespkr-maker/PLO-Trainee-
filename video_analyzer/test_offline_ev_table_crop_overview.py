"""Synthetic HTML overview validation for cropped PLO table videos."""
import unittest

import offline_ev_table_crop as crop
import offline_ev_table_crop_overview as html
import test_offline_ev_table_crop as fixtures


class OverviewTests(unittest.TestCase):
    def setUp(self):
        fixtures.CropTests.setUpClass()
        self.addCleanup(fixtures.CropTests.tearDownClass)
        self.fixture = fixtures.CropTests('test_four_table_render_and_hashes')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.make(4)
        self.fixture.run_export()

    def test_four_mp4_links(self):
        target = html.overview(self.fixture.out)
        text = target.read_text(encoding='utf-8')
        self.assertEqual(text.count('<video controls'), 4)
        self.assertIn('crop_clip-3.mp4', text)
        self.assertIn('não é veredito estratégico', text)

    def test_existing_html_rejected(self):
        target = self.fixture.out / 'crop_overview.html'
        target.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'exists'): html.overview(self.fixture.out)
        self.assertEqual(target.read_text(), 'keep')

    def test_modified_crop_rejected(self):
        with (self.fixture.out / 'crop_clip-0.mp4').open('ab') as f: f.write(b'altered')
        with self.assertRaisesRegex(ValueError, 'provenance'): html.overview(self.fixture.out)
        self.assertFalse((self.fixture.out / 'crop_overview.html').exists())

    def test_modified_metadata_rejected(self):
        path = self.fixture.out / 'crop_clip-0.json'
        data = crop.read_json(path)
        data['automatic_ocr_math_authorization'] = True
        self.fixture.dump(path, data)
        with self.assertRaisesRegex(ValueError, 'provenance'): html.overview(self.fixture.out)

    def test_ledger_ocr_authorization_rejected(self):
        path = self.fixture.out / 'crop_batch_report.json'
        data = crop.read_json(path)
        data['automatic_ocr_math_authorization'] = True
        self.fixture.dump(path, data)
        with self.assertRaisesRegex(ValueError, 'crop ledger'): html.overview(self.fixture.out)


if __name__ == '__main__':
    unittest.main()
