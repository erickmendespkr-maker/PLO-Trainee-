import unittest
from offline_crop_manifest_geometry import validate_manifest_geometry


def table(i, x, y, w=64, h=48):
    return {'table_id': i, 'region': {'table_id': i, 'x': x, 'y': y, 'width': w, 'height': h}}


class ManifestGeometryTests(unittest.TestCase):
    def test_four_disjoint(self):
        self.assertTrue(validate_manifest_geometry([table(1, 0, 0), table(2, 64, 0), table(3, 0, 48), table(4, 64, 48)], 128, 96))
    def test_overlap(self):
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            validate_manifest_geometry([table(1, 0, 0), table(2, 32, 0)], 128, 96)
    def test_touching_edges_allowed(self):
        self.assertTrue(validate_manifest_geometry([table(1, 0, 0), table(2, 64, 0)], 128, 96))
    def test_odd_origin(self):
        with self.assertRaises(ValueError): validate_manifest_geometry([table(1, 1, 0)], 128, 96)
    def test_odd_size(self):
        with self.assertRaises(ValueError): validate_manifest_geometry([table(1, 0, 0, 63)], 128, 96)
    def test_duplicate(self):
        with self.assertRaises(ValueError): validate_manifest_geometry([table(1, 0, 0), table(1, 64, 0)], 128, 96)
    def test_outside(self):
        with self.assertRaises(ValueError): validate_manifest_geometry([table(1, 66, 0)], 128, 96)
    def test_bool_not_integer(self):
        with self.assertRaises(ValueError): validate_manifest_geometry([table(True, 0, 0)], 128, 96)
    def test_extra_fields(self):
        item = table(1, 0, 0); item['region']['reviewed'] = True
        with self.assertRaises(ValueError): validate_manifest_geometry([item], 128, 96)
    def test_fifth_table(self):
        with self.assertRaises(ValueError): validate_manifest_geometry([table(i, 0, 0) for i in range(1, 6)], 128, 96)


if __name__ == '__main__': unittest.main()
