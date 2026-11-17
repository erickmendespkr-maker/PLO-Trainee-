import unittest
from video_analyzer.offline_table_crop_geometry_integration import validated_table_regions

class GeometryIntegrationTests(unittest.TestCase):
    def test_four_tables_sorted(self):
        records = [{'table_id': i, 'x': (i-1)*100, 'y': 0, 'width': 100, 'height': 100} for i in (4,2,1,3)]
        result = validated_table_regions(400, 100, records)
        self.assertEqual([r['table_id'] for r in result], [1,2,3,4])
        self.assertEqual(result[0]['ffmpeg_filter'], 'crop=100:100:0:0')
    def test_overlap(self):
        with self.assertRaises(ValueError):
            validated_table_regions(400,200,[{'table_id':1,'x':0,'y':0,'width':200,'height':100},{'table_id':2,'x':100,'y':0,'width':100,'height':100}])
    def test_odd_coordinates(self):
        with self.assertRaises(ValueError):
            validated_table_regions(400,200,[{'table_id':1,'x':1,'y':0,'width':100,'height':100}])
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            validated_table_regions(400,200,[{'table_id':1,'x':0,'y':0,'width':100,'height':100}]*2)
    def test_bool_id(self):
        with self.assertRaises(ValueError):
            validated_table_regions(400,200,[{'table_id':True,'x':0,'y':0,'width':100,'height':100}])
    def test_outside(self):
        with self.assertRaises(ValueError):
            validated_table_regions(400,200,[{'table_id':1,'x':350,'y':0,'width':100,'height':100}])
    def test_fifth_table(self):
        with self.assertRaises(ValueError):
            validated_table_regions(1000,200,[{'table_id':i,'x':(i-1)*100,'y':0,'width':100,'height':100} for i in range(1,6)])
    def test_invalid_frame(self):
        with self.assertRaises(ValueError):
            validated_table_regions(True,200,[{'table_id':1,'x':0,'y':0,'width':100,'height':100}])
    def test_missing_field(self):
        with self.assertRaises(ValueError):
            validated_table_regions(400,200,[{'table_id':1,'x':0,'y':0,'width':100}])

if __name__ == '__main__': unittest.main()
