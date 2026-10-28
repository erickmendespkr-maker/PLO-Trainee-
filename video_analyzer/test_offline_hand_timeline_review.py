"""Synthetic tests for local timeline review, no real poker or online integration."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from offline_hand_timeline_review import build, timeline, render_html


def fake_hand(id='H1', table=1, variant='PLO5', start=0, end=20):
    return {'hand_id':id,'table_id':table,'variant':variant,'start_seconds':start,
        'end_seconds':end,'boundary_origin':'manual_unverified','boundary_note':'Synthetic',
        'observation_indices':[0,1,2,3],
        'reviewed_fields':{
          'hero_cards':[{'value':'As Ks Qs Js Ts' if variant=='PLO5' else 'As Ks Qs Js Ts 9s',
                         'timestamp_seconds':1,'proposal_index':0,'review':'confirmed'}],
          'board':[{'value':'2h 3h 4h','timestamp_seconds':3,'proposal_index':1,'review':'confirmed'},
                   {'value':'2h 3h 4h 5h','timestamp_seconds':7,'proposal_index':2,'review':'corrected'}],
          'action':[{'value':'call','timestamp_seconds':9,'proposal_index':3,'review':'confirmed'}]},
        'unresolved_indices':[],'missing_fields':['pot'],'consistency_warnings':[],
        'status':'draft_requires_human_reconstruction','ready_for_equity_or_ev':False}


def doc(hands=None):
    return {'schema_version':1,'analysis_status':'offline_reviewed_hand_drafts_only',
      'source_reviewed_report_sha256':'a'*64,'source_boundaries_sha256':'b'*64,
      'source_roi_ocr_report_sha256':'c'*64,'hands_reconstructed':False,
      'ready_for_equity_or_ev':False,'hands':hands or [fake_hand()]}


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.src=self.root/'drafts.json'
        self.data=doc()
        self.save()

    def save(self):
        self.src.write_text(json.dumps(self.data,ensure_ascii=False),encoding='utf8')

    def run_build(self):
        return build(self.src,self.root/'result')

    def test_success_report_and_html(self):
        r=self.run_build()
        self.assertEqual(len(r['hands']),1)
        self.assertEqual(r['hands'][0]['observed_streets'],['flop','turn'])
        self.assertEqual(r['hands'][0]['events'][0]['field'],'hero_cards')
        self.assertFalse(r['ready_for_equity_or_ev'])
        self.assertEqual(r['source_hand_drafts_sha256'],hashlib.sha256(self.src.read_bytes()).hexdigest())
        self.assertIn('Exportar anotações', (self.root/'result'/'hand_timeline_review.html').read_text())

    def test_unresolved_indices_warning(self):
        hand=self.data['hands'][0]
        hand['observation_indices'].append(9)
        hand['unresolved_indices']=[9]
        self.assertIn('unresolved_ocr_observations',timeline(self.data)[0]['warnings'])

    def test_board_regression_warning(self):
        self.data['hands'][0]['reviewed_fields']['board'][1]['value']='2h 3h'
        self.assertIn('board_regressed_in_time',timeline(self.data)[0]['warnings'])

    def test_board_nonprefix_warning(self):
        self.data['hands'][0]['reviewed_fields']['board'][1]['value']='2h 3h 4s 5h'
        self.assertIn('board_changed_nonprefix',timeline(self.data)[0]['warnings'])

    def test_missing_street_warning(self):
        self.data['hands'][0]['reviewed_fields']['board'][1]['value']='2h 3h 4h 5h 6h'
        self.assertIn('missing_intermediate_board_snapshot',timeline(self.data)[0]['warnings'])

    def test_hero_collision(self):
        self.data['hands'][0]['reviewed_fields']['board'][0]['value']='As 3h 4h'
        self.assertIn('hero_board_card_collision',timeline(self.data)[0]['warnings'])

    def test_missing_observations(self):
        h=self.data['hands'][0]
        h['reviewed_fields']={};h['observation_indices']=[];h['missing_fields']=['hero_cards','board','pot','action']
        self.assertIn('no_resolved_observations',timeline(self.data)[0]['warnings'])

    def test_reject_overlapping_hands(self):
        h=fake_hand('H2',start=10,end=30)
        h['observation_indices']=[];h['reviewed_fields']={};h['missing_fields']=['hero_cards','board','pot','action']
        self.data['hands'].append(h)
        with self.assertRaisesRegex(ValueError,'Overlapping'):timeline(self.data)

    def test_parallel_hands_allowed(self):
        h=fake_hand('H2',table=2,variant='PLO6')
        h['observation_indices']=[10,11,12,13]
        for entries in h['reviewed_fields'].values():
            for e in entries:e['proposal_index']+=10
        self.data['hands'].append(h)
        self.assertEqual(len(timeline(self.data)),2)

    def test_reject_duplicate_observation_across_hands(self):
        h=fake_hand('H2',table=2)
        self.data['hands'].append(h)
        with self.assertRaisesRegex(ValueError,'Duplicate observation'):timeline(self.data)

    def test_reject_unaccounted_observation(self):
        self.data['hands'][0]['observation_indices'].append(99)
        with self.assertRaisesRegex(ValueError,'not accounted'):timeline(self.data)

    def test_reject_wrong_variant_cards(self):
        self.data['hands'][0]['variant']='PLO6'
        with self.assertRaisesRegex(ValueError,'hero count'):timeline(self.data)

    def test_reject_out_of_interval_timestamp(self):
        self.data['hands'][0]['reviewed_fields']['action'][0]['timestamp_seconds']=20
        with self.assertRaisesRegex(ValueError,'reviewed observation'):timeline(self.data)

    def test_reject_nonfinite(self):
        self.src.write_text(self.src.read_text().replace('"start_seconds": 0','"start_seconds": NaN'))
        with self.assertRaisesRegex(ValueError,'Nonfinite'):self.run_build()

    def test_reject_duplicate_json_key(self):
        self.src.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.run_build()

    def test_reject_tampered_ready_flag(self):
        self.data['ready_for_equity_or_ev']=True
        with self.assertRaisesRegex(ValueError,'provenance'):timeline(self.data)

    def test_reject_symlink_input(self):
        link=self.root/'link.json';link.symlink_to(self.src)
        with self.assertRaisesRegex(ValueError,'Unsafe JSON'):build(link,self.root/'out')

    def test_reject_existing_output(self):
        (self.root/'result').mkdir()
        with self.assertRaisesRegex(ValueError,'output'):self.run_build()

    def test_html_injection_not_executable(self):
        self.data['hands'][0]['boundary_note']='</script><script>alert(42)</script>'
        html=render_html({'hands':timeline(self.data),'source_hand_drafts_sha256':'f'*64})
        self.assertNotIn('</script><script>alert(42)</script>',html)
        self.assertIn('\\u003c/script>',html)

    def test_deterministic_outputs(self):
        self.run_build()
        build(self.src,self.root/'result2')
        for name in ('hand_timeline_review.json','hand_timeline_review.html'):
            self.assertEqual((self.root/'result'/name).read_bytes(),(self.root/'result2'/name).read_bytes())

    def test_cli(self):
        p=subprocess.run([sys.executable,str(Path(__file__).with_name('offline_hand_timeline_review.py')),
                          str(self.src),str(self.root/'cli')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['hands'],1)

    def test_browser_render_and_export(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('playwright unavailable')
        self.run_build()
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
            try:
                page=browser.new_page(accept_downloads=True)
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.set_content((self.root/'result'/'hand_timeline_review.html').read_text())
                self.assertEqual(page.locator('section h2').count(),1)
                self.assertIn('Mesa 1',page.locator('section h2').first.text_content())
                with page.expect_download() as download_info:
                    page.locator('#export').click()
                download=download_info.value
                path=self.root/'export.json';download.save_as(path)
                exported=json.loads(path.read_text())
                self.assertEqual(exported['annotations'][0]['review_status'],'pending')
                self.assertFalse(exported['ready_for_equity_or_ev'])
                self.assertFalse(errors,errors)
            finally:
                browser.close()


if __name__=='__main__':unittest.main()
