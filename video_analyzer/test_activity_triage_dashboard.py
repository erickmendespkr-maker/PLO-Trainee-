"""Offline triage dashboard tests: no EV authorization or remote browser resources."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

from activity_hypothetical_math import digest
from activity_review_triage_math import STATUS
from activity_triage_dashboard import (
    build_triage_dashboard, validate_triage, write_triage_dashboard, main,
)


def fixture():
    rows = []
    categories = ('human_attention_suggested', 'needs_evidence',
                  'human_review_optional', 'needs_evidence')
    for i, category in enumerate(categories, 1):
        rows.append({
            'table_id': i, 'hand_id': 'h' + str(i), 'event_index': 7 + i,
            'decision_timestamp': 2.0, 'filename': f'review_{i:03d}_table_{i}.mp4',
            'original_mp4_sha256': str(i) * 64,
            'review_category': category,
            'reason': 'Reviewed call >=25% of reviewed pot; heuristic only'
                      if i == 1 else 'Missing human-attested visible fields'
                      if category == 'needs_evidence' else 'No applicable call-exposure heuristic',
            'missing_fields': ['hero_cards', 'board'] if category == 'needs_evidence' else [],
            'call_to_pot_ratio': .25 if i == 1 else None,
            'has_conditional_what_if': i == 1,
            'sampling_ci95_if_available': [.35, .5] if i == 1 else None,
            'visual_evidence_confidence': 'unverified',
            'range_confidence': 'unverified_user_hypothesis',
            'strategic_error_established': False,
            'auto_clip_selection_authorized': False,
            'ev_ranking_authorized': False,
        })
    return {
        'schema_version': 1, 'analysis_status': STATUS,
        'recording_sha256': 'a' * 64,
        'source_explanations_sha256': 'b' * 64,
        'source_clip_manifest_sha256': 'c' * 64,
        'auto_clip_selection_authorized': False,
        'authorized_for_ev_based_ranking': False,
        'strategic_error_established': False,
        'sort_order': 'timestamp_only_not_mathematical_rank',
        'attention_threshold_call_to_pot': .25,
        'candidates': rows,
    }


class TriageDashboardTests(unittest.TestCase):
    def test_four_tables_categories_and_source_hash(self):
        data = fixture()
        output = build_triage_dashboard(data)
        self.assertEqual(output['total'], 4)
        self.assertEqual(output['counts'], {
            'needs_evidence': 2, 'human_attention_suggested': 1,
            'human_review_optional': 1})
        self.assertEqual(output['source_triage_sha256'], digest(data))
        for table in range(1, 5):
            self.assertIn(f'Mesa {table}', output['html'])

    def test_deterministic_output(self):
        data = fixture()
        self.assertEqual(build_triage_dashboard(data), build_triage_dashboard(data))

    def test_csp_no_network_or_media_or_remote_assets(self):
        html = build_triage_dashboard(fixture())['html']
        for value in ("default-src &#x27;none&#x27;", "connect-src &#x27;none&#x27;",
                      "media-src &#x27;none&#x27;", "form-action &#x27;none&#x27;"):
            self.assertIn(value, html)
        self.assertNotIn('https://', html)
        self.assertNotIn('<video', html)
        self.assertNotIn('<iframe', html)
        self.assertNotIn('fetch(', html)
        self.assertNotIn('innerHTML', html)
        self.assertNotIn('eval(', html)

    def test_no_automatic_approval_in_notes_export(self):
        html = build_triage_dashboard(fixture())['html']
        for name in ('visual_evidence_verified: false', 'strategic_error_established: false',
                     'ev_ranking_authorized: false', 'clip_selection_authorized: false',
                     'ready_for_equity_or_ev: false'):
            self.assertIn(name, html)

    def test_escape_malicious_hand_reason_and_filename(self):
        data = fixture()
        data['candidates'][0]['hand_id'] = '<img src=x onerror=alert(1)>'
        data['candidates'][0]['reason'] = '</script><script>alert(1)</script>'
        html = build_triage_dashboard(data)['html']
        self.assertNotIn('<img src=x', html)
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertIn('&lt;img src=x', html)
        self.assertIn('&lt;/script&gt;', html)

    def test_wrong_expected_sha_rejected(self):
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            build_triage_dashboard(fixture(), expected_sha256='0' * 64)

    def test_expected_sha_matches(self):
        data = fixture()
        self.assertEqual(build_triage_dashboard(data, expected_sha256=digest(data))['total'], 4)

    def test_reject_bad_top_level_authorizations(self):
        for key in ('auto_clip_selection_authorized', 'authorized_for_ev_based_ranking',
                    'strategic_error_established'):
            with self.subTest(key=key):
                data = fixture()
                data[key] = True
                with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_bad_candidate_authorizations(self):
        for key in ('auto_clip_selection_authorized', 'ev_ranking_authorized',
                    'strategic_error_established'):
            with self.subTest(key=key):
                data = fixture()
                data['candidates'][0][key] = True
                with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_wrong_status(self):
        data = fixture()
        data['analysis_status'] = 'EV_CONFIRMED'
        with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_wrong_sort_order(self):
        data = fixture()
        data['sort_order'] = 'ev_ranked'
        with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_duplicate_decision_identity(self):
        data = fixture()
        data['candidates'].append(copy.deepcopy(data['candidates'][0]))
        with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_nonchronological_rows(self):
        data = fixture()
        data['candidates'][1]['decision_timestamp'] = 1.0
        with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_nan_timestamp_and_ratio(self):
        for key in ('decision_timestamp', 'call_to_pot_ratio'):
            data = fixture()
            data['candidates'][0][key] = float('nan')
            with self.subTest(key=key), self.assertRaises(ValueError): validate_triage(data)

    def test_reject_missing_evidence_inconsistent_with_category(self):
        data = fixture()
        data['candidates'][1]['missing_fields'] = []
        with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_ratio_category_contradiction(self):
        data = fixture()
        data['candidates'][0]['call_to_pot_ratio'] = .1
        with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_unsafe_mp4_filename(self):
        for bad in ('../../secret.mp4', '/tmp/clip.mp4', 'evil\\x.mp4',
                    'evil.mp4?x=1', 'evil<script>.mp4', 'file..mp4'):
            with self.subTest(bad=bad):
                data = fixture()
                data['candidates'][0]['filename'] = bad
                with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_bad_ci(self):
        for ci in ([.8, .3], [-.1, .2], [.1, 1.1], [0], None):
            with self.subTest(ci=ci):
                data = fixture()
                data['candidates'][0]['sampling_ci95_if_available'] = ci
                with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_false_visual_confidence(self):
        data = fixture()
        data['candidates'][0]['visual_evidence_confidence'] = 'verified'
        with self.assertRaises(ValueError): validate_triage(data)

    def test_reject_too_many_rows(self):
        data = fixture()
        data['candidates'] = [data['candidates'][0]] * 10001
        with self.assertRaises(ValueError): validate_triage(data)

    def test_empty_report(self):
        data = fixture()
        data['candidates'] = []
        self.assertEqual(build_triage_dashboard(data)['total'], 0)

    def test_cli_writes_new_html_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'triage.json'
            target = Path(td) / 'review.html'
            source.write_text(json.dumps(fixture()), encoding='utf-8')
            self.assertEqual(main([str(source), str(target)]), 0)
            self.assertIn('PLO Trainee', target.read_text(encoding='utf-8'))
            with self.assertRaises(ValueError): write_triage_dashboard(source, target)

    def test_cli_rejects_symlink_input(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'triage.json'
            link = Path(td) / 'link.json'
            source.write_text(json.dumps(fixture()), encoding='utf-8')
            link.symlink_to(source)
            with self.assertRaises(ValueError): write_triage_dashboard(link, Path(td)/'out.html')


if __name__ == '__main__':
    unittest.main()
