"""Offline form tests. Browser tests run only when Chromium + Playwright exist."""
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


class ReviewFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_form_fixture_')
        cls.root = Path(cls.fixture.name)
        cls.video = cls.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', 'testsrc2=size=160x120:rate=10', '-t', '4', '-an',
                        '-c:v', 'mpeg4', '-q:v', '4', str(cls.video)],
                       capture_output=True, check=True, timeout=30)
        cls.obs = cls.root / 'observations.json'
        cls.observations = {
            'schema_version': 1, 'status': 'offline_unverified_street_observations',
            'source_video_sha256': media.digest(cls.video), 'variant': 'PLO5',
            'hands': [{'table_id': 'T1', 'hand_id': 'H1', 'start_seconds': .2,
                       'end_seconds': 3.8, 'events': [
                {'timestamp_seconds': .4, 'street': 'preflop', 'kind': 'hero_cards',
                 'value': ['AS','KH','QD','JC','TS'], 'origin': 'ocr_proposal', 'confidence': .55},
                {'timestamp_seconds': 1, 'street': 'flop', 'kind': 'board',
                 'value': ['2C','3D','4H'], 'origin': 'ocr_proposal', 'confidence': .8},
                {'timestamp_seconds': 1.5, 'street': 'flop', 'kind': 'action',
                 'value': 'call', 'origin': 'ocr_proposal', 'confidence': .3},
                {'timestamp_seconds': 2, 'street': 'turn', 'kind': 'board',
                 'value': ['2C','3D','4H','5S'], 'origin': 'manual_claim', 'confidence': 1.0}]}]}
        cls.obs.write_text(json.dumps(cls.observations), encoding='utf-8')
        cls.street_dir = cls.root / 'street'; cls.street_dir.mkdir()
        street.export(cls.video, cls.obs, cls.street_dir)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_form_case_')
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_form_embeds_schema_and_hash(self):
        html = form.export(self.video, self.obs, self.street_dir, self.out).read_text()
        self.assertIn('manual_offline_street_review', html)
        self.assertIn(media.digest(self.street_dir / street.REPORT), html)
        self.assertIn('Nenhuma autorização de equity', html)
        self.assertIn('connect-src \'none\'', html)
        self.assertNotIn('https://', html)

    def test_json_script_escaping(self):
        hostile = '</script><img src=x onerror=alert(1)>&'
        encoded = form.safe_json_for_html({'payload': hostile})
        self.assertNotIn('</script>', encoded)
        self.assertNotIn('<img', encoded)
        self.assertEqual(json.loads(encoded)['payload'], hostile)

    def test_output_collision(self):
        (self.out / form.PAGE).write_text('existing')
        with self.assertRaises(ValueError): form.export(self.video, self.obs, self.street_dir, self.out)
        self.assertEqual((self.out / form.PAGE).read_text(), 'existing')

    def test_output_symlink(self):
        (self.out / form.PAGE).symlink_to(self.obs)
        with self.assertRaises(ValueError): form.export(self.video, self.obs, self.street_dir, self.out)

    def test_output_dir_symlink(self):
        other = self.out / 'actual'; other.mkdir()
        link = self.out / 'link'; link.symlink_to(other, target_is_directory=True)
        with self.assertRaises(ValueError): form.export(self.video, self.obs, self.street_dir, link)

    def test_reject_report_tamper(self):
        bad = self.out / 'bad'; bad.mkdir()
        data = json.loads((self.street_dir / street.REPORT).read_text())
        data['hands'][0]['event_count'] = 999
        (bad / street.REPORT).write_text(json.dumps(data))
        with self.assertRaises(ValueError): form.export(self.video, self.obs, bad, self.out)

    def test_reject_duplicate_json_keys(self):
        bad = self.out / 'bad'; bad.mkdir()
        (bad / street.REPORT).write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): form.export(self.video, self.obs, bad, self.out)

    def test_reject_wrong_video(self):
        wrong = self.out / 'wrong.mp4'; wrong.write_bytes(self.video.read_bytes() + b'changed')
        with self.assertRaises(ValueError): form.export(wrong, self.obs, self.street_dir, self.out)

    def test_reject_alias_path(self):
        with self.assertRaises(ValueError): form.export(self.video, self.obs, self.street_dir, self.street_dir)

    def test_plo6_six_card_form(self):
        from bs4 import BeautifulSoup
        data = json.loads(json.dumps(self.observations))
        data['variant'] = 'PLO6'
        data['hands'][0]['events'][0]['value'].append('9H')
        obs = self.out / 'plo6.json'; obs.write_text(json.dumps(data))
        led = self.out / 'plo6_ledger'; led.mkdir()
        street.export(self.video, obs, led)
        generated = self.out / 'plo6_form'; generated.mkdir()
        html = form.export(self.video, obs, led, generated).read_text()
        soup = BeautifulSoup(html, 'html.parser')
        payload = json.loads(soup.select_one('#ledger').text)
        self.assertEqual(payload['variant'], 'PLO6')
        self.assertEqual(len(payload['hands'][0]['streets']['preflop'][0]['value']), 6)

    def test_hostile_ocr_text_is_data_not_markup(self):
        from bs4 import BeautifulSoup
        data = json.loads(json.dumps(self.observations))
        hostile = '</script><img src=x onerror=alert(1)>'
        data['hands'][0]['events'][2]['value'] = hostile
        obs = self.out / 'hostile.json'; obs.write_text(json.dumps(data))
        led = self.out / 'hostile_ledger'; led.mkdir()
        street.export(self.video, obs, led)
        generated = self.out / 'hostile_form'; generated.mkdir()
        html = form.export(self.video, obs, led, generated).read_text()
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual(len(soup.select('script')), 2)
        self.assertEqual(len(soup.select('img')), 0)
        payload = json.loads(soup.select_one('#ledger').text)
        self.assertEqual(payload['hands'][0]['streets']['flop'][1]['value'], hostile)

    @unittest.skipUnless(shutil.which('node'), 'node unavailable')
    def test_inline_script_syntax(self):
        from bs4 import BeautifulSoup
        html = form.export(self.video, self.obs, self.street_dir, self.out).read_text()
        scripts = [s.string for s in BeautifulSoup(html, 'html.parser').find_all('script') if s.get('type') != 'application/json']
        self.assertEqual(len(scripts), 1)
        js = self.out / 'script.js'; js.write_text(scripts[0])
        subprocess.run(['node','--check',str(js)], check=True, capture_output=True, timeout=15)

    @unittest.skipUnless(shutil.which('chromium'), 'Chromium unavailable')
    def test_browser_download_validated_by_backend(self):
        from playwright.sync_api import sync_playwright
        page_path = form.export(self.video, self.obs, self.street_dir, self.out)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium'), headless=True,
                                        args=['--no-sandbox'])
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            page.set_content(page_path.read_text(encoding='utf-8'))
            self.assertIn('0 de 4', page.locator('#progress').inner_text())
            page.locator('#reviewer').fill('operator_1')
            page.locator('#export').click()
            self.assertIn('Revise explicitamente', page.locator('#message').inner_text())
            for choice in page.locator('.event select').all():
                choice.select_option('confirm')
            self.assertIn('4 de 4', page.locator('#progress').inner_text())
            with page.expect_download() as download_info:
                page.locator('#export').click()
            download = download_info.value
            self.assertEqual(download.suggested_filename, 'manual_review.json')
            review_file = self.out / 'manual_review.json'
            download.save_as(review_file)
            self.assertEqual(len(json.loads(review_file.read_text())['hands'][0]['decisions']), 4)
            reviewed = self.out / 'reviewed'; reviewed.mkdir()
            result = human.export(self.video, self.obs, self.street_dir, review_file, reviewed)
            self.assertEqual(result['hands'][0]['rejected_event_count'], 0)
            self.assertFalse(result['automatic_ocr_math_authorization'])
            browser.close()

    @unittest.skipUnless(shutil.which('chromium'), 'Chromium unavailable')
    def test_browser_correction_rejection_and_invalid_cards(self):
        from playwright.sync_api import sync_playwright
        page_path = form.export(self.video, self.obs, self.street_dir, self.out)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium'), headless=True,
                                        args=['--no-sandbox'])
            context = browser.new_context(accept_downloads=True)
            page = context.new_page(); page.set_content(page_path.read_text(encoding='utf-8'))
            page.locator('#reviewer').fill('operator_2')
            events = page.locator('.event')
            for i in range(4): events.nth(i).locator('select').select_option('confirm')
            events.nth(1).locator('select').select_option('correct')
            events.nth(1).locator('input').fill('2C 3D 3D')
            events.nth(1).locator('textarea').fill('Conferido visualmente')
            page.locator('#export').click()
            self.assertIn('Cartas inválidas', page.locator('#message').inner_text())
            events.nth(1).locator('input').fill('2C,3D,6H')
            events.nth(2).locator('select').select_option('reject')
            events.nth(2).locator('textarea').fill('Ação encoberta')
            with page.expect_download() as info: page.locator('#export').click()
            review_file = self.out / 'review.json'; info.value.save_as(review_file)
            reviewed = self.out / 'reviewed'; reviewed.mkdir()
            report = human.export(self.video, self.obs, self.street_dir, review_file, reviewed)
            self.assertEqual(report['hands'][0]['rejected_event_count'], 1)
            self.assertEqual(report['hands'][0]['events'][1]['reviewed_value'], ['2C','3D','6H'])
            browser.close()


if __name__ == '__main__':
    unittest.main()
