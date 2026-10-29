"""Synthetic FFmpeg integration for human-reviewed clip plans."""
import json
import unittest

import offline_four_table_visual_timeline as core
import offline_review_plan_clip_bridge as bridge
from test_offline_manual_roi_review import TestROIReview


class TestClipBridge(TestROIReview):
    def payloads(self):
        timeline = self.timeline()
        decisions = self.decisions()
        plan = self.plan(timeline=timeline, decisions=decisions)
        explanations = {'explanations': {'H001': 'Revisor selecionou este intervalo sintético.'}}
        return timeline, plan, explanations

    def test_request_mapping_and_crop(self):
        timeline, plan, notes = self.payloads()
        requests = bridge.build_requests(self.video, plan, timeline, notes)
        self.assertEqual(requests[0][1]['crop'], {'x': 0, 'y': 0, 'width': 160, 'height': 96})
        self.assertEqual(requests[0][1]['table_id'], 1)
        self.assertTrue(requests[0][1]['reviewer_confirmed_offline'])

    def test_export_real_mp4_and_sidecar(self):
        timeline, plan, notes = self.payloads()
        tp = self.root / 'timeline.json'; tp.write_text(json.dumps(timeline))
        plan['source_timeline_sha256'] = core.sha256_file(tp)
        pp = self.root / 'plan.json'; pp.write_text(json.dumps(plan))
        np = self.root / 'notes.json'; np.write_text(json.dumps(notes))
        dest = self.root / 'export'
        result = bridge.export_bundle(self.video, pp, tp, np, dest)
        self.assertEqual(len(result['clips']), 1)
        self.assertTrue((dest / 'H001.mp4').is_file())
        self.assertTrue((dest / 'H001.mp4.json').is_file())
        self.assertEqual(result['clips'][0]['clip_sha256'], core.sha256_file(dest / 'H001.mp4'))
        self.assertFalse(result['automatic_hand_detection'])
        self.assertEqual(result['human_explanations_sha256'], core.sha256_file(np))

    def test_missing_human_explanation_rejected(self):
        t, p, _ = self.payloads()
        with self.assertRaises(core.TimelineError):
            bridge.build_requests(self.video, p, t, {'explanations': {}})

    def test_odd_crop_rejected(self):
        t, p, n = self.payloads()
        t['tables'][0]['source_pixel_rect'][0] = 1
        with self.assertRaises(ValueError): bridge.build_requests(self.video, p, t, n)

    def test_wrong_video_hash_rejected(self):
        t, p, n = self.payloads()
        p['source_video_sha256'] = '0'*64
        with self.assertRaises(core.TimelineError): bridge.build_requests(self.video, p, t, n)

    def test_unconfirmed_provenance_rejected(self):
        t, p, n = self.payloads()
        p['clips'][0]['review_basis'] = 'automatic'
        with self.assertRaises(core.TimelineError): bridge.build_requests(self.video, p, t, n)

    def test_no_overwrite(self):
        t, p, n = self.payloads()
        tp = self.root / 'timeline.json'; tp.write_text(json.dumps(t))
        p['source_timeline_sha256'] = core.sha256_file(tp)
        pp = self.root / 'plan.json'; pp.write_text(json.dumps(p))
        np = self.root / 'notes.json'; np.write_text(json.dumps(n))
        dest = self.root / 'existing'; dest.mkdir()
        with self.assertRaises(core.TimelineError): bridge.export_bundle(self.video, pp, tp, np, dest)


if __name__ == '__main__':
    unittest.main()
