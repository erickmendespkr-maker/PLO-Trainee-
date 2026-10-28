"""Portable FFmpeg integration tests for offline consolidated session review."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import test_offline_review_ev_gate as gate_fixtures
from offline_session_consolidated_report import build, summarize, render_html
from offline_review_ev_gate import build as build_gate


class ConsolidatedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gate_fixtures.GateTests.setUpClass()
        cls.fixture_video = gate_fixtures.GateTests.fixture_video
        cls.fixture_clips = gate_fixtures.GateTests.fixture_clips
        cls.packet = gate_fixtures.GateTests.packet

    @classmethod
    def tearDownClass(cls):
        gate_fixtures.GateTests.tearDownClass()

    def setUp(self):
        gate_fixtures.GateTests.setUp(self)
        build_gate(self.video, self.clips, self.source, self.manual,
                   self.reviewed, self.output, self.html)
        self.summary = self.root / 'summary.json'
        self.summary_html = self.root / 'summary.html'

    def run_summary(self):
        return build(self.video, self.clips, self.source, self.manual,
                     self.reviewed, self.output, self.summary, self.summary_html)

    def edit(self, path, change):
        doc = json.loads(path.read_text(encoding='utf-8'))
        change(doc)
        path.write_text(json.dumps(doc), encoding='utf-8')

    def test_four_tables_and_status_counts(self):
        result = self.run_summary()
        self.assertEqual((result['table_count'], result['hand_count'],
                          result['decision_count'], result['clip_count']), (4,4,4,4))
        self.assertEqual(sum(result['ev_status_counts'].values()),4)
        self.assertEqual([h['game_type'] for h in result['hands']],
                         ['PLO5','PLO6','PLO5','PLO6'])

    def test_blocked_ev_not_exposed(self):
        result = self.run_summary()
        decisions = [h['decisions'][0] for h in result['hands']]
        self.assertEqual([d['may_display_hypothetical_ev'] for d in decisions],
                         [True,False,False,False])
        self.assertEqual(decisions[0]['hypothetical_ev_interval_units'], ['20','30'])
        self.assertTrue(all(d['hypothetical_ev_interval_units'] is None for d in decisions[1:]))
        self.assertFalse(result['equity_ev_recomputed'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['action_recommendation_authorized'])

    def test_json_and_html_generated_offline(self):
        report = self.run_summary()
        self.assertEqual(json.loads(self.summary.read_text()), report)
        html = self.summary_html.read_text()
        self.assertIn('Content-Security-Policy',html)
        self.assertEqual(html.count('<video'),4)
        self.assertNotIn('<script',html)
        self.assertNotIn('https://',html)
        self.assertIn('exported_batch/table1.mp4',html)
        self.assertEqual(html.count('EV bloqueado'),3)

    def test_reject_gate_tampering(self):
        self.edit(self.output,lambda d:d['decisions'][1].update(may_display_hypothetical_ev=True))
        with self.assertRaises(ValueError): self.run_summary()
        self.assertFalse(self.summary.exists())

    def test_reject_stale_gate(self):
        self.edit(self.output,lambda d:d.update(warning='stale'))
        with self.assertRaises(ValueError): self.run_summary()

    def test_reject_duplicate_json_key(self):
        with self.output.open('a',encoding='utf-8') as f: f.write('"a":1')
        with self.assertRaises(ValueError): self.run_summary()

    def test_reject_changed_clip(self):
        with (self.clips/'table4.mp4').open('ab') as f: f.write(b'tamper')
        with self.assertRaises(ValueError): self.run_summary()

    def test_reject_changed_video(self):
        with self.video.open('ab') as f: f.write(b'tamper')
        with self.assertRaises(ValueError): self.run_summary()

    def test_reject_changed_manual_review(self):
        self.edit(self.manual,lambda d:d['entries'][0].update(note='different'))
        with self.assertRaises(ValueError): self.run_summary()

    def test_reject_changed_reviewed_report(self):
        self.edit(self.reviewed,lambda d:d.update(equity_ev_recomputed=True))
        with self.assertRaises(ValueError): self.run_summary()

    def test_no_overwrite(self):
        self.summary.write_text('keep',encoding='utf-8')
        with self.assertRaises(ValueError): self.run_summary()
        self.assertEqual(self.summary.read_text(),'keep')
        self.assertFalse(self.summary_html.exists())

    def test_reject_output_outside_batch_parent(self):
        other = self.root/'other'
        other.mkdir()
        with self.assertRaises(ValueError):
            build(self.video,self.clips,self.source,self.manual,self.reviewed,self.output,
                  other/'summary.json',other/'summary.html')

    def test_reject_symlink_gate(self):
        self.output.rename(self.root/'original_gate.json')
        self.output.symlink_to(self.root/'original_gate.json')
        with self.assertRaises(ValueError): self.run_summary()

    def test_reject_symlink_clip(self):
        clip=self.clips/'table1.mp4'
        clip.rename(self.root/'real.mp4')
        clip.symlink_to(self.root/'real.mp4')
        with self.assertRaises(ValueError): self.run_summary()

    def test_reject_duplicate_input_paths(self):
        with self.assertRaises(ValueError):
            summarize(self.video,self.clips,self.source,self.manual,self.reviewed,self.reviewed)

    def test_html_escape_untrusted_hand_and_ranges(self):
        report=self.run_summary()
        report['hands'][0]['hand_id']='<img src=x onerror=alert(1)>'
        report['hands'][0]['decisions'][0]['call_range_assumption_unverified']='<script>alert(1)</script>'
        html=render_html(report,'exported_batch')
        self.assertNotIn('<img src=x',html)
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('&lt;script&gt;',html)

    def test_deterministic_summary(self):
        a,_,_=summarize(self.video,self.clips,self.source,self.manual,self.reviewed,self.output)
        b,_,_=summarize(self.video,self.clips,self.source,self.manual,self.reviewed,self.output)
        self.assertEqual(a,b)

    def test_reject_existing_html_no_partial_json(self):
        self.summary_html.write_text('existing',encoding='utf-8')
        with self.assertRaises(ValueError): self.run_summary()
        self.assertFalse(self.summary.exists())
        self.assertEqual(self.summary_html.read_text(),'existing')

    def test_reject_missing_clip(self):
        (self.clips/'table3.mp4').unlink()
        with self.assertRaises(ValueError): self.run_summary()


if __name__ == '__main__':
    unittest.main()
