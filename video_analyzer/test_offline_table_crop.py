import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_table_crop import validate_regions, export_table_crops, probe_dimensions

R = [{'table_id': 1, 'x': 0, 'y': 0, 'width': 64, 'height': 48},
     {'table_id': 2, 'x': 64, 'y': 0, 'width': 64, 'height': 48}]

class CropTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(len(validate_regions(R, 128, 96)), 2)
    def test_four_tables(self):
        regions = [dict(table_id=i+1, x=(i%2)*64, y=(i//2)*48, width=64, height=48) for i in range(4)]
        self.assertEqual(len(validate_regions(regions, 128, 96)), 4)
    def test_out_of_bounds(self):
        with self.assertRaises(ValueError): validate_regions([dict(R[0], width=129)], 128, 96)
    def test_duplicate_id(self):
        with self.assertRaises(ValueError): validate_regions([R[0], dict(R[1], table_id=1)], 128, 96)
    def test_boolean_coordinate(self):
        with self.assertRaises(ValueError): validate_regions([dict(R[0], x=True)], 128, 96)
    def test_too_many(self):
        with self.assertRaises(ValueError): validate_regions([R[0]]*5, 128, 96)
    def test_actual_ffmpeg_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source.mkv'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                            '-i', 'testsrc2=size=128x96:rate=10', '-t', '2', '-c:v', 'ffv1',
                            str(source)], check=True, timeout=30)
            self.assertEqual(probe_dimensions(source), (128,96))
            out = root/'crops'
            manifest = export_table_crops(source, out, R, start_seconds=0, duration_seconds=1)
            self.assertEqual(manifest['status'], 'UNREVIEWED_TABLE_CROPS')
            self.assertFalse(manifest['poker_analysis_verified'])
            self.assertEqual(probe_dimensions(out/'table_1.mkv'), (64,48))
            self.assertEqual(probe_dimensions(out/'table_2.mkv'), (64,48))
            self.assertEqual(len(json.loads((out/'manifest.json').read_text())['tables']), 2)
            with self.assertRaises(ValueError): export_table_crops(source, out, R, start_seconds=0, duration_seconds=1)
    def test_invalid_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)/'s'; src.write_bytes(b'x')
            with self.assertRaises(ValueError): export_table_crops(src, Path(tmp)/'out', R, start_seconds=0, duration_seconds=float('nan'))

if __name__ == '__main__': unittest.main()
