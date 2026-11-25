"""Short real-media smoke test and input guards for the synthetic load harness."""
import json
from pathlib import Path
import tempfile
import unittest

from plo5_session_load import fixture, run, size, STAGES
from offline_ingest_pts_audit import decoded_pts
from offline_video_ingest_probe import probe
from plo5_session_export import verify


class LoadTests(unittest.TestCase):
    def test_fixture_four_regions_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);video=fixture(root,8)
            self.assertEqual(probe(video)['duration_seconds'],8)
            self.assertEqual(decoded_pts(video),list(range(8)))
            regions=json.loads((root/'regions.json').read_text())['tables']
            self.assertEqual(len(regions),4)
            self.assertEqual({(r['x'],r['y']) for r in regions},{(0,0),(320,0),(0,320),(320,320)})
            self.assertEqual(len(list(root.glob('phase*.png'))),len(STAGES))
            self.assertEqual(len(list((root/'templates').glob('*.png'))),17)

    def test_reject_invalid_duration_and_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for value in (2,3601,True,8.0):
                with self.subTest(value=value),self.assertRaises(ValueError):fixture(root,value)
            self.assertEqual(list(root.iterdir()),[])
            with self.assertRaises(ValueError):run(root,duration=8)

    def test_short_full_pipeline_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'load';r=run(root,duration=8)
            self.assertEqual(r['decoded_source_frames'],8);self.assertEqual(r['samples_expected'],12)
            self.assertEqual(r['samples_audited'],12);self.assertEqual(r['pixel_spotchecks'],12)
            self.assertEqual(r['draft_frame_count']+r['unassigned_samples'],12)
            self.assertEqual(len(r['clips']),4);self.assertEqual(r['decision_reports'],0)
            self.assertEqual({c['table_id'] for c in r['clips']},{1,2,3,4})
            self.assertTrue(all(c['decoded_yuv420p_pixels_match'] and c['relative_pts_audited'] for c in r['clips']))
            self.assertEqual(r['dataset_kind'],'synthetic_fixture')
            for k in ('real_session_validated','complete_hands_verified','full_session_decisions_verified','gto_solution','automatic_clip_selection_authorized'):self.assertIs(r[k],False)
            self.assertEqual(verify(root/'package')['status'],'CONDITIONAL_SESSION_PACKAGE')
            self.assertGreater(size(root),r['retained_bytes_before_report'])
            (root/'package/session.txt').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):verify(root/'package')


if __name__=='__main__':unittest.main()
