"""Synthetic tests for the offline, fail-closed mathematical HTML report."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from hand_math_report import render, export
from hand_math_scenario_run import run
import test_hand_math_scenario_run as scenario_fixtures


class MathReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scenario_fixtures.HypotheticalMathTests.setUpClass()

    def setUp(self):
        self.fixture = scenario_fixtures.HypotheticalMathTests(methodName='test_empty_all_four_tables_skipped')
        self.fixture.setUp()
        self.intake = self.fixture.intake
        self.filled = self.fixture.completed

    def calc(self):
        return run(self.intake, self.filled, 'f' * 64)

    def html(self, result=None):
        return render(self.intake, self.filled, self.calc() if result is None else result,
                      intake_sha256='f' * 64, filled_sha256='a' * 64,
                      math_sha256='b' * 64)

    def test_four_tables_without_math(self):
        h = self.html()
        self.assertEqual(h.count('<article class="card">'), 4)
        self.assertIn('4 intervalos', h)
        self.assertIn('sem cálculo', h)
        self.assertIn("default-src 'none'", h)

    def test_plo5_equity_and_ev_visible(self):
        self.fixture.fill()
        h = self.html()
        self.assertIn('PLO5', h)
        self.assertIn('100.00%', h)
        self.assertIn('100.00 fichas', h)
        self.assertIn('12 / 42', h)
        self.assertIn('Monte Carlo', h)

    def test_plo6_raise_visible(self):
        self.fixture.fill(1, variant=6, action='raise')
        h = self.html()
        self.assertIn('PLO6', h)
        self.assertIn('140.00 fichas', h)

    def test_blocked_scenario_visible(self):
        self.fixture.fill()['human_confirmed'] = False
        self.assertIn('blocked_invalid_manual_scenario', self.html())

    def test_html_escapes_user_notes(self):
        self.fixture.fill()['model_notes'] = '<img src=x onerror=alert(1)> synthetic'
        h = self.html()
        self.assertNotIn('<img', h)
        self.assertIn('&lt;img', h)

    def test_reject_changed_equity(self):
        self.fixture.fill()
        result = self.calc()
        result['results'][0]['equity'] = .5
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.html(result)

    def test_reject_changed_status_and_counts(self):
        for field in ('status', 'model_limitations'):
            self.fixture.setUp()
            self.fixture.fill()
            result = self.calc()
            result['results'][0][field] = 'verified' if field == 'status' else 'no limits'
            with self.subTest(field=field), self.assertRaises(ValueError): self.html(result)
        result = self.calc()
        result['counts']['hypothetical'] = 99
        with self.assertRaises(ValueError): self.html(result)

    def test_reject_mismatched_sha(self):
        with self.assertRaises(ValueError):
            render(self.intake, self.filled, self.calc(),
                   intake_sha256='bad', filled_sha256='a' * 64, math_sha256='b' * 64)

    def test_export_round_trip_no_overwrite(self):
        self.fixture.fill()
        with tempfile.TemporaryDirectory() as temp:
            files = [Path(temp) / n for n in ('intake.json', 'filled.json', 'math.json')]
            result = self.calc()
            # The calculation's source hash must match the exact intake file bytes.
            files[0].write_text(json.dumps(self.intake))
            digest = hashlib.sha256(files[0].read_bytes()).hexdigest()
            result = run(self.intake, self.filled, digest)
            files[1].write_text(json.dumps(self.filled))
            files[2].write_text(json.dumps(result))
            target = Path(temp) / 'report.html'
            meta = export(*files, target)
            h = target.read_text()
            self.assertIn(digest, h)
            self.assertIn('PLO5', h)
            self.assertEqual(meta['counts']['hypothetical'], 1)
            with self.assertRaises(ValueError): export(*files, target)

    def test_export_rejects_tampered_math_file(self):
        with tempfile.TemporaryDirectory() as temp:
            files = [Path(temp) / n for n in ('intake.json', 'filled.json', 'math.json')]
            files[0].write_text(json.dumps(self.intake))
            files[1].write_text(json.dumps(self.filled))
            result = run(self.intake, self.filled, hashlib.sha256(files[0].read_bytes()).hexdigest())
            result['counts']['total'] = 9
            files[2].write_text(json.dumps(result))
            with self.assertRaises(ValueError): export(*files, Path(temp) / 'out.html')

    def test_export_rejects_symlink_input(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / 'intake.json'
            a.write_text(json.dumps(self.intake))
            link = Path(temp) / 'link.json'
            link.symlink_to(a)
            with self.assertRaises(ValueError): export(link, a, a, Path(temp) / 'out.html')

    def test_export_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            files = [Path(temp) / n for n in ('intake.json', 'filled.json', 'math.json')]
            files[0].write_text('{"a":1,"a":2}')
            files[1].write_text(json.dumps(self.filled))
            files[2].write_text(json.dumps(self.calc()))
            with self.assertRaises(ValueError): export(*files, Path(temp) / 'out.html')

    def test_deterministic_render(self):
        self.fixture.fill()
        self.assertEqual(self.html(), self.html())


if __name__ == '__main__':
    unittest.main()
