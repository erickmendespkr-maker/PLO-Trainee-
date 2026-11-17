"""Synthetic-only crop geometry tests; no poker recognition is implied."""
import unittest
from offline_table_crop_geometry import crop_filter, table_crop_filters


class TableCropTests(unittest.TestCase):
    def test_valid_crop(self):
        self.assertEqual(crop_filter(800, 600, dict(x=0,y=0,width=400,height=300)), 'crop=400:300:0:0')

    def test_four_tables(self):
        regions = {1:dict(x=0,y=0,width=400,height=300),2:dict(x=400,y=0,width=400,height=300),3:dict(x=0,y=300,width=400,height=300),4:dict(x=400,y=300,width=400,height=300)}
        self.assertEqual(len(table_crop_filters(800,600,regions)),4)

    def test_reject_overlap(self):
        with self.assertRaises(ValueError):
            table_crop_filters(800,600,{1:dict(x=0,y=0,width=400,height=300),2:dict(x=200,y=0,width=400,height=300)})

    def test_reject_outside(self):
        with self.assertRaises(ValueError):
            crop_filter(800,600,dict(x=600,y=0,width=400,height=300))

    def test_reject_odd_dimensions(self):
        with self.assertRaises(ValueError):
            crop_filter(800,600,dict(x=1,y=0,width=400,height=300))

    def test_reject_boolean(self):
        with self.assertRaises(ValueError):
            crop_filter(True,600,dict(x=0,y=0,width=400,height=300))

    def test_reject_extra_fields(self):
        with self.assertRaises(ValueError):
            crop_filter(800,600,dict(x=0,y=0,width=400,height=300,command='bad'))

    def test_reject_empty(self):
        with self.assertRaises(ValueError):
            table_crop_filters(800,600,{})

    def test_reject_fifth_table(self):
        with self.assertRaises(ValueError):
            table_crop_filters(800,600,{5:dict(x=0,y=0,width=400,height=300)})


if __name__ == '__main__':
    unittest.main()
