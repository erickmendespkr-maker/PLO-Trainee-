import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import offline_manual_roi_review as m
import offline_four_table_visual_timeline as core


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class TestROIReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.fixture_dir.name) / 'synthetic_four_tables.mp4'
        filters = ','.join(
            f"drawbox=x={x}:y={y}:w=160:h=96:color=white:t=fill:enable='gte(t,{time})'"
            for x, y, time in [(0, 0, 2), (160, 0, 4), (0, 96, 6), (160, 96, 8)])
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'color=c=black:s=320x192:r=5:d=12',
                        '-vf', filters, '-c:v', 'mpeg4', '-q:v', '2', '-an', str(cls.fixture)],
                       check=True, capture_output=True, timeout=25)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_dir.cleanup()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.video = self.fixture
        self.config = {'schema_version': 1, 'tables': [
            {'table_id': f'table_{i+1}', 'normalized_rect': rect}
            for i, rect in enumerate(([0, 0, .5, .5], [.5, 0, .5, .5],
                                      [0, .5, .5, .5], [.5, .5, .5, .5]))]}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root)

    def test_rois_four_quadrants(self):
        rois = m.validate_rois(self.config)
        self.assertEqual([r['pixel_rect'] for r in rois],
                         [[0, 0, 80, 48], [80, 0, 80, 48], [0, 48, 80, 48], [80, 48, 80, 48]])

    def test_custom_roi_ffmpeg_pts(self):
        timeline = m.custom_timeline(self.video, self.config)
        self.assertEqual([t['events'][0]['pts_seconds'] for t in timeline['tables']], [2, 4, 6, 8])
        self.assertFalse(timeline['hand_boundaries_verified'])
        self.assertEqual(timeline['roi_origin'], 'human_configured_not_automatically_detected')
        self.assertEqual(timeline['sampled_frame_count'], 12)

    def test_small_offset_roi(self):
        c = {'schema_version': 1, 'tables': [{'table_id': 'left', 'normalized_rect': [.1, .1, .3, .3]}]}
        self.assertEqual(m.validate_rois(c)[0]['pixel_rect'], [16, 10, 48, 28])

    def test_overlap_rejected(self):
        c = {'schema_version': 1, 'tables': [
            {'table_id': 'one', 'normalized_rect': [0, 0, .6, .6]},
            {'table_id': 'two', 'normalized_rect': [.5, .5, .5, .5]}]}
        with self.assertRaises(core.TimelineError): m.validate_rois(c)

    def test_duplicate_table_rejected(self):
        self.config['tables'][1]['table_id'] = 'table_1'
        with self.assertRaises(core.TimelineError): m.validate_rois(self.config)

    def test_bad_rectangles_rejected(self):
        for rect in ([0, 0, 0, .5], [.9, .9, .2, .2], [0, 0, True, .5],
                     [0, 0, .01, .01], [0, 0, float('nan'), .5]):
            with self.subTest(rect=rect), self.assertRaises(core.TimelineError):
                m.validate_rois({'schema_version': 1, 'tables': [
                    {'table_id': 'a', 'normalized_rect': rect}]})

    def timeline(self):
        return m.custom_timeline(self.video, self.config)

    def decisions(self, decision='confirmed_hand'):
        item = {'table_id': 'table_1', 'candidate_index': 0, 'decision': decision}
        if decision == 'confirmed_hand':
            item.update(hand_id='H001', start_seconds=1.2, end_seconds=3.4)
        return {'schema_version': 1, 'reviews': [item]}

    def plan(self, timeline=None, decisions=None):
        return m.review_plan(self.video, timeline or self.timeline(), decisions or self.decisions(), 'a'*64, 'b'*64)

    def test_review_confirmed_clip(self):
        result = self.plan()
        self.assertEqual(result['clips'][0]['hand_id'], 'H001')
        self.assertEqual(result['clips'][0]['duration_seconds'], 2.2)
        self.assertFalse(result['clip_mp4_exported'])
        self.assertFalse(result['equity_or_ev_calculated'])
        self.assertEqual(result['reviews'][0]['candidate_window']['start_seconds'], 1)

    def test_uncertain_and_not_hand_not_exported(self):
        for decision in ('uncertain', 'not_hand'):
            with self.subTest(decision=decision):
                self.assertEqual(self.plan(decisions=self.decisions(decision))['clips'], [])

    def test_duplicate_review_rejected(self):
        d = self.decisions(); d['reviews'].append(d['reviews'][0].copy())
        with self.assertRaises(core.TimelineError): self.plan(decisions=d)

    def test_bad_candidate_index_rejected(self):
        d = self.decisions(); d['reviews'][0]['candidate_index'] = 9
        with self.assertRaises(core.TimelineError): self.plan(decisions=d)

    def test_unconfirmed_boundaries_rejected(self):
        d = self.decisions('uncertain'); d['reviews'][0]['start_seconds'] = 1
        with self.assertRaises(core.TimelineError): self.plan(decisions=d)

    def test_bad_boundaries_rejected(self):
        for a, b in ((2, 2), (3, 1), (-1, 2), (0, 400), (1, float('nan'))):
            d = self.decisions(); d['reviews'][0].update(start_seconds=a, end_seconds=b)
            with self.subTest(a=a, b=b), self.assertRaises(core.TimelineError):
                self.plan(decisions=d)

    def test_video_hash_mismatch_rejected(self):
        t = self.timeline(); t['video_sha256'] = '0'*64
        with self.assertRaises(core.TimelineError): self.plan(timeline=t)

    def test_video_duration_mismatch_rejected(self):
        t = self.timeline(); t['video']['duration_seconds'] = 11
        with self.assertRaises(core.TimelineError): self.plan(timeline=t)

    def test_review_hash_mismatch_rejected(self):
        d = self.decisions(); d['video_sha256'] = '0'*64
        with self.assertRaises(core.TimelineError): self.plan(decisions=d)

    def test_invalid_json_rejected(self):
        p = self.root / 'bad.json'; p.write_text('{"v": NaN}')
        with self.assertRaises(core.TimelineError): m.load_object(p)

    def test_output_exclusive(self):
        p = self.root / 'out.json'; p.write_text('{}')
        with self.assertRaises(core.TimelineError): m.new_output(p, [self.video])

    def test_cli_end_to_end(self):
        rois = self.root / 'rois.json'; rois.write_text(json.dumps(self.config))
        timeline = self.root / 'timeline.json'
        self.assertEqual(m.main(['analyze', str(self.video), str(rois), str(timeline)]), 0)
        self.assertEqual(json.loads(timeline.read_text())['roi_config_sha256'], core.sha256_file(rois))
        decisions = self.root / 'decisions.json'; decisions.write_text(json.dumps(self.decisions()))
        plan = self.root / 'plan.json'
        self.assertEqual(m.main(['review', str(self.video), str(timeline), str(decisions), str(plan)]), 0)
        result = json.loads(plan.read_text())
        self.assertEqual(result['source_timeline_sha256'], core.sha256_file(timeline))
        self.assertEqual(len(result['clips']), 1)

    def test_no_hidden_cards_claims(self):
        result = self.plan()
        self.assertNotIn('cards', result)
        self.assertNotIn('hand_equity', result)
        self.assertEqual(result['status'], 'human_reviewed_clip_plan_not_automated_hand_detection')


if __name__ == '__main__':
    unittest.main()
