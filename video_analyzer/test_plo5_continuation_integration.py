"""End-to-end candidate path with explicit synthetic priors, never certified prints."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_integrated_video import run
from plo5_acceptance import audit
from plo5_continuation_bounds import digest
from test_plo5_continuity import full_hand, manifest, collect
from test_plo5_snapshot_replay import V

BANK=Path(__file__).resolve().parents[1]/'calibration'/'ppp_bank.json'

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe') and BANK.exists(),'FFmpeg and bank required')
class ContinuationIntegrationTests(unittest.TestCase):
    def test_prior_from_recovered_prefix_and_report_stays_pending(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);v=p/'v.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(v)],check=True,timeout=30)
            rows=full_hand()[:4];hands,records,_,_=collect([rows]);hand=hands[0];sd=hand['seed'];j=int(records[0]['decision_id']);ident=sd['hand_id'];self.assertEqual(j,0)
            cfg=dict(prefix_sha256=digest(dict(seed=sd,events=hand['events'][:j])),hypotheses=[dict(id='synthetic',provenance=dict(description='Test only',source_sha256=digest('test only')),deals=[dict(holdings={'SB':sd['holding'],'BB':V},weight=1,likelihoods=[])])],rake_bps=0,rake_cap=0,rake_on_fold=False)
            def observe(source,coarse,refined,tables,money,card,seat,dealt,**kw):
                return dict(variant=5,source_sha256=coarse['source_sha256'],actions_verified=False,strategy_authorized=False,frames=[dict(rows[int(f['pts'])],rgb_sha256=f['rgb_sha256'],file=f['file']) for f in coarse['frames']])
            # Keep test fast with a tiny model budget, while calling the actual review.
            from plo5_continuation_bounds import review
            def bounded(*args,**kw):return review(*args,max_nodes=8,**kw)
            out=p/'report'
            with patch('plo5_integrated_video.observe_shared',side_effect=observe),patch('plo5_integrated_video.continuation_review',side_effect=bounded):
                r=run(v,out,ppp=BANK,tables=[1],chunk=2,workers=1,refine_budget=0,configs={'terminal':{},'cfr':{},'bounds':{ident:{str(j):cfg}}})
            self.assertEqual(r['counts']['candidate_decisions'],1);self.assertEqual(r['counts']['selected_pending'],1);self.assertEqual(r['counts']['errors'],0);self.assertEqual(r['counts']['prints'],0)
            data=json.loads((out/'window_00002/candidates.json').read_text());m=data['continuation_models'][0]['model'];self.assertEqual(m['status'],'CONDITIONAL_CONTINUATION_ENVELOPE');self.assertFalse(m['strategy_verified']);self.assertEqual(m['prefix_sha256'],cfg['prefix_sha256']);self.assertTrue(audit(v,out)['structural_audit_passed'])

if __name__=='__main__':unittest.main()
