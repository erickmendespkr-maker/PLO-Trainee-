import csv
import tempfile
import unittest
from pathlib import Path

try:
    from .poker_cortes_evidence_bridge import build_evidence_review, write_review_json
except ImportError:
    from poker_cortes_evidence_bridge import build_evidence_review, write_review_json

H = 'a'*64


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'report.csv'
        with self.path.open('w', encoding='utf8', newline='') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(['inicio','fim','mesa','status','perda_bb','rebuy_visto'])
            w.writerow(['00:00:01','00:00:09','1','PERDA','320','NAO'])
            w.writerow(['00:00:01','00:00:09','2','INCONCLUSIVO','','SIM'])

    def observation(self, table, t, stack):
        return {'video_sha256': H, 'table_id': table, 'time_seconds': t,
                'stack_bb': stack, 'source_frame': f'frame-{table}-{t}'}

    def build(self, obs):
        return build_evidence_review(self.path, obs, video_sha256=H, duration_seconds=20)

    def test_two_tables(self):
        result = self.build([self.observation(1,2,320), self.observation(1,8,0),
                             self.observation(2,5,90)])
        self.assertEqual(len(result['hands']),2)
        self.assertEqual([len(h['stack_samples']) for h in result['hands']],[2,1])

    def test_no_auto_confirm(self):
        r = self.build([self.observation(1,2,320), self.observation(1,8,0)])
        self.assertFalse(r['ev_authorized'])
        self.assertFalse(r['mp4_loss_label_authorized'])
        self.assertIsNone(r['hands'][0]['confirmed_loss_bb'])

    def test_unmatched(self):
        r = self.build([self.observation(1,12,50)])
        self.assertEqual(r['unresolved_observations'][0]['reason'],'NO_MATCHING_HAND')

    def test_reproducible(self):
        self.assertEqual(self.build([]),self.build([]))

    def test_row_ids(self):
        r = self.build([])
        self.assertEqual([h['hand_key']['hand_id'] for h in r['hands']], ['csv-row-2','csv-row-3'])

    def test_create_only(self):
        out = Path(self.tmp.name)/'review.json'
        write_review_json(self.build([]),out)
        with self.assertRaises(FileExistsError):
            write_review_json(self.build([]),out)

    def test_bad_hash(self):
        with self.assertRaises(ValueError):
            build_evidence_review(self.path,[],video_sha256='bad',duration_seconds=20)

    def test_invalid_observation(self):
        with self.assertRaises(ValueError):
            self.build([self.observation(1,-1,100)])

    def test_false_bust_flag(self):
        r = self.build([self.observation(1,2,320),self.observation(1,8,0)])
        self.assertIn('LARGE_STACK_JUMP_RECHECK_OCR',r['hands'][0]['flags'])


if __name__ == '__main__':
    unittest.main()
