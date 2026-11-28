import os
import sqlite3
import shutil
import subprocess
import json
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path
from fractions import Fraction
from plo5_strategy_cache import connection, prune, solve_cached
from test_plo5_post_gto_multiway import fixture
from plo5_continuation_bounds import envelopes
from test_plo5_post_gto_river import context,NUT,CATCH,BOARD
import plo5_post_gto_tree as post

class PerformanceTests(unittest.TestCase):
    def test_cache_quota_fifo_and_reuse(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'cache.sqlite';con=connection(p)
            with con:
                for i in range(5):con.execute('INSERT INTO strategy_zlib_v1 VALUES (?,?,?,?,?)',(str(i),b'spec',100,'a'*64,b'x'*100))
                stats=prune(con,max_bytes=1000,max_entries=2)
            self.assertEqual(stats['entries'],2);self.assertEqual(stats['removed'],3)
            self.assertEqual([x[0] for x in con.execute('SELECT cache_key FROM strategy_zlib_v1 ORDER BY rowid')],['3','4'])
            with con:self.assertEqual(prune(con,max_bytes=0)['entries'],0)
            con.close()
            a=solve_cached(p,fixture(3,2),1,rake_on_fold=False);b=solve_cached(p,fixture(3,2),1,rake_on_fold=False)
            self.assertTrue(b['cache_hit']);self.assertEqual(a['result'],b['result'])
    def test_quota_rollback_and_validation(self):
        with tempfile.TemporaryDirectory() as t:
            con=connection(Path(t)/'cache.sqlite')
            with con:con.execute('INSERT INTO strategy_zlib_v1 VALUES (?,?,?,?,?)',('x',b'spec',100,'a'*64,b'x'*100))
            with self.assertRaises(ValueError):
                with con:prune(con,max_entries=0);prune(con,max_bytes=-1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM strategy_zlib_v1').fetchone()[0],1);con.close()
    @unittest.skipUnless(os.environ.get('PLO5_RANK_WORKER_EXE'),'Native worker required')
    def test_batched_native_terminal_budget_exact(self):
        from plo5_rank_worker import RankWorker
        s=post.step(post.start(context([(NUT,1)],[(CATCH,1)],board=BOARD[:4])),'BB','bet',2)
        deal=[((tuple(sorted(NUT)),tuple(sorted(CATCH))),Fraction(1))]
        class Count:
            def __init__(self,w):self.w=w;self.calls=0
            def lookup(self,*a):self.calls+=1;return self.w.lookup(*a)
        with RankWorker(os.environ['PLO5_RANK_WORKER_EXE']) as w:
            for n in (1,4,100):
                a=dict(rake_bps=0,rake_cap=0,rake_on_fold=False,max_nodes=n)
                c=Count(w);ref=envelopes(s,'BTN',deal,[('call',2)],**a);r=envelopes(s,'BTN',deal,[('call',2)],rank_worker=c,**a)
                self.assertEqual(r,ref);self.assertLessEqual(c.calls,1)

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe') and
                     (Path(__file__).resolve().parents[1]/'calibration'/'ppp_bank.json').is_file(),
                     'FFmpeg and validated PPPoker calibration bank required')
class ReanalysisTests(unittest.TestCase):
    def test_no_ocr_and_scope_validation(self):
        from plo5_integrated_video import run
        from plo5_acceptance import audit
        bank=Path(__file__).resolve().parents[1]/'calibration'/'ppp_bank.json'
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);v=p/'v.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(v)],check=True,timeout=30)
            original=p/'original';a=run(v,original,ppp=bank,tables=[1],workers=1,chunk=2,refine_budget=0)
            with patch('plo5_integrated_video.observe_shared') as obs,patch('plo5_integrated_video.scan_session') as scan,patch('plo5_integrated_video.refine') as ref:
                out=p/'again';b=run(v,out,observations_from=original,tables=[1]);obs.assert_not_called();scan.assert_not_called();ref.assert_not_called()
            self.assertTrue(b['observations_reused']);self.assertEqual(a['counts'],b['counts']);self.assertTrue(audit(v,out)['structural_audit_passed']);self.assertIsNone(b['seat_cache']);self.assertFalse(b['beta_ready'])
            for args in ({'tables':[2]},{'tables':[1],'start':0},{'tables':[1],'ppp':bank}):
                with self.assertRaises(ValueError):run(v,p/'bad',observations_from=original,**args)
            f=original/'summary.json';data=json.loads(f.read_text());data['beta_ready']=True;f.write_text(json.dumps(data))
            with self.assertRaises(ValueError):run(v,p/'bad',observations_from=original,tables=[1])
            self.assertFalse((p/'bad').exists())

if __name__=='__main__':unittest.main()
