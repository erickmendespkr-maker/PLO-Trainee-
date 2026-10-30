"""Synthetic, offline tests for strict clip-to-Monte-Carlo provenance binding."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import offline_reviewed_hand_math_queue as q
import offline_reviewed_math_runner as runner
import offline_reviewed_math_clip_gallery as bridge
from test_offline_reviewed_hand_math_queue import fixture


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')


class MathClipGalleryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan, self.ann = fixture()
        self.plan_path = self.root / 'plan.json'
        self.ann_path = self.root / 'annotations.json'
        self.queue_path = self.root / 'queue.json'
        self.workspace = self.root / 'workspace'
        self.clips = self.workspace / 'clips'
        self.math = self.workspace / 'math'
        self.clips.mkdir(parents=True)
        self.prepare()

    def prepare(self):
        dump(self.plan_path, self.plan)
        self.ann['source_plan_sha256'] = q.digest(self.plan_path)
        dump(self.ann_path, self.ann)
        queue = q.build(self.plan, self.ann, q.digest(self.plan_path), q.digest(self.ann_path))
        dump(self.queue_path, queue)
        runner.run(self.plan_path, self.ann_path, self.queue_path, self.math)
        self.make_clips()

    def make_clips(self):
        rows = []
        for plan_clip in self.plan['clips']:
            hand = plan_clip['hand_id']
            raw = b'FAKE MP4 SYNTHETIC UNIT TEST ' + hand.encode('ascii')
            (self.clips / (hand + '.mp4')).write_bytes(raw)
            clip_sha = hashlib.sha256(raw).hexdigest()
            sidecar = {'schema_version': 1, 'analysis_status': 'manually_selected_offline_clip',
                       'hand_id': hand, 'start_seconds': plan_clip['start_seconds'],
                       'end_seconds': plan_clip['end_seconds'],
                       'explanation': 'Synthetic manual clip, not a recognized poker hand.',
                       'clip_sha256': clip_sha,
                       'source_video_sha256': self.plan['source_video_sha256'],
                       'video_evidence_verified': False,
                       'automatic_clip_selection_authorized': False}
            dump(self.clips / (hand + '.mp4.json'), sidecar)
            rows.append({'hand_id': hand, 'file': hand + '.mp4',
                         'clip_sha256': clip_sha, 'sidecar': hand + '.mp4.json',
                         'source_table_id': plan_clip['table_id']})
        manifest = {'schema_version': 1,
                    'status': 'human_reviewed_clips_not_verified_hands',
                    'source_video_sha256': self.plan['source_video_sha256'],
                    'source_plan_sha256': q.digest(self.plan_path),
                    'automatic_hand_detection': False, 'equity_or_ev_calculated': False,
                    'clips': rows}
        dump(self.clips / 'manifest.json', manifest)

    def generate(self):
        return bridge.process(self.plan_path, self.ann_path, self.queue_path, self.workspace)

    def verify(self):
        return bridge.process(self.plan_path, self.ann_path, self.queue_path,
                              self.workspace, verify=True)

    def test_two_table_mixed_math_and_blocked(self):
        summary = self.generate()
        self.assertEqual((summary['clips'], summary['calculated'], summary['blocked']), (2,1,1))
        html = (self.workspace/'index.html').read_text()
        self.assertIn('25.83%', html)
        self.assertIn('Sem cálculo', html)
        self.assertIn('math/hands/H001.json', html)
        self.assertIn('clips/H001.mp4', html)
        self.assertIn('não é avaliação da ação real', html)
        self.assertTrue(self.verify()['verified'])

    def test_html_is_deterministic(self):
        self.generate()
        first = (self.workspace/'index.html').read_bytes()
        self.assertEqual(first, bridge.render(bridge.assemble(self.plan_path,
                         self.ann_path,self.queue_path,self.workspace)).encode())

    def test_no_overwrite(self):
        self.generate()
        with self.assertRaisesRegex(ValueError,'already exists'):
            self.generate()

    def test_dashboard_tampering_detected(self):
        self.generate()
        path = self.workspace/'index.html'
        path.write_text(path.read_text() + 'tamper')
        with self.assertRaisesRegex(ValueError,'differs'):
            self.verify()

    def test_escaped_user_explanation(self):
        sidecar = self.clips/'H001.mp4.json'
        obj = json.loads(sidecar.read_text())
        obj['explanation'] = '<img src=x onerror=alert(1)> & testing'
        dump(sidecar, obj)
        self.generate()
        html = (self.workspace/'index.html').read_text()
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;img src=x', html)
        self.assertIn('&amp; testing', html)

    def test_wrong_plan_digest_rejected(self):
        path = self.clips/'manifest.json'
        obj = json.loads(path.read_text())
        obj['source_plan_sha256'] = '0'*64
        dump(path,obj)
        with self.assertRaisesRegex(ValueError,'reviewed plan'):
            self.generate()
        self.assertFalse((self.workspace/'index.html').exists())

    def test_wrong_video_digest_rejected(self):
        path = self.clips/'manifest.json'
        obj = json.loads(path.read_text())
        obj['source_video_sha256'] = '0'*64
        dump(path,obj)
        with self.assertRaisesRegex(ValueError,'video'):
            self.generate()

    def test_cross_table_clip_rejected(self):
        path = self.clips/'manifest.json'
        obj = json.loads(path.read_text())
        obj['clips'][0]['source_table_id'] = 'T2'
        dump(path,obj)
        with self.assertRaisesRegex(ValueError,'table identity'):
            self.generate()

    def test_shifted_clip_timestamp_rejected(self):
        path = self.clips/'H001.mp4.json'
        obj = json.loads(path.read_text())
        obj['start_seconds'] = 12.5
        dump(path,obj)
        with self.assertRaisesRegex(ValueError,'timestamp mismatch'):
            self.generate()

    def test_tampered_clip_bytes_rejected(self):
        with (self.clips/'H001.mp4').open('ab') as f:
            f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'MP4 hash mismatch'):
            self.generate()

    def test_tampered_math_payload_rejected(self):
        with (self.math/'hands/H001.json').open('ab') as f:
            f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'digest mismatch'):
            self.generate()

    def test_tampered_math_manifest_rejected(self):
        path = self.math/'manifest.json'
        obj = json.loads(path.read_text())
        obj['hands'][0]['table_id'] = 'T2'
        dump(path,obj)
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            self.generate()

    def test_queue_changed_rejected(self):
        path = self.queue_path
        obj = json.loads(path.read_text())
        obj['entries'][0]['equity_input']['seed'] = 99
        dump(path,obj)
        with self.assertRaisesRegex(ValueError,'queue does not match'):
            self.generate()

    def test_clip_symlink_rejected(self):
        path = self.clips/'H001.mp4'
        other = self.root/'real.mp4'
        path.rename(other)
        path.symlink_to(other)
        with self.assertRaisesRegex(ValueError,'linked file'):
            self.generate()

    def test_workspace_symlink_rejected(self):
        alias = self.root/'alias'
        alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'invalid workspace'):
            bridge.process(self.plan_path,self.ann_path,self.queue_path,alias)

    def test_html_symlink_rejected(self):
        (self.workspace/'index.html').symlink_to(self.plan_path)
        with self.assertRaisesRegex(ValueError,'linked HTML'):
            self.generate()

    def test_four_tables_with_plo6(self):
        self.math.rename(self.root/'old_math')
        for p in self.clips.iterdir():
            p.unlink()
        for i in (3,4):
            self.plan['clips'].append({'hand_id':f'H00{i}', 'table_id':f'T{i}',
                'start_seconds':i*10., 'end_seconds':i*10.+10.,
                'review_basis':'human_declared_boundaries_not_automatic_detection'})
        self.ann['hands'][0]['variant'] = 'PLO6'
        self.ann['hands'][0]['hero_cards'].append('9s')
        self.ann['hands'][0]['card_evidence'].append(
            {'card':'9s','pts_seconds':16.,'source':'human_frame_review'})
        self.prepare()
        self.assertEqual(self.generate()['clips'],4)
        self.assertIn('PLO6', (self.workspace/'index.html').read_text())
        self.assertTrue(self.verify()['verified'])

    def test_missing_clip_allowed_but_reported(self):
        manifest_path = self.clips/'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['clips'] = manifest['clips'][:1]
        dump(manifest_path, manifest)
        self.assertEqual(self.generate()['clips'],1)
        self.assertIn('1 mão(s) sem corte', (self.workspace/'index.html').read_text())

    def test_unlisted_clip_hand_rejected(self):
        path = self.clips/'manifest.json'
        obj = json.loads(path.read_text())
        obj['clips'][0]['hand_id'] = 'H999'
        dump(path,obj)
        with self.assertRaises(ValueError):
            self.generate()

    def test_cli_generate_and_verify(self):
        args = [str(self.plan_path),str(self.ann_path),str(self.queue_path),str(self.workspace)]
        self.assertEqual(bridge.main(args),0)
        self.assertEqual(bridge.main(['--verify']+args),0)


if __name__ == '__main__':
    unittest.main()
