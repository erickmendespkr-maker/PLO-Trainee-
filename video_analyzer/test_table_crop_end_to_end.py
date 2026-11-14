"""FFmpeg end-to-end regression for offline table crops and independent audit."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from offline_table_crop import export_table_crops
from offline_table_crop_audit import audit_table_crops


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)


class TableCropEndToEnd(unittest.TestCase):
    def test_two_regions_and_manifest_audit(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / 'source.mkv'
            run('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                'testsrc2=size=128x96:rate=10:duration=3', '-c:v', 'ffv1', str(source))
            regions = [dict(table_id=1, x=0, y=0, width=64, height=48),
                       dict(table_id=2, x=64, y=48, width=64, height=48)]
            output = root / 'crops'
            manifest = export_table_crops(source, output, regions, start_seconds=0.5, duration_seconds=2)
            self.assertEqual(manifest['status'], 'UNREVIEWED_TABLE_CROPS')
            audit = audit_table_crops(source, output)
            self.assertEqual(audit['status'], 'TECHNICAL_CROPS_AUDITED_ONLY')
            self.assertEqual(len(audit['tables']), 2)
            self.assertTrue(all(row['decoded_frames'] >= 18 for row in audit['tables']))
            self.assertFalse(audit['hands_verified'])
            self.assertFalse(audit['equity_ev_verified'])

    def test_tampered_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / 'source.mkv'
            run('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                'testsrc2=size=128x96:rate=10:duration=3', '-c:v', 'ffv1', str(source))
            output = root / 'crops'
            export_table_crops(source, output, [dict(table_id=1, x=0, y=0, width=64, height=48)],
                               start_seconds=0.5, duration_seconds=2)
            manifest_path = output / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['tables'][0]['hand_reconstructed'] = True
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                audit_table_crops(source, output)


if __name__ == '__main__':
    unittest.main()
