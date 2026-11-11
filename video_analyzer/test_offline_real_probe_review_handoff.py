"""Synthetic, offline tests; no private recording is committed."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_real_probe_review_handoff as handoff


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_handoff_test_')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / 'fixture.mp4'
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-f', 'lavfi', '-i', 'color=c=0x2a3256:s=640x480:r=2:d=4',
               '-an', '-c:v', 'mpeg4', '-q:v', '5', str(self.video)]
        proc = subprocess.run(cmd, capture_output=True, timeout=40)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'slots': [
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 480},
            {'table_id': 2, 'x': 320, 'y': 0, 'width': 320, 'height': 480}],
            'felt_rgb': [42, 50, 86], 'tolerance': 40}), 'utf-8')
        self.probe = self.root / 'probe.json'
        def candidate(tid, visible=True, bb=10., conf=.9):
            return {'table_id':tid, 'proposal':'likely_visible' if visible else 'absent_or_uncertain',
                    'matched_felt_probes':4 if visible else 0,
                    'rgb_distances':[0., 0., 0., 0.], 'human_verified':False,
                    'pot_ocr':{'raw_text':f'{bb} BB', 'minimum_word_confidence':conf,
                               'candidate_bb':bb, 'status':'needs_human_review'} if visible else None}
        self.candidate = candidate
        self.report = {'schema_version':1, 'status':'real_video_ocr_and_layout_proposals_only',
            'source_video_sha256':handoff.sha256(self.video),
            'source_layout_sha256':handoff.sha256(self.config),
            'recording':{'width':640,'height':480,'duration_seconds':4.},
            'samples':[
                {'requested_playback_seconds':.5, 'decoded_source_pts_seconds':.5,
                 'table_proposals':[candidate(1),candidate(2)]},
                {'requested_playback_seconds':1.5,'decoded_source_pts_seconds':1.5,
                 'table_proposals':[candidate(1,bb=20.),candidate(2,visible=False)]}],
            'hands_reconstructed':False,'equity_ev_authorized':False,
            'automatic_clip_selection_authorized':False,
            'warnings':['unverified']}
        self.save()

    def save(self):
        self.probe.write_text(json.dumps(self.report), 'utf-8')

    def build(self):
        return handoff.assemble(self.video,self.config,self.probe)

    def test_events_and_clip_requests_need_review(self):
        report = self.build()
        self.assertEqual(len(report['events']), 2)
        self.assertEqual(report['events'][0]['event_kinds'], ['pot_ocr_change_unverified'])
        self.assertEqual(report['events'][1]['event_kinds'], ['table_visibility_change_unverified'])
        self.assertEqual(len(report['unapproved_clip_request_drafts']),2)
        self.assertTrue(all(x['reviewer_confirmed_offline'] is False
                            for x in report['unapproved_clip_request_drafts']))
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertFalse(report['hands_reconstructed'])
        self.assertEqual(report['source_video_sha256'],handoff.sha256(self.video))

    def test_low_confidence_change_never_promoted(self):
        self.report['samples'][0]['table_proposals'][0]['pot_ocr']['minimum_word_confidence']=.4
        self.save()
        result=self.build()
        self.assertEqual([e['table_id'] for e in result['events']],[2])

    def test_no_change_gives_empty_queue(self):
        self.report['samples'][1]['table_proposals']=copy.deepcopy(self.report['samples'][0]['table_proposals'])
        self.save()
        self.assertEqual(len(self.build()['events']),0)

    def test_no_draft_when_samples_too_far_apart(self):
        self.report['recording']['duration_seconds']=500
        self.report['samples'][1]['requested_playback_seconds']=250
        self.report['samples'][1]['decoded_source_pts_seconds']=250
        self.save()
        result=self.build()
        self.assertEqual(len(result['events']),2)
        self.assertEqual(result['unapproved_clip_request_drafts'],[])

    def test_reject_wrong_video_hash(self):
        self.report['source_video_sha256']='0'*64
        self.save()
        with self.assertRaises(ValueError):self.build()

    def test_reject_wrong_layout_hash(self):
        self.report['source_layout_sha256']='0'*64
        self.save()
        with self.assertRaises(ValueError):self.build()

    def test_reject_promoted_math_flag(self):
        self.report['equity_ev_authorized']=True
        self.save()
        with self.assertRaises(ValueError):self.build()

    def test_reject_boolean_as_timestamp(self):
        self.report['samples'][1]['decoded_source_pts_seconds']=True
        self.save()
        with self.assertRaises(ValueError):self.build()

    def test_reject_inconsistent_pts(self):
        self.report['samples'][1]['decoded_source_pts_seconds']=2.7
        self.save()
        with self.assertRaises(ValueError):self.build()

    def test_reject_duplicate_or_missing_table(self):
        self.report['samples'][1]['table_proposals'][1]['table_id']=1
        self.save()
        with self.assertRaises(ValueError):self.build()

    def test_reject_ocr_promotion(self):
        self.report['samples'][1]['table_proposals'][0]['pot_ocr']['status']='verified'
        self.save()
        with self.assertRaises(ValueError):self.build()

    def test_reject_duplicate_keys(self):
        self.probe.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):self.build()

    def test_refuse_overwrite(self):
        out=self.root/'output.json'
        result=handoff.run(self.video,self.config,self.probe,out)
        self.assertEqual(json.loads(out.read_text())['source_probe_sha256'],result['source_probe_sha256'])
        with self.assertRaises(ValueError):handoff.run(self.video,self.config,self.probe,out)

    def test_reject_invalid_roi(self):
        self.config.write_text(json.dumps({'slots':[{'table_id':1,'x':350,'y':0,'width':320,'height':480},
            {'table_id':2,'x':320,'y':0,'width':320,'height':480}],
            'felt_rgb':[42,50,86],'tolerance':40}), 'utf-8')
        self.report['source_layout_sha256']=handoff.sha256(self.config)
        self.save()
        with self.assertRaises(ValueError):self.build()

    def test_odd_roi_remains_event_but_no_clip(self):
        cfg = json.loads(self.config.read_text()); cfg['slots'][0]['x']=1;cfg['slots'][0]['width']=319
        self.config.write_text(json.dumps(cfg),'utf-8')
        self.report['source_layout_sha256']=handoff.sha256(self.config)
        self.save()
        result=self.build()
        self.assertEqual(len(result['events']),2)
        self.assertEqual([d['table_id'] for d in result['unapproved_clip_request_drafts']],[2])

if __name__=='__main__':unittest.main(verbosity=2)
