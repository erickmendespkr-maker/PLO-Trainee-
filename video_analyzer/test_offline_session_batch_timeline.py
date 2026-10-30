"""Synthetic tests for verified multi-batch offline timeline; no real poker video."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_session_batch_timeline as timeline
import offline_session_batch_planner as planner
import offline_session_batch_history as history
from test_offline_reviewed_hand_math_queue import fixture


class TimelineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.plan, self.ann = fixture()
        self.plan['clips'] = []
        self.ann['hands'] = []
        for n in range(102):
            self.plan['clips'].append({'hand_id': f'H{n:04d}',
                'table_id': f'T{n%4+1}', 'start_seconds': (n//4)*5,
                'end_seconds': (n//4)*5+4,
                'review_basis': 'human_declared_boundaries_not_automatic_detection'})
        one = copy.deepcopy(fixture()[1]['hands'][0])
        one['hand_id'], one['table_id'] = 'H0000', 'T1'
        one['card_evidence'] = [{**x, 'pts_seconds': 1} for x in one['card_evidence']]
        self.ann['hands'] = [one]
        self.plan_file = self.root/'plan.json'
        self.ann_file = self.root/'annotations.json'
        self.batches = self.root/'batches'
        self.workspace = self.root/'workspace'
        self.workspace.mkdir()
        self.plan_file.write_bytes(planner.encode(self.plan))
        self.ann['source_plan_sha256'] = planner.q.digest(self.plan_file)
        self.ann_file.write_bytes(planner.encode(self.ann))
        planner.process(self.plan_file, self.ann_file, self.batches)
        history.process(self.plan_file, self.ann_file, self.batches,
                        self.workspace/'results', max_new=2)

    def run_timeline(self, **kw):
        return timeline.process(self.plan_file, self.ann_file,
                                self.batches, self.workspace, **kw)

    def add_clip(self, *, corrupt=False, wrong_table=False):
        folder = self.workspace/'clips/batch-0001'
        folder.mkdir(parents=True)
        hand = 'H0000'
        clip = folder/(hand+'.mp4')
        # Actual FFmpeg video; no claims of visual poker recognition.
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                        'color=c=blue:s=64x64:d=1','-c:v','mpeg4','-y',str(clip)],
                       check=True, capture_output=True)
        digest = timeline.gallery.sha(clip)
        side = {'schema_version':1, 'analysis_status':'manually_selected_offline_clip',
                'hand_id':hand, 'clip_sha256':digest,
                'source_video_sha256':self.plan['source_video_sha256'],
                'video_evidence_verified':False,
                'automatic_clip_selection_authorized':False,
                'start_seconds':0, 'end_seconds':4,
                'explanation':'Revisão humana <sem> confirmação de cartas'}
        (folder/(hand+'.mp4.json')).write_text(json.dumps(side))
        manifest = {'schema_version':1, 'status':'human_reviewed_clips_not_verified_hands',
                    'automatic_hand_detection':False, 'equity_or_ev_calculated':False,
                    'source_video_sha256':self.plan['source_video_sha256'],
                    'source_plan_sha256':planner.q.digest(self.batches/'batch-0001/plan.json'),
                    'clips':[{'hand_id':hand, 'source_table_id':'T2' if wrong_table else 'T1',
                              'file':hand+'.mp4', 'sidecar':hand+'.mp4.json',
                              'clip_sha256':digest}]}
        (folder/'manifest.json').write_text(json.dumps(manifest))
        if corrupt:
            clip.write_bytes(clip.read_bytes()+b'bad')
        return folder

    def test_two_batches_four_tables_and_verify(self):
        result = self.run_timeline()
        self.assertEqual((result['hands'], result['tables'], result['clips']), (102,4,0))
        self.assertTrue(result['complete'])
        html = (self.workspace/timeline.OUTPUT).read_text()
        self.assertIn('H0101', html)
        self.assertIn('Ranges', html)
        self.assertIn('results/batch-0001/hands/H0000.json', html)
        self.assertNotIn('<video ', html)
        self.assertTrue(self.run_timeline(verify=True)['verified'])

    def test_valid_ffmpeg_clip_is_linked(self):
        self.add_clip()
        self.assertEqual(self.run_timeline()['clips'], 1)
        html = (self.workspace/timeline.OUTPUT).read_text()
        self.assertIn('clips/batch-0001/H0000.mp4', html)
        self.assertIn('&lt;sem&gt;', html)
        self.assertTrue(self.run_timeline(verify=True)['verified'])

    def test_reject_modified_video(self):
        self.add_clip(corrupt=True)
        with self.assertRaisesRegex(ValueError, 'MP4 hash mismatch'):
            self.run_timeline()

    def test_reject_wrong_table_clip(self):
        self.add_clip(wrong_table=True)
        with self.assertRaisesRegex(ValueError, 'clip does not match'):
            self.run_timeline()

    def test_reject_tampered_clip_manifest(self):
        folder = self.add_clip()
        manifest = folder/'manifest.json'
        value = json.loads(manifest.read_text())
        value['source_plan_sha256'] = '0'*64
        manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'not bound'):
            self.run_timeline()

    def test_reject_unexpected_clip_directory(self):
        (self.workspace/'clips/rogue').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'unexpected clip batch'):
            self.run_timeline()

    def test_reject_tampered_history(self):
        f = self.workspace/'results/session_history.json'
        data = json.loads(f.read_text())
        data['hands'][0]['table_id'] = 'FAKE'
        f.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'history differs'):
            self.run_timeline()

    def test_reject_tampered_math(self):
        f = self.workspace/'results/batch-0001/hands/H0000.json'
        f.write_bytes(f.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.run_timeline()

    def test_refuse_overwrite_and_detect_html_change(self):
        self.run_timeline()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_timeline()
        f = self.workspace/timeline.OUTPUT
        f.write_bytes(f.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.run_timeline(verify=True)

    def test_partial_history_is_labeled(self):
        # Build independent one-batch prefix in a separate workspace.
        partial = self.root/'partial'
        partial.mkdir()
        history.process(self.plan_file, self.ann_file, self.batches,
                        partial/'results', max_new=1)
        data = timeline.process(self.plan_file,self.ann_file,self.batches,partial)
        self.assertFalse(data['complete'])
        self.assertEqual(data['hands'],100)
        self.assertIn('Parcial', (partial/timeline.OUTPUT).read_text())

    def test_symlink_clip_root_rejected(self):
        folder = self.root/'external'
        folder.mkdir()
        try:
            (self.workspace/'clips').symlink_to(folder, target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'invalid clips root'):
            self.run_timeline()

    def test_symlink_output_rejected(self):
        target = self.root/'external.html'
        target.write_text('x')
        try:
            (self.workspace/timeline.OUTPUT).symlink_to(target)
        except (OSError,NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'symlink output'):
            self.run_timeline()


class RenderScaleTests(unittest.TestCase):
    def test_render_4000_synthetic_blocked_records(self):
        groups = {}
        for t in range(4):
            rows = []
            for n in range(1000):
                rows.append({'hand_id': f'H{t}-{n}', 'table_id': f'T{t+1}',
                             'start_seconds': n*3.5, 'end_seconds': n*3.5+3,
                             'status': 'blocked_not_analyzed',
                             'blocked_reasons': ['no confirmed cards']})
            groups[f'T{t+1}'] = rows
        state = {'total_hands_reviewed':4000, 'completed_batches':40,
                 'total_batches':40, 'complete':True}
        page = timeline.render(state, groups, {})
        self.assertEqual(page.count('<details id="hand-'), 4000)
        self.assertLess(len(page.encode('utf-8')), 2_500_000)
        self.assertNotIn('<video ', page)


if __name__ == '__main__':
    unittest.main()
