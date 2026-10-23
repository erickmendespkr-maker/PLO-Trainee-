"""Synthetic tests for the offline clip selection editor (no auto-approval)."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_clip_selection_editor import (render_clip_selection_editor,
                                            validate_unapproved_template, main)
from activity_review_clip_template import build_clip_selection_template
from activity_review_clip_export import build_review_clip_plan
import test_activity_review_clip_export as clip_fixture


class ClipSelectionEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clip_fixture.NeutralReviewClipsTests.setUpClass()
        cls.fixture = clip_fixture.NeutralReviewClipsTests
        f = cls.fixture
        cls.template = build_clip_selection_template(f.video, f.queue, f.draft)

    @classmethod
    def tearDownClass(cls):
        clip_fixture.NeutralReviewClipsTests.tearDownClass()

    def test_template_remains_unapproved_after_render(self):
        original = copy.deepcopy(self.template)
        html = render_clip_selection_editor(self.template)
        self.assertEqual(self.template, original)
        self.assertIn('Confirme manualmente', html)
        self.assertIn('nenhum EV', html.lower().replace('nenhum ev', 'nenhum EV'))
        self.assertIn('Content-Security-Policy', html)
        self.assertNotIn('https://', html)

    def test_rejects_preapproved_regions(self):
        t = copy.deepcopy(self.template); t['regions_human_confirmed'] = True
        with self.assertRaises(ValueError): validate_unapproved_template(t)

    def test_rejects_preapproved_decision(self):
        t = copy.deepcopy(self.template); t['selections'][0]['reviewer_approved'] = True
        with self.assertRaises(ValueError): validate_unapproved_template(t)

    def test_rejects_priority_already_filled(self):
        t = copy.deepcopy(self.template); t['selections'][0]['reviewer_priority'] = .8
        with self.assertRaises(ValueError): validate_unapproved_template(t)

    def test_rejects_duplicate_decision(self):
        t = copy.deepcopy(self.template); t['selections'].append(copy.deepcopy(t['selections'][0]))
        with self.assertRaises(ValueError): validate_unapproved_template(t)

    def test_rejects_nonfinite_timestamp(self):
        t = copy.deepcopy(self.template); t['selections'][0]['decision_timestamp'] = float('nan')
        with self.assertRaises(ValueError): validate_unapproved_template(t)

    def test_rejects_invalid_sha(self):
        t = copy.deepcopy(self.template); t['recording_sha256'] = 'x'*64
        with self.assertRaises(ValueError): validate_unapproved_template(t)

    def test_rejects_malicious_script_close_and_escapes(self):
        t = copy.deepcopy(self.template)
        t['selections'][0]['hand_id'] = '</script><script>alert(1)</script>'
        html = render_clip_selection_editor(t)
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertIn(r'\u003c/script\u003e', html)

    def test_selection_requires_explicit_approval_at_export_gate(self):
        f = self.fixture
        with self.assertRaises(ValueError):
            build_review_clip_plan(f.video, f.queue, f.draft, self.template)

    def test_cli_creates_new_html_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'template.json'; target = Path(tmp)/'selection.html'
            source.write_text(json.dumps(self.template), encoding='utf-8')
            self.assertEqual(main([str(source), str(target)]), 0)
            self.assertIn('<html', target.read_text(encoding='utf-8'))
            with self.assertRaises(ValueError): main([str(source), str(target)])
            with self.assertRaises(ValueError): main([str(source), str(source)])


if __name__ == '__main__':
    unittest.main()
