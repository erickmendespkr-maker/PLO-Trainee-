"""Portable synthetic FFmpeg integration tests for the offline EV review gate."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_human_observation_review import build as build_review
from offline_review_ev_gate import build, render_html


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise unittest.SkipTest('FFmpeg and FFprobe required for media integration')
        cls.fixture_dir = tempfile.TemporaryDirectory()
        root = Path(cls.fixture_dir.name)
        cls.fixture_video = root / 'synthetic_recording.mp4'
        cls.fixture_clips = root / 'exported_batch'
        cls.fixture_clips.mkdir()
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi',
                        '-i','testsrc2=size=640x360:rate=12','-t','4','-an',
                        '-c:v','mpeg4','-y',str(cls.fixture_video)],check=True,timeout=30)
        for i in range(1,5):
            clip = cls.fixture_clips / f'table{i}.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(cls.fixture_video),
                            '-t','2','-an','-c:v','mpeg4','-y',str(clip)],check=True,timeout=30)
            probe = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration',
                                    '-of','default=noprint_wrappers=1:nokey=1',str(clip)],
                                   check=True,capture_output=True,text=True,timeout=15)
            assert abs(float(probe.stdout.strip())-2)<0.1
        rows=[]
        for i in range(1,5):
            rows.append({'table_id':i,'hand_id':f'hand{i}','decision_id':f'd{i}',
                         'game_type':'PLO5' if i%2 else 'PLO6',
                         'clip_file':f'table{i}.mp4',
                         'clip_sha256':digest(cls.fixture_clips/f'table{i}.mp4'),
                         'clip_window_seconds':[0.0,2.0],
                         'candidate_window_seconds':[0.25,1.75],
                         'action_pts_seconds':1.0,'observed_action':'call',
                         'human_review_status':'pending','model_conditional_only':True,
                         'decision_quality_verified':False,
                         'observed_ev_interval_units':['20','30'],
                         'review_label':'overlapping_intervals_manual_review'})
        cls.packet = {'schema_version':1,
                      'analysis_status':'offline_read_only_human_review_packet',
                      'source_recording_sha256':digest(cls.fixture_video),
                      'human_review_recorded':False,
                      'video_evidence_independently_verified':False,
                      'range_assumptions_verified':False,
                      'decision_quality_verified':False,
                      'automatic_clip_selection_authorized':False,
                      'action_recommendation_authorized':False,
                      'clip_media_hashes_rechecked':True,'ffprobe_media_checked':True,
                      'decision_count':4,'clip_count':4,'decisions':rows}

    @classmethod
    def tearDownClass(cls):
        cls.fixture_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.video=self.root/'recording.mp4'
        self.clips=self.root/'exported_batch'
        self.clips.mkdir()
        shutil.copyfile(self.fixture_video,self.video)
        for clip in self.fixture_clips.glob('*.mp4'):
            shutil.copyfile(clip,self.clips/clip.name)
        self.source=self.root/'session_review.json'
        self.source.write_text(json.dumps(self.packet),encoding='utf-8')
        self.manual=self.root/'manual_annotations.json'
        self.manual.write_text(json.dumps({'schema_version':1,
            'source_session_review_sha256':digest(self.source),'reviewer_alias':'reviewer_local',
            'entries':[
                {'table_id':1,'hand_id':'hand1','decision_id':'d1','outcome':'confirmed',
                 'corrected_observed_action':None,'corrected_action_pts_seconds':None,'note':''},
                {'table_id':2,'hand_id':'hand2','decision_id':'d2','outcome':'corrected',
                 'corrected_observed_action':'raise','corrected_action_pts_seconds':1.25,
                 'note':'Ação corrigida após revisão visual.'},
                {'table_id':3,'hand_id':'hand3','decision_id':'d3','outcome':'inconclusive',
                 'corrected_observed_action':None,'corrected_action_pts_seconds':None,
                 'note':'Não foi possível observar claramente a ação.'}]}),encoding='utf-8')
        self.reviewed=self.root/'reviewed.json'
        build_review(self.video,self.clips,self.source,self.manual,
                     self.reviewed,self.root/'reviewed.html')
        self.output=self.root/'gate.json'
        self.html=self.root/'gate.html'

    def gate(self):
        return build(self.video,self.clips,self.source,self.manual,
                     self.reviewed,self.output,self.html)

    def edit(self,path,fn):
        obj=json.loads(path.read_text(encoding='utf-8'))
        fn(obj)
        path.write_text(json.dumps(obj),encoding='utf-8')

    def test_four_states_and_ev_suppression(self):
        result=self.gate()
        self.assertEqual([x['ev_interpretation_status'] for x in result['decisions']],[
            'conditional_model_only','blocked_stale_observation_requires_recalculation',
            'blocked_inconclusive_observation','blocked_pending_review'])
        self.assertEqual([x['may_display_hypothetical_ev'] for x in result['decisions']],
                         [True,False,False,False])
        self.assertEqual(result['decisions'][0]['observed_ev_interval_units'],['20','30'])
        self.assertTrue(all(x['observed_ev_interval_units'] is None for x in result['decisions'][1:]))
        self.assertFalse(result['equity_ev_recomputed'])
        self.assertEqual(sum(result['status_counts'].values()),4)

    def test_report_written_and_html_offline(self):
        result=self.gate()
        self.assertEqual(json.loads(self.output.read_text()),result)
        html=self.html.read_text()
        self.assertIn('blocked_stale_observation_requires_recalculation',html)
        self.assertNotIn('https://',html)
        self.assertNotIn('<script',html)

    def test_no_overwrite(self):
        self.output.write_text('keep')
        with self.assertRaises(ValueError): self.gate()
        self.assertEqual(self.output.read_text(),'keep')
        self.assertFalse(self.html.exists())

    def test_reject_modified_clip(self):
        with (self.clips/'table1.mp4').open('ab') as f:f.write(b'altered')
        with self.assertRaises(ValueError): self.gate()

    def test_reject_modified_recording(self):
        with self.video.open('ab') as f:f.write(b'altered')
        with self.assertRaises(ValueError): self.gate()

    def test_reject_modified_annotations(self):
        self.edit(self.manual,lambda d:d['entries'][0].update(note='changed'))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_modified_source(self):
        self.edit(self.source,lambda d:d.update(warning='changed'))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_modified_review(self):
        self.edit(self.reviewed,lambda d:d['decisions'][0].update(original_observed_action='raise'))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_promoted_ev(self):
        self.edit(self.reviewed,lambda d:d.update(equity_ev_recomputed=True))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_reordered_decisions(self):
        self.edit(self.reviewed,lambda d:d['decisions'].reverse())
        with self.assertRaises(ValueError): self.gate()

    def test_reject_symlink_clip(self):
        clip=self.clips/'table2.mp4'
        clip.rename(self.root/'saved.mp4')
        clip.symlink_to(self.root/'saved.mp4')
        with self.assertRaises(ValueError): self.gate()

    def test_html_escapes_user_identifiers(self):
        html=render_html({'decisions':[{'table_id':1,'hand_id':'<script>alert(1)</script>',
            'decision_id':'<img src=x>','ev_interpretation_status':'blocked_pending_review'}]})
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>alert',html)


if __name__=='__main__':unittest.main()
