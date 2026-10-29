"""Fail-closed synthetic contract tests; mocked replay/viewer are not real media proof."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import offline_selected_roi_clip_binding as mod


class SelectedROIClipBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.args = [root / n for n in ('video.mp4','regions.json','ingest','changes.json',
                    'refined','tasks.json','ocr','reviewed.json','drafts.json',
                    'timeline.json','triage.json','bundle')]
        for i, p in enumerate(self.args):
            if i in (2,4,6,11): p.mkdir()
            else: p.write_text('placeholder')
        self.video,self.regions,self.ingest,self.changes,self.refined,self.tasks,self.ocr,\
        self.reviewed,self.drafts,self.timeline,self.triage,self.bundle = self.args
        (self.ocr/'roi_ocr_proposals.json').write_text('ocr')
        (self.ocr/'roi_002.png').write_bytes(b'fake png')
        (self.bundle/'reviewed_clip').mkdir()
        (self.bundle/'reviewed_clip'/'clip.mp4').write_bytes(b'clip')
        self.out = root/'binding.json'
        self.candidate = {'hand_id':'H4','table_id':4,'variant':'PLO6',
            'proposal_index':2,'timestamp_seconds':5.0,'action_ocr':'raise',
            'clip_export_authorized':False}
        self.timeline_doc = {'hands':[]}
        self.triage_expected = {'candidates':[self.candidate]}
        self.triage_doc = dict(self.triage_expected, source_timeline_sha256=mod.sha(self.timeline))
        self.triage.write_text(json.dumps(self.triage_doc))
        self.viewer_doc = {'hands':[{'hand_id':'H4','table_id':4,
            'events':[{'proposal_index':2,'field':'action','value':'raise',
                       'timestamp_seconds':5.0,'review':'corrected',
                       'roi_png':'assets/roi_002.png',
                       'roi_png_sha256':mod.sha(self.ocr/'roi_002.png')}]}]}
        self.audit_doc = {'source_video_to_frame_to_roi_reproduced':True,
            'source_video_sha256':mod.sha(self.video),
            'source_roi_ocr_report_sha256':mod.sha(self.ocr/'roi_ocr_proposals.json'),
            'ocr_semantics_verified':False,'ready_for_equity_or_ev':False}
        self.link = {'hand_id':'H4','proposal_index':2,'table_id':4,
            'timestamp_seconds':5.0,'action_ocr':'raise',
            'source_timeline_sha256':mod.sha(self.timeline),
            'source_triage_sha256':mod.sha(self.triage),
            'source_hand_drafts_sha256':mod.sha(self.drafts),
            'source_video_sha256':mod.sha(self.video),
            'clip_sha256':mod.sha(self.bundle/'reviewed_clip'/'clip.mp4'),
            'ready_for_equity_or_ev':False,'actor_identified':False,
            'clip_start_seconds':3.0,'clip_end_seconds':8.0}
        self.manifest = {'clip_sha256':self.link['clip_sha256'],
            'source_video_sha256':mod.sha(self.video),'ready_for_equity_or_ev':False}
        self.att = {'analysis_status':'offline_source_replayed_triage_clip_media_only',
            'source_video_to_frame_to_roi_reproduced':True,
            'source_video_matches_clip_source_verified':True,
            'ocr_text_linked_to_replayed_roi_verified':False,
            'ready_for_equity_or_ev':False,
            'source_video_sha256':mod.sha(self.video),
            'source_roi_ocr_report_sha256':mod.sha(self.ocr/'roi_ocr_proposals.json'),
            'clip_sha256':self.link['clip_sha256'],
            'hand_id':'H4','proposal_index':2}
        self.write_bundle()

    def write_bundle(self):
        folder = self.bundle/'reviewed_clip'
        (folder/'triage_clip_link.json').write_text(json.dumps(self.link))
        (folder/'manifest.json').write_text(json.dumps(self.manifest))
        self.att['clip_manifest_sha256']=mod.sha(folder/'manifest.json')
        self.att['triage_clip_link_sha256']=mod.sha(folder/'triage_clip_link.json')
        (self.bundle/'source_replay_clip_attestation.json').write_text(json.dumps(self.att))

    def build_viewer(self, ocr, reviewed, drafts, timeline, output):
        (Path(output)/'assets').mkdir(parents=True)
        (Path(output)/'assets'/'roi_002.png').write_bytes((self.ocr/'roi_002.png').read_bytes())
        return self.viewer_doc

    def invoke(self, **kwargs):
        with mock.patch.object(mod,'replay_audit',return_value=self.audit_doc), \
             mock.patch.object(mod,'build_viewer',side_effect=self.build_viewer), \
             mock.patch.object(mod,'build_triage',return_value=self.triage_expected), \
             mock.patch.object(mod,'load',side_effect=self.mock_load):
            return mod.bind(*self.args,'H4',2,kwargs.get('output',self.out))

    def mock_load(self,path):
        if Path(path)==self.timeline:return self.timeline_doc
        return json.loads(Path(path).read_text())

    def rejected(self):
        with self.assertRaises((ValueError, TypeError, KeyError)):
            self.invoke()
        self.assertFalse(self.out.exists())

    def test_happy_path_contract(self):
        result=self.invoke()
        self.assertTrue(result['selected_action_to_replayed_roi_verified'])
        self.assertFalse(result['ocr_semantics_verified'])
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertEqual(json.loads(self.out.read_text()),result)

    def test_existing_output_rejected(self):
        self.out.write_text('do not replace')
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(self.out.read_text(),'do not replace')

    def test_untrusted_action_index(self):
        self.candidate['proposal_index']=3
        self.rejected()

    def test_wrong_table(self):
        self.viewer_doc['hands'][0]['table_id']=1
        self.rejected()

    def test_wrong_roi_hash(self):
        self.viewer_doc['hands'][0]['events'][0]['roi_png_sha256']='0'*64
        self.rejected()

    def test_roi_mutation(self):
        (self.ocr/'roi_002.png').write_bytes(b'mutated')
        self.rejected()

    def test_timeline_hash_changed(self):
        self.timeline.write_text('changed')
        self.rejected()

    def test_wrong_clip_source(self):
        self.link['source_video_sha256']='0'*64
        self.write_bundle()
        self.rejected()

    def test_wrong_clip_hash(self):
        (self.bundle/'reviewed_clip'/'clip.mp4').write_bytes(b'mutated')
        self.rejected()

    def test_wrong_clip_timestamp(self):
        self.link['clip_end_seconds']=5.0
        self.write_bundle()
        self.rejected()

    def test_wrong_selected_action(self):
        self.link['action_ocr']='fold'
        self.write_bundle()
        self.rejected()

    def test_false_semantics_promotion(self):
        self.audit_doc['ocr_semantics_verified']=True
        self.rejected()

    def test_false_equity_promotion(self):
        self.att['ready_for_equity_or_ev']=True
        self.write_bundle()
        self.rejected()

    def test_duplicate_json_keys(self):
        (self.bundle/'reviewed_clip'/'manifest.json').write_text('{"a":1,"a":2}')
        self.rejected()

    def test_missing_clip(self):
        (self.bundle/'reviewed_clip'/'clip.mp4').unlink()
        self.rejected()

    def test_symlink_roi(self):
        roi=self.ocr/'roi_002.png'
        target=self.ocr/'actual.png'
        roi.rename(target)
        roi.symlink_to(target)
        self.rejected()

    def test_output_inside_ocr_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke(output=self.ocr/'new.json')

    def test_output_inside_bundle_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke(output=self.bundle/'new.json')


if __name__=='__main__': unittest.main()
