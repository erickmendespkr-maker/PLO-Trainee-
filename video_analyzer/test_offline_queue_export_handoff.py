import json
import tempfile
import unittest
from pathlib import Path
try:
    from .offline_queue_export_handoff import build_export_handoff, save_export_handoff, HandoffError
except ImportError:
    from offline_queue_export_handoff import build_export_handoff, save_export_handoff, HandoffError


def candidate(identifier, table, start, end, confidence=0.5):
    return {'candidate_id': identifier, 'table_id': table, 'start_pts': start,
            'end_pts': end, 'visual_confidence': confidence}


class HandoffTests(unittest.TestCase):
    def test_merge_same_table(self):
        result = build_export_handoff([candidate('a', 1, 10, 12), candidate('b', 1, 13, 15)], source_duration=50)
        self.assertEqual(len(result['windows']), 1)
        self.assertEqual(result['windows'][0]['candidate_ids'], ['a', 'b'])
        self.assertEqual((result['windows'][0]['start_pts'], result['windows'][0]['end_pts']), (8, 17))

    def test_do_not_merge_different_tables(self):
        result = build_export_handoff([candidate('a', 1, 10, 12), candidate('b', 2, 10, 12)], source_duration=50)
        self.assertEqual(len(result['windows']), 2)

    def test_clamp(self):
        result = build_export_handoff([candidate('a', 1, 0, 1)], source_duration=2)
        self.assertEqual((result['windows'][0]['start_pts'], result['windows'][0]['end_pts']), (0, 2))

    def test_duration_exceeded(self):
        with self.assertRaises(HandoffError):
            build_export_handoff([candidate('a', 1, 10, 15)], source_duration=12)

    def test_invalid_numeric(self):
        for value in [True, float('nan'), float('inf'), 0, -1]:
            with self.subTest(value=value), self.assertRaises(HandoffError):
                build_export_handoff([], source_duration=value)

    def test_reject_bad_padding(self):
        for value in [True, -1, 31, float('nan')]:
            with self.subTest(value=value), self.assertRaises(HandoffError):
                build_export_handoff([], source_duration=20, padding_seconds=value)

    def test_no_claims(self):
        result = build_export_handoff([candidate('a', 4, 2, 3)], source_duration=10)
        window = result['windows'][0]
        self.assertFalse(window['export_approved'])
        self.assertFalse(window['hand_boundary_verified'])
        self.assertIsNone(window['strategic_conclusion'])
        self.assertFalse(window['gto_solution'])

    def test_deterministic(self):
        records = [candidate('z', 2, 9, 10), candidate('a', 1, 3, 4)]
        self.assertEqual(build_export_handoff(records, source_duration=30), build_export_handoff(list(reversed(records)), source_duration=30))

    def test_json_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'queue.json'
            save_export_handoff([candidate('a', 1, 2, 3)], path, source_duration=20)
            self.assertEqual(json.loads(path.read_text())['type'], 'provisional_clip_export_handoff')
            with self.assertRaises(FileExistsError):
                save_export_handoff([], path, source_duration=20)


if __name__ == '__main__':
    unittest.main()
