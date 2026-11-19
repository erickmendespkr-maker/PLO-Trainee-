import hashlib
import tempfile
import unittest
from pathlib import Path
from offline_ledger_pipeline import sha256_file, persist_proposals
from offline_review_ledger_io import load_ledger

def proposal(table=1, start=1, end=3):
    return {'table_id':table,'start_observed_seconds':start,'end_observed_seconds':end,
            'sample_count':2,'minimum_confidence':0.7,
            'board_states_observed':['flop','turn'],
            'hand_verified':False,'boundaries_verified':False}

def result(proposals):
    return {'schema_version':1,'analysis_verified':False,
            'hand_boundaries_verified':False,'proposals':proposals}

class LedgerPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)
        self.video=self.dir/'recording.mp4'
        self.video.write_bytes(b'synthetic video placeholder; not decoded media')
        self.dest=self.dir/'ledger.json'

    def run_pipeline(self, proposals=None):
        return persist_proposals(result([proposal()] if proposals is None else proposals),
                                 video_path=self.video,duration_seconds=60,destination=self.dest)

    def test_hash_actual_bytes(self):
        self.assertEqual(sha256_file(self.video),hashlib.sha256(self.video.read_bytes()).hexdigest())

    def test_valid_roundtrip(self):
        info=self.run_pipeline()
        ledger=load_ledger(self.dest)
        self.assertEqual(info['proposal_count'],1)
        self.assertEqual(info['video_sha256'],ledger['video_sha256'])
        self.assertFalse(ledger['entries'][0]['hand_verified'])
        self.assertIsNone(ledger['entries'][0]['ev'])

    def test_empty_proposals(self):
        self.assertEqual(self.run_pipeline([])['proposal_count'],0)

    def test_four_tables(self):
        items=[proposal(t,t,t+1) for t in range(1,5)]
        self.assertEqual(self.run_pipeline(items)['proposal_count'],4)

    def test_duplicate_rejected_without_file(self):
        with self.assertRaises(ValueError): self.run_pipeline([proposal(),proposal()])
        self.assertFalse(self.dest.exists())

    def test_invalid_table_rejected(self):
        with self.assertRaises(ValueError): self.run_pipeline([proposal(table=5)])

    def test_out_of_duration_rejected(self):
        with self.assertRaises(ValueError): self.run_pipeline([proposal(end=70)])

    def test_verified_hand_rejected(self):
        p=proposal();p['hand_verified']=True
        with self.assertRaises(ValueError): self.run_pipeline([p])

    def test_missing_video_rejected(self):
        self.video.unlink()
        with self.assertRaises(FileNotFoundError): self.run_pipeline()

    def test_no_overwrite(self):
        self.run_pipeline()
        old=self.dest.read_bytes()
        with self.assertRaises(FileExistsError): self.run_pipeline()
        self.assertEqual(old,self.dest.read_bytes())

    def test_invalid_chunk(self):
        with self.assertRaises(ValueError): sha256_file(self.video,0)

    def test_sha_changes_with_video(self):
        first=sha256_file(self.video)
        self.video.write_bytes(b'changed')
        self.assertNotEqual(first,sha256_file(self.video))

if __name__=='__main__': unittest.main()
