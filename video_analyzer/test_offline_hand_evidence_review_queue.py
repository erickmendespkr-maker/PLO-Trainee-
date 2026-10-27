"""Synthetic-only review-queue tests. No poker platform or real video is accessed."""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest

from offline_action_evidence_link import link
from offline_street_contribution_ledger import reconstruct
from offline_hand_evidence_review_queue import analyze_hand, build_queue, export, render_html


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.crop = self.root / 'crop.png'
        self.crop.write_bytes(b'synthetic-crop')
        self.source_sha = 'a' * 64
        self.ledger_input = {
            'schema_version': 1, 'variant': 'PLO6', 'source': 'synthetic',
            'table_id': 1, 'hand_label': 'hand-1',
            'initial_stacks': {'A': 200, 'B': 200}, 'starting_pot': 0,
            'events': [
                {'street': 'preflop', 'actor': 'A', 'kind': 'post_blind', 'delta_chips': 1,
                 'source_pts_seconds': 10, 'confidence': .95, 'evidence': 'synthetic',
                 'min_full_raise_increment': None},
                {'street': 'preflop', 'actor': 'B', 'kind': 'post_blind', 'delta_chips': 2,
                 'source_pts_seconds': 11, 'confidence': .9, 'evidence': 'synthetic',
                 'min_full_raise_increment': None},
                {'street': 'preflop', 'actor': 'A', 'kind': 'fold', 'delta_chips': 0,
                 'source_pts_seconds': 12, 'confidence': .6, 'evidence': 'synthetic',
                 'min_full_raise_increment': None},
            ],
        }
        self.ledger = reconstruct(self.ledger_input)
        self.evidence_input = {
            'schema_version': 1, 'source_recording_sha256': self.source_sha,
            'source_duration_seconds': 100,
            'ledger_input_canonical_sha256': self.ledger['input_canonical_sha256'],
            'table_id': 1, 'hand_label': 'hand-1',
            'observations': [{
                'event_index': 0, 'frame_pts_seconds': 10.1,
                'crop_path': 'crop.png',
                'crop_sha256': hashlib.sha256(self.crop.read_bytes()).hexdigest(),
                'bbox_pixels': [0, 0, 10, 10], 'recognition_confidence': .65,
                'extraction_method': 'synthetic',
            }],
        }
        self.evidence = link(self.ledger, self.evidence_input, self.root)
        self.tail = {
            'schema_version': 1, 'status': 'terminal_sequence_diagnostic_only',
            'source_sha256': self.source_sha, 'clip_sha256': 'b' * 64,
            'classification': 'possible_missing_terminal_frames',
            'possible_added_terminal_duplicate': False,
            'possible_missing_terminal_frames': True,
            'visual_provenance_verified': False, 'ocr_verified': False,
            'equity_ev_authorized': False,
        }
        self.manifest = {
            'schema_version': 1, 'session_label': 'Synthetic session',
            'source_recording_sha256_claim': self.source_sha,
            'hands': [{'ledger': 'ledger.json', 'evidence': 'evidence.json',
                       'temporal_audit': 'tail.json'}],
        }
        self.write()

    def write(self):
        for name, data in [('ledger.json', self.ledger), ('evidence.json', self.evidence),
                           ('tail.json', self.tail), ('session.json', self.manifest)]:
            (self.root / name).write_text(json.dumps(data), encoding='utf-8')

    def test_queue_prioritizes_missing_and_low_confidence(self):
        hand = analyze_hand(self.ledger, self.evidence, self.tail)
        self.assertEqual(hand['unlinked_event_count'], 2)
        self.assertEqual(hand['event_count'], 3)
        self.assertIn('no_linked_frame_crop', hand['events'][1]['review_reasons'])
        self.assertIn('low_uncalibrated_recognition_confidence', hand['events'][0]['review_reasons'])
        self.assertIn('low_uncalibrated_event_confidence', hand['events'][2]['review_reasons'])
        self.assertEqual(hand['temporal_audit_classification'], 'possible_missing_terminal_frames')
        self.assertGreater(hand['review_priority_points_not_probability'], 0)
        self.assertFalse(hand['equity_ev_authorized'])
        self.assertFalse(hand['video_evidence_verified'])
        self.assertFalse(hand['automatic_clip_selection_authorized'])

    def test_export_json_and_html_no_overwrite(self):
        output = self.root / 'queue.json'
        page = self.root / 'queue.html'
        result = export(self.root / 'session.json', output, page)
        self.assertEqual(result['hands'], 1)
        data = json.loads(output.read_text())
        self.assertEqual(data['hand_count'], 1)
        self.assertFalse(data['ocr_accuracy_verified'])
        self.assertIn('NÃO', page.read_text())
        self.assertIn('Content-Security-Policy', page.read_text())
        with self.assertRaisesRegex(ValueError, 'Outputs must be new'):
            export(self.root / 'session.json', output, page)

    def test_four_tables_sorted_by_review_need_not_table_order(self):
        reports = {}
        hands = []
        for table in range(1, 5):
            ledger = copy.deepcopy(self.ledger)
            evidence = copy.deepcopy(self.evidence)
            ledger['table_id'] = evidence['table_id'] = table
            ledger['hand_label'] = evidence['hand_label'] = f'hand-{table}'
            if table == 4:
                evidence['linked_observations'] = []
                evidence['linked_count'] = 0
                evidence['unlinked_event_indices'] = [0, 1, 2]
            ln, en = f'l{table}.json', f'e{table}.json'
            reports[ln], reports[en] = ledger, evidence
            hands.append({'ledger': ln, 'evidence': en, 'temporal_audit': None})
        manifest = {**self.manifest, 'hands': hands}
        result = build_queue(manifest, reports)
        self.assertEqual(result['hand_count'], 4)
        self.assertEqual(result['hands'][0]['table_id'], 4)
        self.assertTrue(result['all_hands_require_manual_review'])

    def test_clean_tail_does_not_certify(self):
        self.tail['classification'] = 'no_anomaly_detected_in_compared_tail'
        self.tail['possible_missing_terminal_frames'] = False
        hand = analyze_hand(self.ledger, self.evidence, self.tail)
        self.assertTrue(hand['manual_review_required'])
        self.assertFalse(hand['equity_ev_authorized'])

    def test_no_tail_still_works(self):
        self.manifest['hands'][0]['temporal_audit'] = None
        self.write()
        result = export(self.root / 'session.json', self.root / 'queue.json', self.root / 'queue.html')
        self.assertEqual(result['hands'], 1)
        self.assertIn('não fornecida', (self.root / 'queue.html').read_text())

    def test_xss_escape(self):
        self.ledger['hand_label'] = self.evidence['hand_label'] = '<img src=x onerror=alert(1)>'
        self.ledger['events'][0]['actor'] = '<script>bad</script>'
        self.evidence['linked_observations'][0]['actor'] = '<script>bad</script>'
        self.manifest['session_label'] = '<svg onload=alert(1)>'
        self.write()
        export(self.root / 'session.json', self.root / 'queue.json', self.root / 'queue.html')
        page = (self.root / 'queue.html').read_text()
        parser = Tags(); parser.feed(page)
        self.assertNotIn('img', parser.tags)
        self.assertNotIn('svg', parser.tags)
        self.assertNotIn('script', parser.tags)
        self.assertIn('&lt;script&gt;', page)

    def test_reject_mismatched_ledger_digest(self):
        self.evidence['ledger_input_canonical_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            analyze_hand(self.ledger, self.evidence)

    def test_reject_source_mismatch(self):
        self.manifest['source_recording_sha256_claim'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Different source'):
            build_queue(self.manifest, {'ledger.json': self.ledger,
                                        'evidence.json': self.evidence, 'tail.json': self.tail})

    def test_reject_tail_source_mismatch(self):
        self.tail['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Temporal audit'):
            analyze_hand(self.ledger, self.evidence, self.tail)

    def test_reject_tail_overclaim(self):
        self.tail['equity_ev_authorized'] = True
        with self.assertRaisesRegex(ValueError, 'Temporal audit'):
            analyze_hand(self.ledger, self.evidence, self.tail)

    def test_reject_evidence_overclaim(self):
        self.evidence['video_evidence_verified'] = True
        with self.assertRaisesRegex(ValueError, 'Evidence/ledger'):
            analyze_hand(self.ledger, self.evidence)

    def test_reject_duplicate_observation_index(self):
        self.evidence['linked_observations'].append(copy.deepcopy(self.evidence['linked_observations'][0]))
        self.evidence['linked_count'] = 2
        with self.assertRaisesRegex(ValueError, 'linked observation'):
            analyze_hand(self.ledger, self.evidence)

    def test_reject_missing_indices_forgery(self):
        self.evidence['unlinked_event_indices'] = []
        with self.assertRaisesRegex(ValueError, 'Unlinked event'):
            analyze_hand(self.ledger, self.evidence)

    def test_reject_observation_actor_mismatch(self):
        self.evidence['linked_observations'][0]['actor'] = 'X'
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            analyze_hand(self.ledger, self.evidence)

    def test_reject_nan_confidence(self):
        self.ledger['events'][0]['confidence'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'event confidence'):
            analyze_hand(self.ledger, self.evidence)

    def test_reject_bool_confidence(self):
        self.ledger['events'][0]['confidence'] = True
        with self.assertRaisesRegex(ValueError, 'event confidence'):
            analyze_hand(self.ledger, self.evidence)

    def test_reject_report_traversal(self):
        self.manifest['hands'][0]['ledger'] = '../ledger.json'
        self.write()
        with self.assertRaisesRegex(ValueError, 'Unsafe report filename'):
            export(self.root / 'session.json', self.root / 'queue.json', self.root / 'queue.html')

    def test_reject_symlink_report(self):
        (self.root / 'ledger.json').unlink()
        (self.root / 'ledger.json').symlink_to(self.root / 'evidence.json')
        with self.assertRaisesRegex(ValueError, 'Unsafe report file'):
            export(self.root / 'session.json', self.root / 'queue.json', self.root / 'queue.html')

    def test_reject_duplicate_json_keys(self):
        (self.root / 'session.json').write_text('{"hands":[],"hands":[]}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            export(self.root / 'session.json', self.root / 'queue.json', self.root / 'queue.html')

    def test_reject_nonfinite_json(self):
        (self.root / 'session.json').write_text('{"hands":NaN}')
        with self.assertRaisesRegex(ValueError, 'Nonfinite JSON'):
            export(self.root / 'session.json', self.root / 'queue.json', self.root / 'queue.html')

    def test_reject_duplicate_hand(self):
        self.manifest['hands'].append(copy.deepcopy(self.manifest['hands'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate table/hand'):
            build_queue(self.manifest, {'ledger.json': self.ledger,
                                        'evidence.json': self.evidence, 'tail.json': self.tail})

    def test_reject_over_200_hands(self):
        self.manifest['hands'] *= 201
        with self.assertRaisesRegex(ValueError, 'Invalid session metadata'):
            build_queue(self.manifest, {})

    def test_reject_existing_html_keeps_json_unwritten(self):
        (self.root / 'queue.html').write_text('preserve')
        with self.assertRaisesRegex(ValueError, 'Outputs must be new'):
            export(self.root / 'session.json', self.root / 'queue.json', self.root / 'queue.html')
        self.assertFalse((self.root / 'queue.json').exists())
        self.assertEqual((self.root / 'queue.html').read_text(), 'preserve')

    def test_reject_source_duration_before_event(self):
        self.evidence['source_duration_seconds_claim_unverified'] = 9
        with self.assertRaisesRegex(ValueError, 'after source duration'):
            analyze_hand(self.ledger, self.evidence)

    def test_no_event_hand_is_still_manual_review(self):
        ledger = copy.deepcopy(self.ledger)
        evidence = copy.deepcopy(self.evidence)
        ledger['events'] = []
        evidence['linked_observations'] = []
        evidence['linked_count'] = 0
        evidence['ledger_event_count'] = 0
        evidence['unlinked_event_indices'] = []
        hand = analyze_hand(ledger, evidence)
        self.assertTrue(hand['manual_review_required'])
        self.assertEqual(hand['event_count'], 0)

    def test_render_is_deterministic(self):
        queue = build_queue(self.manifest, {'ledger.json': self.ledger,
                                            'evidence.json': self.evidence, 'tail.json': self.tail})
        self.assertEqual(render_html(queue), render_html(queue))


if __name__ == '__main__':
    unittest.main()
