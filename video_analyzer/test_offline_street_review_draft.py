"""Synthetic offline review-draft tests."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_ev_table_crop as media
import offline_street_evidence as street
import offline_street_human_review as human
import offline_street_review_draft as draft

class DraftTests(unittest.TestCase):
    def test_pending_draft_requires_explicit_review(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            video = root / 'sample.mp4'
            subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-f','lavfi',
                            '-i','testsrc2=size=160x120:rate=10','-t','2','-an',
                            '-c:v','mpeg4',str(video)],check=True,timeout=30)
            obs = root / 'observations.json'
            obs.write_text(json.dumps({'schema_version':1,
                'status':'offline_unverified_street_observations',
                'source_video_sha256':media.digest(video),'variant':'PLO5',
                'hands':[{'table_id':'T1','hand_id':'H1','start_seconds':.1,
                'end_seconds':1.8,'events':[{'timestamp_seconds':.4,'street':'preflop',
                'kind':'action','value':'fold','origin':'ocr_proposal','confidence':.4}]}]}))
            led = root / 'ledger'; led.mkdir(); street.export(video,obs,led)
            out = root / 'out'; out.mkdir()
            path = draft.export(video,obs,led,out)
            data = json.loads(path.read_text())
            self.assertEqual(data['hands'][0]['decisions'][0]['decision'],'pending')
            self.assertEqual(data['source_street_report_sha256'],media.digest(led/street.REPORT))
            reviewed = root / 'reviewed'; reviewed.mkdir()
            with self.assertRaises(ValueError): human.export(video,obs,led,path,reviewed)
            data['reviewer_label'] = 'operator_1'
            data['hands'][0]['decisions'][0]['decision'] = 'confirm'
            review = root / 'manual_review.json'; review.write_text(json.dumps(data))
            report = human.export(video,obs,led,review,reviewed)
            self.assertFalse(report['automatic_ocr_math_authorization'])
            with self.assertRaises(ValueError): draft.export(video,obs,led,out)

if __name__ == '__main__': unittest.main()
