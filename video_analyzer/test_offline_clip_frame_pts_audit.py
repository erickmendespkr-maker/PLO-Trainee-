"""Synthetic-only tests of bounded frame PTS observations; no poker footage."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_clip_frame_pts_audit import build_audit, export_audit, frame_pts_near
from offline_manual_clip_export import export_clip


class FrameAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.source = cls.base/'cfr.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                        'testsrc2=size=160x120:rate=10:duration=4',
                        '-c:v','libx264','-pix_fmt','yuv420p','-y',str(cls.source)],check=True)
        cls.sel = {'schema_version':1,'recording_sha256':hashlib.sha256(cls.source.read_bytes()).hexdigest(),
                   'table_id':1,'start_seconds':0.55,'end_seconds':2.55,
                   'human_selected':True,'explanation':'Revisão sintética',
                   'reviewer_confidence':0.7,'crop':None}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_cfr_nearest_pts_and_flags(self):
        r=build_audit(self.source,self.sel)
        self.assertAlmostEqual(r['edges']['start_seconds']['nearest_observed_frame_pts_seconds'],0.5)
        self.assertAlmostEqual(r['edges']['end_seconds']['nearest_observed_frame_pts_seconds'],2.5)
        self.assertTrue(r['both_edges_have_observed_frames_within_tolerance'])
        for key in ('hand_start_or_end_pts_verified','hand_reconstruction_verified',
                    'math_analysis_linked','strategic_error_established','automatic_clip_selection_authorized'):
            self.assertFalse(r[key])

    def test_selection_and_clip_integration(self):
        s=self.base/'selection.json'; s.write_text(json.dumps(self.sel))
        out=self.base/'frame_report.json'
        audit=export_audit(self.source,s,out)
        clip=export_clip(self.source,s,self.base/'selected.mp4')
        self.assertEqual(audit['source_sha256'],clip['source_sha256'])
        self.assertFalse(audit['hand_start_or_end_pts_verified'])
        self.assertFalse(clip['source_pts_boundaries_verified'])
        self.assertEqual(json.loads(out.read_text()),audit)
        with self.assertRaises(ValueError):
            export_audit(self.source,s,out)

    def test_source_digest_mismatch(self):
        s=copy.deepcopy(self.sel);s['recording_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            build_audit(self.source,s)

    def test_invalid_tolerance(self):
        for x in (-1,0,1.1,float('nan'),True):
            with self.subTest(value=x), self.assertRaises(ValueError):
                build_audit(self.source,self.sel,x)

    def test_invalid_duration(self):
        s=copy.deepcopy(self.sel);s['end_seconds']=4.2
        with self.assertRaisesRegex(ValueError,'timeline'):
            build_audit(self.source,s)

    def test_invalid_crop(self):
        s=copy.deepcopy(self.sel);s['crop']={'x':100,'y':0,'width':100,'height':100}
        with self.assertRaisesRegex(ValueError,'Crop'):
            build_audit(self.source,s)

    def test_missing_frame_sample_fails_closed(self):
        with patch('offline_clip_frame_pts_audit.subprocess.run') as run:
            run.return_value.stdout=b''
            with self.assertRaisesRegex(ValueError,'No decoded'):
                frame_pts_near(self.source,1.0,4.0)

    def test_invalid_frame_pts_fails_closed(self):
        with patch('offline_clip_frame_pts_audit.subprocess.run') as run:
            run.return_value.stdout=b'NaN\n'
            with self.assertRaisesRegex(ValueError,'Out-of-bounds'):
                frame_pts_near(self.source,1.0,4.0)

    def test_no_output_on_bad_source(self):
        p=self.base/'bad_selection.json'; s=copy.deepcopy(self.sel)
        s['recording_sha256']='0'*64;p.write_text(json.dumps(s))
        target=self.base/'never_written.json'
        with self.assertRaises(ValueError):
            export_audit(self.source,p,target)
        self.assertFalse(target.exists())

    def test_input_symlink_rejected(self):
        symlink=self.base/'linked.mp4';symlink.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            build_audit(symlink,self.sel)

    def test_selection_symlink_rejected(self):
        p=self.base/'real_selection.json';p.write_text(json.dumps(self.sel))
        link=self.base/'linked_selection.json';link.symlink_to(p)
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            export_audit(self.source,link,self.base/'not_created.json')

    def test_duplicate_json_key_rejected(self):
        p=self.base/'duplicate_selection.json';p.write_text('{"table_id":1,"table_id":2}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            export_audit(self.source,p,self.base/'duplicate_out.json')

    def test_source_changes_during_audit(self):
        tamper_source=self.base/'tamper_source.mp4'
        tamper_source.write_bytes(self.source.read_bytes())
        original=hashlib.sha256(tamper_source.read_bytes()).hexdigest()
        s=copy.deepcopy(self.sel)
        self.assertEqual(s['recording_sha256'],original)
        with patch('offline_clip_frame_pts_audit.frame_pts_near') as sample:
            def change(src, timestamp, duration):
                if not sample.side_effect.done:
                    sample.side_effect.done=True
                    src.write_bytes(src.read_bytes()+b'tamper')
                return {'absolute_offset_seconds':0.0}
            change.done=False
            sample.side_effect=change
            with self.assertRaisesRegex(ValueError,'changed'):
                build_audit(tamper_source,s)

    def test_four_tables_keep_manual_identity(self):
        for table in (1,2,3,4):
            with self.subTest(table=table):
                s=copy.deepcopy(self.sel);s['table_id']=table
                r=build_audit(self.source,s)
                self.assertEqual(r['table_id_human_selected'],table)
                self.assertFalse(r['automatic_clip_selection_authorized'])

    def test_sparse_frames_do_not_promote_boundaries(self):
        sparse=self.base/'sparse.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                        'testsrc2=size=160x120:rate=1:duration=4',
                        '-c:v','libx264','-y',str(sparse)],check=True)
        s=copy.deepcopy(self.sel)
        s['recording_sha256']=hashlib.sha256(sparse.read_bytes()).hexdigest()
        r=build_audit(sparse,s,tolerance=0.1)
        self.assertFalse(r['both_edges_have_observed_frames_within_tolerance'])
        self.assertFalse(r['hand_start_or_end_pts_verified'])

    def test_nonzero_source_pts_origin_fails_closed(self):
        offset=self.base/'offset.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                        'testsrc2=size=160x120:rate=10:duration=4',
                        '-vf','setpts=PTS+5/TB','-fps_mode','passthrough',
                        '-c:v','libx264','-pix_fmt','yuv420p','-y',str(offset)],check=True)
        s=copy.deepcopy(self.sel)
        s['recording_sha256']=hashlib.sha256(offset.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'PTS origin'):
            build_audit(offset,s)

    def test_vfr_spacing_observed(self):
        vfr=self.base/'vfr.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                        'testsrc2=size=160x120:rate=10:duration=4',
                        '-vf',"select='not(mod(n,2))+not(mod(n,5))'",
                        '-fps_mode','vfr','-c:v','libx264','-pix_fmt','yuv420p',
                        '-y',str(vfr)],check=True)
        result=frame_pts_near(vfr,1.0,4.0)
        self.assertTrue(result['variable_spacing_observed'])
        self.assertGreater(result['max_sampled_frame_gap_seconds'],
                           result['median_sampled_frame_gap_seconds'])


if __name__=='__main__':
    unittest.main()
