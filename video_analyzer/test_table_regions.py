import unittest
from table_regions import Region, grid_regions, validate_regions


class TableRegionsTests(unittest.TestCase):
    def test_four_regions_cover_odd_sized_frame(self):
        regions = grid_regions(1919, 1079)
        self.assertEqual(len(regions), 4)
        self.assertEqual(sum(r.width * r.height for r in regions), 1919 * 1079)
        self.assertTrue(validate_regions(regions, 1919, 1079))

    def test_reject_overlap(self):
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            validate_regions([Region(1, 0, 0, 50, 50), Region(2, 25, 25, 50, 50)], 100, 100)

    def test_reject_out_of_bounds(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            validate_regions([Region(1, 99, 0, 2, 10)], 100, 100)

    def test_reject_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_regions([Region(1, 0, 0, 10, 10), Region(1, 20, 0, 10, 10)], 100, 100)

    def test_reject_invalid_grid(self):
        with self.assertRaises(ValueError):
            grid_regions(1, 100, 2, 2)


if __name__ == '__main__':
    unittest.main()
