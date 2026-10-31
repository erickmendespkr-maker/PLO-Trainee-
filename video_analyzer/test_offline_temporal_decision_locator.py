"""Synthetic decision-to-temporal-region contract tests; no poker client."""
import copy
import unittest
import offline_temporal_decision_locator as mod

SHA = 'a' * 64
R1 = [{'table_id': 'T1', 'x': 0, 'y': 0, 'width': 160, 'height': 180},
      {'table_id': 'T2', 'x': 160, 'y': 0, 'width': 160, 'height': 180}]
R2 = [{'table_id': 'T1', 'x': 0, 'y': 0, 'width': 184, 'height': 180},
      {'table_id': 'T2', 'x': 184, 'y': 0, 'width': 136, 'height': 180}]


def review():
    return {'schema_version': 1, 'status': mod.STATUS,
            'source_video_sha256': SHA, 'source_width': 320,
            'source_height': 180, 'source_duration_seconds': 6.0,
            'human_confirmation_claimed': True,
            'table_identity_verified': False,
            'automatic_ocr_math_authorization': False,
            'segments': [{'start_seconds': 0.0, 'end_seconds': 3.0,
                          'regions': copy.deepcopy(R1)},
                         {'start_seconds': 3.0, 'end_seconds': 6.0,
                          'regions': copy.deepcopy(R2)}]}


class LocatorTests(unittest.TestCase):
    def call(self, r=None, **kwargs):
        return mod.locate(r if r is not None else review(), video_sha256=SHA,
                          width=320, height=180, duration=6.0,
                          table_id=kwargs.pop('table_id', 'T1'),
                          timestamp=kwargs.pop('timestamp', 1.0), **kwargs)

    def bad(self, change):
        r = review()
        change(r)
        with self.assertRaises(ValueError):
            self.call(r)

    def test_first_segment(self):
        a = self.call(timestamp=1.0)
        self.assertEqual(a['region_claim']['width'], 160)
        self.assertFalse(a['automatic_ocr_math_authorization'])
        self.assertFalse(a['table_identity_verified'])

    def test_second_segment(self):
        a = self.call(timestamp=4.0, table_id='T2')
        self.assertEqual(a['segment_index'], 2)
        self.assertEqual(a['region_claim']['x'], 184)

    def test_guard_before_transition(self):
        self.assertEqual(self.call(timestamp=2.8)['status'], 'blocked_transition_uncertainty')

    def test_guard_after_transition(self):
        self.assertEqual(self.call(timestamp=3.2)['status'], 'blocked_transition_uncertainty')

    def test_guard_zero_at_transition(self):
        self.assertEqual(self.call(timestamp=3.0, boundary_guard_seconds=0)['status'],
                         'blocked_transition_uncertainty')

    def test_false_confirmation_rejected(self):
        self.bad(lambda r: r.update(human_confirmation_claimed=False))

    def test_automatic_math_authorization_rejected(self):
        self.bad(lambda r: r.update(automatic_ocr_math_authorization=True))

    def test_false_identity_claim_rejected(self):
        self.bad(lambda r: r.update(table_identity_verified=True))

    def test_hash_mismatch_rejected(self):
        self.bad(lambda r: r.update(source_video_sha256='b' * 64))

    def test_noncontiguous_segments_rejected(self):
        self.bad(lambda r: r['segments'][1].update(start_seconds=3.1))

    def test_uncovered_tail_rejected(self):
        self.bad(lambda r: r['segments'][1].update(end_seconds=5.0))

    def test_boolean_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            self.call(timestamp=True)

    def test_odd_geometry_rejected(self):
        self.bad(lambda r: r['segments'][1]['regions'][0].update(x=1))

    def test_duplicate_id_rejected(self):
        self.bad(lambda r: r['segments'][1]['regions'][1].update(table_id='T1'))

    def test_overlapping_regions_rejected(self):
        self.bad(lambda r: r['segments'][0]['regions'][1].update(x=100))

    def test_unsupported_table_rejected(self):
        with self.assertRaises(ValueError):
            self.call(table_id='T3')

    def test_negative_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            self.call(timestamp=-1)

    def test_invalid_guard_rejected(self):
        with self.assertRaises(ValueError):
            self.call(boundary_guard_seconds=3)

    def test_more_than_twelve_segments_rejected(self):
        self.bad(lambda r: r.update(segments=r['segments'] * 7))


if __name__ == '__main__':
    unittest.main()
