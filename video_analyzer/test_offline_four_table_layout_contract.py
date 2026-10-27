import unittest
from offline_four_table_layout_contract import build_plan

GRID = {'schema_version': 1, 'layout': 'grid', 'rows': 2, 'columns': 2}


class LayoutContractTests(unittest.TestCase):
    def plan(self, layout=None, times=None, width=321, height=241, duration=60):
        return build_plan(GRID if layout is None else layout, width, height, duration,
                          [0.1, 30.1] if times is None else times)

    def test_odd_dimensions_covered(self):
        p = self.plan()
        self.assertEqual(len(p['regions']), 4)
        self.assertEqual(sum(r['width'] * r['height'] for r in p['regions']), 321 * 241)

    def test_all_authorization_flags_false(self):
        p = self.plan()
        for key in ('regions_human_confirmed', 'cards_actions_verified',
                    'ready_for_equity_or_ev', 'automatic_clip_selection_authorized'):
            self.assertIs(p[key], False)

    def test_requested_not_decoded_pts(self):
        self.assertEqual(self.plan()['timestamp_semantics'], 'requested_seconds_not_decoded_pts')

    def test_deterministic_hash(self):
        self.assertEqual(self.plan()['layout_sha256'], self.plan()['layout_sha256'])

    def test_manual_two_tables(self):
        m = {'schema_version': 1, 'layout': 'manual', 'regions': [
            {'table_id': 4, 'x': 200, 'y': 0, 'width': 100, 'height': 100},
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 100, 'height': 100}]}
        self.assertEqual([r['table_id'] for r in self.plan(m)['regions']], [1, 4])

    def test_reject_overlap(self):
        m = {'schema_version': 1, 'layout': 'manual', 'regions': [
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 100, 'height': 100},
            {'table_id': 2, 'x': 50, 'y': 0, 'width': 100, 'height': 100}]}
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            self.plan(m)

    def test_reject_boolean_dimensions(self):
        with self.assertRaises(ValueError):
            self.plan(width=True)

    def test_reject_boolean_coordinate(self):
        m = {'schema_version': 1, 'layout': 'manual', 'regions': [
            {'table_id': 1, 'x': False, 'y': 0, 'width': 100, 'height': 100}]}
        with self.assertRaisesRegex(ValueError, 'Invalid manual'):
            self.plan(m)

    def test_reject_five_tables(self):
        with self.assertRaises(ValueError):
            self.plan({'schema_version': 1, 'layout': 'grid', 'rows': 1, 'columns': 5})

    def test_reject_duplicate_timestamps(self):
        with self.assertRaises(ValueError):
            self.plan(times=[1, 1])

    def test_reject_nan_timestamp(self):
        with self.assertRaises(ValueError):
            self.plan(times=[float('nan')])

    def test_reject_time_outside_recording(self):
        with self.assertRaises(ValueError):
            self.plan(times=[60])

    def test_reject_too_many_samples(self):
        with self.assertRaises(ValueError):
            self.plan(times=list(range(9)))

    def test_reject_bad_version(self):
        with self.assertRaises(ValueError):
            self.plan({'schema_version': 2, 'layout': 'grid', 'rows': 2, 'columns': 2})


if __name__ == '__main__':
    unittest.main()
