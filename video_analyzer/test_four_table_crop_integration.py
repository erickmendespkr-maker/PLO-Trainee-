"""Four-table FFmpeg integration and fail-closed crop audit regression.

No poker hands, cards, or EV are inferred from these synthetic frames.
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_table_crop import export_table_crops
from offline_table_crop_audit import audit_table_crops

REGIONS = [dict(table_id=i+1, x=(i%2)*64, y=(i//2)*48, width=64, height=48) for i in range(4)]

def source_video(root):
    path = root / 'source.mkv'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                    'testsrc2=size=128x96:rate=10:duration=3','-c:v','ffv1',str(path)],
                   check=True, capture_output=True, timeout=45)
    return path

class FourTableCropIntegration(unittest.TestCase):
    def test_four_table_export_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = source_video(root)
            dest = root/'crops'
            manifest = export_table_crops(src,dest,REGIONS,start_seconds=0.5,duration_seconds=2)
            self.assertEqual(len(manifest['tables']),4)
            result = audit_table_crops(src,dest)
            self.assertEqual(result['status'],'TECHNICAL_CROPS_AUDITED_ONLY')
            self.assertEqual({t['table_id'] for t in result['tables']},{1,2,3,4})
            self.assertTrue(all(t['decoded_frames'] >= 18 for t in result['tables']))
            self.assertFalse(result['visual_identity_verified'])
            self.assertFalse(result['hands_verified'])
            self.assertFalse(result['equity_ev_verified'])

    def test_tampered_fourth_table_geometry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = source_video(root)
            dest = root/'crops'
            export_table_crops(src,dest,REGIONS,start_seconds=0.5,duration_seconds=2)
            path = dest/'manifest.json'
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['tables'][3]['region']['width'] = 66
            path.write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaises(ValueError):
                audit_table_crops(src,dest)

    def test_missing_fourth_table_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = source_video(root)
            dest = root/'crops'
            export_table_crops(src,dest,REGIONS,start_seconds=0.5,duration_seconds=2)
            (dest/'table_4.mkv').unlink()
            with self.assertRaises(ValueError):
                audit_table_crops(src,dest)

if __name__ == '__main__':
    unittest.main()
