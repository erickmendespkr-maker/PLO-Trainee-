import unittest
from offline_clip_plan_preflight import validate_clip_plan

BASE = dict(table_id=1, hand_id='hand-001', source_sha256='a'*64,
            review_status='insufficient_data', strategic_verdict_allowed=False,
            start_seconds=1, end_seconds=3, duration_seconds=2)

class PreflightTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_clip_plan(BASE))
    def test_tables(self):
        for value in (0, 5, True, 1.0, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'table'):
                validate_clip_plan({**BASE, 'table_id': value})
    def test_hand_id(self):
        for value in ('../x', '', 'a/b', 'a\\b', ' ', 'x'*81, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'hand'):
                validate_clip_plan({**BASE, 'hand_id': value})
    def test_hash(self):
        for value in ('A'*64, 'a'*63, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'hash'):
                validate_clip_plan({**BASE, 'source_sha256': value})
    def test_time(self):
        for field, value in [('start_seconds', -1), ('end_seconds', 1), ('duration_seconds', 4), ('start_seconds', float('nan')), ('end_seconds', True)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_clip_plan({**BASE, field: value})
    def test_gate(self):
        for field, value in [('review_status', 'unverified'), ('strategic_verdict_allowed', True)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_clip_plan({**BASE, field: value})

if __name__ == '__main__':
    unittest.main()
