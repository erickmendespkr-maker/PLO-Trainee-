"""Offline worksheet security and non-executable template regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_review_packet import build_review_packet, write_review_packet, _digest
from activity_snapshot_chain import build_activity_snapshot_queue
from test_activity_snapshot_chain import fixture


class ReviewPacketTests(unittest.TestCase):
    def queue(self):
        return build_activity_snapshot_queue(fixture())

    def test_four_tables_no_auto_confirmation(self):
        packet = build_review_packet(self.queue())
        self.assertEqual(packet['counts']['tasks'], 4)
        self.assertEqual({x['table_id'] for x in packet['template']['entries']}, {1, 2, 3, 4})
        self.assertFalse(packet['template']['ready_for_equity_or_ev'])
        for entry in packet['template']['entries']:
            self.assertFalse(entry['human_confirmed'])
            self.assertIsNone(entry['call_range'])
            self.assertIsNone(entry['model_assumptions'])
            self.assertTrue(all(not v['human_confirmed'] and v['value'] is None
                                for v in entry['reviewed_fields'].values()))

    def test_html_is_offline_and_read_only(self):
        html = build_review_packet(self.queue())['html']
        self.assertIn('Content-Security-Policy', html)
        self.assertIn("default-src 'none'", html)
        self.assertNotIn('<script', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('http://', html)
        self.assertNotIn('https://', html)

    def test_escaped_html_in_action_hand_and_source(self):
        queue = self.queue()
        task = queue['tasks'][0]
        task['hand_id'] = '<img src=x onerror=alert(1)>'
        task['observed_action_hint'] = '<script>alert(1)</script>'
        task['reviewed_ocr_sources']['pot']['source_image'] = '<img src=x>.png'
        html = build_review_packet(queue)['html']
        self.assertNotIn('<img', html)
        self.assertNotIn('<script', html)
        self.assertIn('&lt;script&gt;', html)

    def test_pinned_sha(self):
        queue = self.queue()
        self.assertEqual(build_review_packet(queue, expected_sha256=_digest(queue))['template']['source_queue_sha256'], _digest(queue))
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            build_review_packet(queue, expected_sha256='a'*64)

    def test_no_ev_ready_queue_or_task(self):
        queue = self.queue(); queue['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build_review_packet(queue)
        queue = self.queue(); queue['tasks'][0]['ready_for_ev'] = True
        with self.assertRaises(ValueError):
            build_review_packet(queue)

    def test_reject_future_or_same_frame(self):
        for time in (2, 3):
            queue = self.queue()
            queue['tasks'][0]['reviewed_ocr_sources']['pot']['source_timestamp'] = time
            with self.subTest(time=time), self.assertRaises(ValueError):
                build_review_packet(queue)

    def test_reject_unsafe_image_path(self):
        for path in ('../secret', '/tmp/x', 'file://secret', 'a\\b', ''):
            queue = self.queue()
            queue['tasks'][0]['reviewed_ocr_sources']['pot']['source_image'] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_review_packet(queue)

    def test_reject_duplicate_identity(self):
        queue = self.queue()
        queue['tasks'].append(copy.deepcopy(queue['tasks'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            build_review_packet(queue)

    def test_reject_malformed_input(self):
        for queue in (None, {}, {'schema_version': 2}, {'schema_version': 1, 'tasks': []}):
            with self.subTest(queue=queue), self.assertRaises(ValueError):
                build_review_packet(queue)

    def test_reject_invalid_table_timestamp(self):
        for key, value in (('table_id', 5), ('table_id', True), ('decision_timestamp', float('nan')),
                           ('decision_observation_index', -1)):
            queue = self.queue(); queue['tasks'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_review_packet(queue)

    def test_file_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, html, template = (root / x for x in ('queue.json', 'review.html', 'template.json'))
            source.write_text(json.dumps(self.queue()), encoding='utf-8')
            result = write_review_packet(source, html, template)
            self.assertEqual(result['tasks'], 4)
            self.assertEqual(len(json.loads(template.read_text())['entries']), 4)
            self.assertTrue(html.read_text().startswith('<!doctype html>'))
            with self.assertRaises(ValueError):
                write_review_packet(source, html, template)
            with self.assertRaises(ValueError):
                write_review_packet(source, source, root/'other.json')


if __name__ == '__main__':
    unittest.main()