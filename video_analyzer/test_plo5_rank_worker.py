import os
import random
import subprocess
import tempfile
import unittest
from pathlib import Path
from plo5_rank_worker import RankWorker
from plo5_rank_service import lookup_states
from plo5_index_native import unrank_batch,SIZES
from plo5_review_session import review_batch
from test_plo5_post_gto_river import polar,CATCH,NUT,BOARD

EXE=os.environ.get('PLO5_RANK_WORKER_EXE');INDEX=os.environ.get('PLO5_INDEX_EXE');RANK=os.environ.get('PLO5_RANK_EXE')

@unittest.skipUnless(EXE and INDEX and RANK,'native binaries absent')
class RankWorkerTests(unittest.TestCase):
    def test_parity_across_requests(self):
        rng=random.Random(27112026)
        with RankWorker(EXE) as w:
            pid=w.process.pid
            for s in (3,4,5,3,5):
                states=unrank_batch(INDEX,s,[0,SIZES[s]-1]+[rng.randrange(SIZES[s]) for _ in range(50)])
                states+=states[:1]
                self.assertEqual(w.lookup(s,states),lookup_states(INDEX,None,s,states,rank_executable=RANK))
                self.assertEqual(w.process.pid,pid)
            self.assertEqual(w.lookup(3,[]),[])
        self.assertIsNotNone(w.process.poll())
        with self.assertRaises(ValueError):w.lookup(3,[])
    def test_invalid_and_dead_worker(self):
        with RankWorker(EXE) as w:
            for h,b in ((NUT,[NUT[0],'2c','3d']),(NUT,BOARD[:2])):
                with self.assertRaises(ValueError):w.lookup(3,[(h,b)])
            self.assertEqual(len(w.lookup(3,[(NUT,BOARD[:3])])),1)
            w.process.kill();w.process.wait()
            with self.assertRaises((ValueError,OSError)):w.lookup(3,[(NUT,BOARD[:3])])
            self.assertTrue(w.closed)
        for payload in ('2 1\n','5 4097\n','3 1\n0 1 2 3 4 4 5 6\n'):
            self.assertNotEqual(subprocess.run([EXE],input=payload,text=True,capture_output=True,timeout=10).returncode,0)
    def test_timeout_closes_process(self):
        from concurrent.futures import TimeoutError
        with RankWorker(EXE,timeout=.000001) as w:
            with self.assertRaises(TimeoutError):w.lookup(5,[(NUT,BOARD)])
            self.assertTrue(w.closed);self.assertIsNotNone(w.process.poll())
    def test_review_batch(self):
        m=dict(id='A',context=polar(),history=[['BB','bet',2]],holding=CATCH,action=['call',2],rake_on_fold=False,iterations=10)
        with tempfile.TemporaryDirectory() as t,RankWorker(EXE) as w:
            cache=Path(t)/'cache.db';models=[m,dict(m,id='B')]
            review_batch(cache,models)
            a=review_batch(cache,models,rank_executables=(INDEX,RANK));b=review_batch(cache,models,rank_worker=w)
            self.assertEqual(a,b)
            with self.assertRaises(ValueError):review_batch(cache,models,rank_worker=w,rank_executables=(INDEX,RANK))

if __name__=='__main__':unittest.main()
