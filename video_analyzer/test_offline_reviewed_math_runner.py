"""Offline synthetic integration tests: source binding -> Monte Carlo -> manifests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_reviewed_hand_math_queue as q
import offline_reviewed_math_runner as runner
from test_offline_reviewed_hand_math_queue import fixture


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan, self.ann = fixture()
        self.plan_path = self.root / 'plan.json'
        self.ann_path = self.root / 'annotations.json'
        self.queue_path = self.root / 'queue.json'
        self.dest = self.root / 'math'
        self.prepare()

    def prepare(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding='utf-8')
        self.ann['source_plan_sha256'] = q.digest(self.plan_path)
        self.ann_path.write_text(json.dumps(self.ann), encoding='utf-8')
        self.queued = q.build(self.plan, self.ann, q.digest(self.plan_path),
                              q.digest(self.ann_path))
        self.queue_path.write_text(json.dumps(self.queued), encoding='utf-8')

    def run_math(self, dest=None):
        return runner.run(self.plan_path, self.ann_path, self.queue_path, dest or self.dest)

    def test_real_monte_carlo_result_with_blocked_hand(self):
        manifest = self.run_math()
        self.assertEqual((manifest['eligible_analyzed_count'], manifest['blocked_count']), (1, 1))
        hand = manifest['hands'][0]
        self.assertEqual(hand['status'], 'offline_conditional_equity_computed')
        self.assertEqual(hand['iterations'], 120)
        result_file = self.dest / hand['result_file']
        self.assertEqual(q.digest(result_file), hand['result_sha256'])
        result = json.loads(result_file.read_text())
        self.assertEqual(sum(result[k] for k in ('win_count','tie_count','loss_count')), 120)
        self.assertEqual(result['seed'], 42)
        self.assertIsNotNone(result['terminal_call_ev_model'])
        self.assertIsNone(manifest['hands'][1]['result_file'])
        self.assertFalse(manifest['video_or_ocr_verified'])
        self.assertTrue(manifest['ci95_is_sampling_error_only'])

    def test_determinism_two_runs(self):
        self.run_math()
        other = self.root / 'math_again'
        self.run_math(other)
        self.assertEqual((self.dest/'manifest.json').read_bytes(),
                         (other/'manifest.json').read_bytes())
        self.assertEqual((self.dest/'hands/H001.json').read_bytes(),
                         (other/'hands/H001.json').read_bytes())

    def test_four_tables_and_plo6(self):
        for i in (3,4):
            self.plan['clips'].append({'hand_id':f'H00{i}', 'table_id':f'T{i}',
                'start_seconds':i*10., 'end_seconds':i*10.+10.,
                'review_basis':'human_declared_boundaries_not_automatic_detection'})
        self.ann['hands'][0]['variant'] = 'PLO6'
        self.ann['hands'][0]['hero_cards'].append('9s')
        self.ann['hands'][0]['card_evidence'].append(
            {'card':'9s','pts_seconds':16.,'source':'human_frame_review'})
        self.prepare()
        manifest = self.run_math()
        self.assertEqual(len(manifest['hands']),4)
        self.assertEqual(manifest['eligible_analyzed_count'],1)
        self.assertEqual(json.loads((self.dest/'hands/H001.json').read_text())['variant'],'PLO6')

    def test_known_royal_flush_equity_and_ev(self):
        hand = self.ann['hands'][0]
        hand['hero_cards'] = ['As','Ks','2c','3d','4c']
        hand['board_cards'] = ['Qs','Js','Ts','8d','7c']
        hand['card_evidence'] = [
            {'card':c,'pts_seconds':15.,'source':'human_frame_review'}
            for c in hand['hero_cards']+hand['board_cards']]
        hand['opponent_model'] = {'kind':'weighted_combos', 'combos':[
            {'cards':['2h','3h','4h','5h','6h'], 'weight':1}]}
        self.prepare()
        manifest = self.run_math()
        result = json.loads((self.dest/'hands/H001.json').read_text())
        self.assertEqual(result['equity'],1.)
        self.assertEqual(result['terminal_call_ev_model']['call_ev_incremental'],100.)
        self.assertEqual(manifest['hands'][0]['equity_ci95_sampling_only'],[1.,1.])

    def test_tampered_queue_rejected_before_output(self):
        tampered = json.loads(self.queue_path.read_text())
        tampered['entries'][0]['equity_input']['seed'] = 999
        self.queue_path.write_text(json.dumps(tampered))
        with self.assertRaisesRegex(ValueError,'queue does not match'):
            self.run_math()
        self.assertFalse(self.dest.exists())

    def test_tampered_plan_rejected(self):
        self.plan_path.write_text(self.plan_path.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'unbound'):
            self.run_math()
        self.assertFalse(self.dest.exists())

    def test_tampered_annotations_rejected(self):
        self.ann_path.write_text(self.ann_path.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'queue does not match'):
            self.run_math()
        self.assertFalse(self.dest.exists())

    def test_output_no_overwrite(self):
        self.run_math()
        with self.assertRaisesRegex(ValueError,'new directory'):
            self.run_math()

    def test_budget_rejected_before_output(self):
        self.ann['hands'][0]['iterations'] = 50000
        for i in range(3,8):
            self.plan['clips'].append({'hand_id':f'H{i:03d}','table_id':'T1',
                'start_seconds':float(i*20), 'end_seconds':float(i*20+10),
                'review_basis':'human_declared_boundaries_not_automatic_detection'})
            h = copy.deepcopy(self.ann['hands'][0])
            h['hand_id'] = f'H{i:03d}'
            for ev in h['card_evidence']:
                ev['pts_seconds'] = float(i*20+5)
            self.ann['hands'].append(h)
        self.prepare()
        with self.assertRaisesRegex(ValueError,'budget'):
            self.run_math()
        self.assertFalse(self.dest.exists())

    def test_symlink_input_rejected(self):
        alias = self.root/'alias.json'
        alias.symlink_to(self.queue_path)
        with self.assertRaisesRegex(ValueError,'invalid or oversized'):
            runner.run(self.plan_path,self.ann_path,alias,self.dest)
        self.assertFalse(self.dest.exists())

    def test_duplicate_json_key_rejected(self):
        self.queue_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError,'duplicate JSON'):
            self.run_math()

    def test_blocked_only_produces_manifest_without_hands(self):
        self.ann['hands'] = []
        self.prepare()
        result = self.run_math()
        self.assertEqual(result['eligible_analyzed_count'],0)
        self.assertEqual(result['blocked_count'],2)
        self.assertEqual(list((self.dest/'hands').iterdir()),[])

    def test_verify_success_and_cli(self):
        self.run_math()
        self.assertEqual(runner.verify_results(self.plan_path,self.ann_path,
                                               self.queue_path,self.dest)['verified'],1)
        self.assertEqual(runner.main(['--verify',str(self.plan_path),str(self.ann_path),
                                      str(self.queue_path),str(self.dest)]),0)

    def test_verify_rejects_tampered_result(self):
        self.run_math()
        path = self.dest/'hands/H001.json'
        path.write_text(path.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'digest mismatch'):
            runner.verify_results(self.plan_path,self.ann_path,self.queue_path,self.dest)

    def test_verify_rejects_extra_file(self):
        self.run_math()
        (self.dest/'extra.txt').write_text('unexpected')
        with self.assertRaisesRegex(ValueError,'unexpected or missing'):
            runner.verify_results(self.plan_path,self.ann_path,self.queue_path,self.dest)

    def test_verify_rejects_tampered_manifest(self):
        self.run_math()
        path = self.dest/'manifest.json'
        obj = json.loads(path.read_text())
        obj['hands'][0]['table_id'] = 'T4'
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'identity mismatch'):
            runner.verify_results(self.plan_path,self.ann_path,self.queue_path,self.dest)

    def test_verify_rejects_symlink(self):
        self.run_math()
        (self.dest/'other').symlink_to(self.dest/'manifest.json')
        with self.assertRaisesRegex(ValueError,'symlink'):
            runner.verify_results(self.plan_path,self.ann_path,self.queue_path,self.dest)

    def test_cli(self):
        self.assertEqual(runner.main([str(self.plan_path),str(self.ann_path),
                                      str(self.queue_path),str(self.dest)]),0)
        self.assertTrue((self.dest/'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
