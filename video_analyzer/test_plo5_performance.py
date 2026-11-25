"""Exact rank equivalence and lossless export optimization regression tests."""
from collections import Counter
from itertools import combinations_with_replacement
import random
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_omaha_showdown import _five, RANKS, SUITS
from plo5_rank_cache import fast_five, clear_cache, cache_info
from test_plo5_evaluator import oracle_five
from plo5_evaluator import evaluate
from plo5_postflop_draws import draws
from plo5_equity import equity
from test_plo5_action_ev import scenario
from plo5_session_export import render, frame_hashes
from offline_ingest_pts_audit import decoded_pts


class PerformanceTests(unittest.TestCase):
    def test_all_7462_rank_signatures(self):
        clear_cache();count=0
        for ranks in combinations_with_replacement(RANKS,5):
            if max(Counter(ranks).values())>4:continue
            cards=tuple(r+s for r,s in zip(ranks,'cdhsc'))
            self.assertEqual(fast_five(cards),oracle_five(cards));count+=1
            if len(set(ranks))==5:
                cards=tuple(r+'s' for r in ranks)
                self.assertEqual(fast_five(cards),oracle_five(cards));count+=1
        self.assertEqual(count,7462);self.assertEqual(cache_info().currsize,7462)
        self.assertEqual(cache_info().maxsize,7462)

    def test_random_physical_hands_and_order(self):
        rng=random.Random(35);deck=[r+s for r in RANKS for s in SUITS]
        for _ in range(10000):
            h=rng.sample(deck,5);self.assertEqual(fast_five(h),_five(h));self.assertEqual(fast_five(h[::-1]),_five(h))
        self.assertLessEqual(cache_info().currsize,7462)

    def test_cache_hits_and_clear(self):
        clear_cache();h=['As','Ad','Ks','7h','2c'];a=fast_five(h);b=fast_five(['Ah','Ac','Kd','7s','2h'])
        self.assertEqual(a,b);self.assertEqual(cache_info().misses,1);self.assertEqual(cache_info().hits,1)
        clear_cache();self.assertEqual(cache_info().currsize,0);self.assertEqual(fast_five(h),a)

    def test_end_to_end_reference_equivalence(self):
        import plo5_evaluator as e, plo5_board_texture as b, plo5_postflop_draws as d
        h=['As','Ks','Qh','Jh','Tc'];board=['9s','8s','2d'];s=scenario()
        def compute():return [evaluate(h,board),draws(h,board),equity(s['hero'],[],s['range'],trials=100,seed=35)]
        with patch.object(e,'_five',_five),patch.object(b,'_five',_five),patch.object(d,'_five',_five):reference=compute()
        self.assertEqual(compute(),reference)

    def test_export_presets_and_full_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=256x128:r=10:d=3','-c:v','libx264','-threads','1',str(source)],check=True)
            pts=decoded_pts(source);p={'region':{'width':128,'height':128,'x':0,'y':0},'start_frame':2,'end_frame_inclusive':12}
            a=root/'a.mp4';b=root/'b.mp4';ra=render(source,a,p,pts);rb=render(source,b,p,pts,preset='superfast')
            self.assertEqual((ra['frames'],rb['frames']),(11,11));self.assertEqual(decoded_pts(a),decoded_pts(b));self.assertEqual(frame_hashes(a),frame_hashes(b))
            self.assertTrue(ra['decoded_yuv420p_pixels_match']);self.assertTrue(rb['decoded_yuv420p_pixels_match'])
            self.assertEqual((ra['encoding_preset'],rb['encoding_preset']),('ultrafast','superfast'))
            with self.assertRaises(ValueError):render(source,root/'bad.mp4',p,pts,preset='medium')
            with self.assertRaises(ValueError):frame_hashes(source,max_frames=0)


if __name__=='__main__':unittest.main()
