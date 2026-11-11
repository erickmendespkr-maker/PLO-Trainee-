"""Synthetic offline video and explicit hypothetical EV; no online poker or private samples."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_hypothetical_footage_composer as app


class ComposerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plo_footage_composer_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clip = self.root / 'sample.mp4'
        p = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                            '-f', 'lavfi', '-i', 'testsrc2=s=640x360:r=15:d=2',
                            '-an', '-c:v', 'mpeg4', '-q:v', '5', str(self.clip)],
                           capture_output=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        self.metadata_path = Path(str(self.clip)+'.json')
        self.meta = {'schema_version': 1,
                     'analysis_status': 'manually_selected_offline_clip',
                     'clip_sha256': app.sha(self.clip), 'source_video_sha256': 'a'*64,
                     'source_request_sha256': 'b'*64, 'explanation': 'Human selected only',
                     'video_evidence_verified': False, 'automatic_clip_selection_authorized': False,
                     'audio_included': False, 'hand_id': 'sample_hand', 'table_id': 1,
                     'start_seconds': 7., 'end_seconds': 9.}
        self.write_meta()
        self.math = self.root/'math.json'
        self.math.write_text((Path(__file__).parent/'synthetic_result.json').read_text('utf-8'), 'utf-8')
        self.ack_path = self.root/'ack.json'
        self.ack = {'schema_version': 1,
                    'status': 'illustrative_footage_plus_hypothetical_math_only',
                    'source_clip_sha256': app.sha(self.clip),
                    'source_math_sha256': app.sha(self.math),
                    'scenario_id': 'example_1',
                    'reviewer_acknowledged_not_observed_analysis': True,
                    'reviewer_note': 'Illustrative math does not describe the visible decision.'}
        self.write_ack()

    def write_meta(self):
        self.metadata_path.write_text(json.dumps(self.meta), encoding='utf-8')

    def write_ack(self):
        self.ack_path.write_text(json.dumps(self.ack), encoding='utf-8')

    def compose(self):
        return app.compose(self.clip, self.math, self.ack_path, self.root/'result.mp4')

    def test_actual_ffmpeg_join_and_hash_provenance(self):
        result = self.compose()
        out = self.root/'result.mp4'
        self.assertEqual(result['combined_mp4_sha256'],app.sha(out))
        self.assertEqual(result['source_math_sha256'],app.sha(self.math))
        self.assertEqual(result['source_clip_sha256'],app.sha(self.clip))
        self.assertEqual(result['combined_video']['width'],1280)
        self.assertEqual(result['combined_video']['height'],720)
        self.assertAlmostEqual(result['combined_video']['duration_seconds'],9,delta=.2)
        self.assertFalse(result['strategic_error_established'])
        self.assertFalse(result['cards_actions_ranges_verified_from_video'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertIn('UNRELATED HYPOTHETICAL',result['warning'])
        self.assertEqual(json.loads(Path(str(out)+'.json').read_text()),result)

    def test_no_overwrite(self):
        self.compose()
        with self.assertRaises(ValueError): self.compose()

    def test_wrong_source_sha(self):
        self.meta['clip_sha256']='1'*64;self.write_meta()
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_unapproved_ack(self):
        self.ack['reviewer_acknowledged_not_observed_analysis']=False;self.write_ack()
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_math_hash_mismatch(self):
        self.ack['source_math_sha256']='1'*64;self.write_ack()
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_wrong_scenario_binding(self):
        self.ack['scenario_id']='another';self.write_ack()
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_unverified_evidence_promoted_to_true(self):
        self.meta['video_evidence_verified']=True;self.write_meta()
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_automatic_selection(self):
        self.meta['automatic_clip_selection_authorized']=True;self.write_meta()
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_bad_hand_id(self):
        self.meta['hand_id']='hand\nESCAPE';self.write_meta()
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_invalid_duration(self):
        self.meta['end_seconds']=20.;self.write_meta()
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_duplicate_meta_json(self):
        self.metadata_path.write_text('{"schema_version":1,"schema_version":1}', 'utf-8')
        with self.assertRaises(ValueError): self.compose()

    def test_refuse_unsafe_math_claims(self):
        data=json.loads(self.math.read_text('utf-8'))
        data['strategic_error_established']=True
        self.math.write_text(json.dumps(data),'utf-8')
        self.ack['source_math_sha256']=app.sha(self.math);self.write_ack()
        with self.assertRaises(ValueError): self.compose()

    def test_missing_orig_source_claim_rejected(self):
        del self.meta['source_video_sha256'];self.write_meta()
        with self.assertRaises(ValueError): self.compose()

    def test_alternate_unverified_sample_with_truthful_disclosure(self):
        self.meta['analysis_status']='unverified_excerpt_for_illustration_only'
        self.meta['manual_sample_only']=True
        del self.meta['source_request_sha256']
        self.write_meta()
        self.assertEqual(app.check_clip_sidecar(self.meta,app.sha(self.clip)),None)

    def test_alternate_sample_without_disclosure_rejected(self):
        self.meta['analysis_status']='unverified_excerpt_for_illustration_only'
        del self.meta['source_request_sha256'];self.write_meta()
        with self.assertRaises(ValueError): self.compose()

    def test_no_audio_claim_wrong(self):
        self.meta['audio_included']=True;self.write_meta()
        with self.assertRaises(ValueError): self.compose()

    def test_boolean_timestamp_rejected(self):
        self.meta['start_seconds']=True;self.write_meta()
        with self.assertRaises(ValueError): self.compose()


if __name__ == '__main__':
    unittest.main(verbosity=2)
