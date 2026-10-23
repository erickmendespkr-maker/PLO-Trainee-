"""Offline editor CSP and fail-closed JSON review validation tests."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest

from activity_review_editor import render_editor, validate_draft, main
from activity_review_packet import build_review_packet
from activity_snapshot_chain import build_activity_snapshot_queue
from test_activity_snapshot_chain import fixture


class ActivityReviewEditorTests(unittest.TestCase):
    def setUp(self):
        self.queue = build_activity_snapshot_queue(fixture())
        self.template = build_review_packet(self.queue)['template']

    def draft(self):
        value = copy.deepcopy(self.template)
        value['analysis_status'] = 'manual_review_draft_unverified_no_ev'
        return value

    def test_four_table_editor_no_remote_resources(self):
        html = render_editor(self.queue)
        self.assertEqual(html.count('<script>'), 1)
        self.assertIn('connect-src &#x27;none&#x27;', html)
        self.assertNotIn('http://', html)
        self.assertNotIn('https://', html)
        self.assertNotIn('fetch(', html)
        self.assertNotIn('innerHTML', html)
        self.assertIn('Exportar rascunho JSON', html)

    def test_script_hash_matches_actual_script(self):
        html = render_editor(self.queue)
        script = html.split('<script>', 1)[1].split('</script>', 1)[0]
        actual = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        self.assertIn("sha256-" + actual, html)

    def test_script_injection_is_encoded(self):
        queue = copy.deepcopy(self.queue)
        queue['tasks'][0]['hand_id'] = '</script><img src=x onerror=alert(1)>'
        queue['tasks'][0]['observed_action_hint'] = '";alert(1);//'
        html = render_editor(queue)
        self.assertEqual(html.count('</script>'), 1)
        self.assertNotIn('<img', html)
        self.assertIn('\\u003c/script\\u003e', html)

    def test_blank_draft_is_valid_but_blocked(self):
        draft = validate_draft(self.queue, self.draft())
        self.assertFalse(draft['ready_for_equity_or_ev'])
        self.assertFalse(draft['source_visual_content_verified'])
        self.assertTrue(all(not e['human_confirmed'] and not e['ready_for_ev'] for e in draft['entries']))

    def test_confirmed_field_remains_ev_blocked(self):
        draft = self.draft()
        field = draft['entries'][0]['reviewed_fields']['hero_cards']
        field.update(value=['As', 'Ks', '2d', '3c', '4h'], confidence=.9,
                     source_timestamp=1, source='frame audited manually', human_confirmed=True)
        result = validate_draft(self.queue, draft)
        self.assertTrue(result['entries'][0]['reviewed_fields']['hero_cards']['human_confirmed'])
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['entries'][0]['human_confirmed'])

    def test_missing_manual_evidence_blocks_confirmation(self):
        draft = self.draft()
        draft['entries'][0]['reviewed_fields']['observed_action']['human_confirmed'] = True
        with self.assertRaisesRegex(ValueError, 'lacks'):
            validate_draft(self.queue, draft)

    def test_reject_root_tampering(self):
        for key, value in [('ready_for_equity_or_ev', True), ('source_visual_content_verified', True),
                           ('recording_sha256', '0'*64), ('source_queue_sha256', '0'*64),
                           ('analysis_status', 'ready_for_ev')]:
            draft = self.draft(); draft[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_draft(self.queue, draft)

    def test_reject_identity_and_entry_tampering(self):
        for key, value in [('table_id', 3), ('hand_id', 'another'), ('decision_timestamp', 999),
                           ('human_confirmed', True), ('ready_for_ev', True), ('call_range', [])]:
            draft = self.draft(); draft['entries'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_draft(self.queue, draft)

    def test_reject_cross_queue_replay(self):
        queue = copy.deepcopy(self.queue)
        queue['tasks'][0]['hand_id'] = 'new-hand'
        with self.assertRaisesRegex(ValueError, 'Protected'):
            validate_draft(queue, self.draft())

    def test_reject_future_and_same_frame_evidence(self):
        for field, pts in [('hero_cards', 2), ('board', 2), ('observed_action', 3),
                           ('pot_before_action', 2.1), ('call_amount', -1)]:
            draft = self.draft(); draft['entries'][0]['reviewed_fields'][field]['source_timestamp'] = pts
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_draft(self.queue, draft)

    def test_reject_bad_cards_and_duplicates(self):
        for cards in (['As']*5, ['As', 'Ks', '2d', '3c', 'XX'], ['As', 'Ks', '2d', '3c'], ['As']*6):
            draft = self.draft(); draft['entries'][0]['reviewed_fields']['hero_cards']['value'] = cards
            with self.subTest(cards=cards), self.assertRaises(ValueError):
                validate_draft(self.queue, draft)
        draft = self.draft()
        draft['entries'][0]['reviewed_fields']['hero_cards']['value'] = ['As','Ks','2d','3c','4h']
        draft['entries'][0]['reviewed_fields']['board']['value'] = ['As','Ts','9h']
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_draft(self.queue, draft)

    def test_reject_nan_bool_invalid_confidence(self):
        for key, value in [('confidence', float('nan')), ('confidence', 1.01),
                           ('confidence', True), ('source_timestamp', float('inf')),
                           ('value', True)]:
            draft = self.draft(); draft['entries'][0]['reviewed_fields']['pot_before_action'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_draft(self.queue, draft)

    def test_reject_extra_keys_and_reordering(self):
        draft = self.draft(); draft['malicious'] = 'x'
        with self.assertRaises(ValueError): validate_draft(self.queue, draft)
        draft = self.draft(); draft['entries'].reverse()
        with self.assertRaises(ValueError): validate_draft(self.queue, draft)
        draft = self.draft(); draft['entries'][0]['reviewed_fields']['hero_cards']['evil'] = True
        with self.assertRaises(ValueError): validate_draft(self.queue, draft)

    def test_cli_render_validate_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            queue, draft, html, verified = (root/x for x in ('queue.json','draft.json','editor.html','validated.json'))
            queue.write_text(json.dumps(self.queue))
            draft.write_text(json.dumps(self.draft()))
            self.assertEqual(main(['render', str(queue), str(html)]), 0)
            self.assertEqual(main(['validate', str(queue), str(draft), str(verified)]), 0)
            self.assertEqual(json.loads(verified.read_text())['analysis_status'], 'manual_review_draft_unverified_no_ev')
            with self.assertRaises(FileExistsError): main(['render', str(queue), str(html)])
            with self.assertRaises(ValueError): main(['validate', str(queue), str(draft), str(queue)])


if __name__ == '__main__':
    unittest.main()
