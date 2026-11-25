import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import local_ingest
from offline_jobs import OfflineJobStore
from offline_video_ingest_probe import probe, sha256, sample_times
from offline_ingest_audited_pipeline import choose_spotcheck
from video_validator import validate_recording, MAX_DURATION_SECONDS
from plo5_ingest_job import run_job, read_bound_evidence


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires FFmpeg and FFprobe')
class IngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.video = Path(tmp.name) / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=128x128:rate=5:duration=2', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', str(cls.video)], check=True, capture_output=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.database = self.root / 'jobs.db'
        self.results = self.root / 'results'
        self.regions = self.root / 'regions.json'
        self.regions.write_text(json.dumps({'tables': [
            {'table_id': i+1, 'x': (i%2)*64, 'y': (i//2)*64, 'width': 64, 'height': 64}
            for i in range(4)]}))

    def enqueue(self):
        return local_ingest.ingest_local(self.video, self.root / 'uploads', self.database)

    def run_one(self, job):
        return run_job(self.database, job['job_id'], self.regions, self.results, pixel_checks=5)

    def test_real_four_region_job_and_tamper(self):
        first = self.enqueue()
        second = self.enqueue()
        result = self.run_one(second)
        self.assertEqual(result['state'], 'review_required')
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(OfflineJobStore(self.database).get(first['job_id'])['state'], 'queued')
        binding = read_bound_evidence(self.database, second['job_id'])
        self.assertEqual((binding['variant'], binding['crops_pts_hash_audited'], binding['crops_pixel_checked']), (5,12,4))
        self.assertFalse(binding['equity_ev_authorized'])
        self.assertEqual(binding['source_sha256'], sha256(self.video))
        bundle = Path(result['result_path']).parent
        chain = json.loads((bundle/'evidence/chain_report.json').read_text())
        self.assertEqual(chain['pixel_ffmpeg_decode_passes'],1)
        with self.assertRaises(ValueError):
            self.run_one(second)
        crop = next((bundle/'evidence/ingest').glob('*.jpg'))
        crop.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'crop mismatch'):
            read_bound_evidence(self.database,second['job_id'])

    def test_source_hash_mismatch(self):
        job = self.enqueue()
        path = Path(job['source_path'])
        data = path.read_bytes()
        path.write_bytes(bytes([data[0]^1])+data[1:])
        with self.assertRaisesRegex(ValueError,'queued SHA-256'):
            self.run_one(job)
        self.assertEqual(OfflineJobStore(self.database).get(job['job_id'])['state'],'failed')
        self.assertEqual(list(self.results.iterdir()),[])

    def test_invalid_regions_no_output(self):
        job = self.enqueue()
        self.regions.write_text('{"tables":[]}')
        with self.assertRaises(ValueError):
            self.run_one(job)
        self.assertEqual(OfflineJobStore(self.database).get(job['job_id'])['state'],'failed')
        self.assertEqual(list(self.results.iterdir()),[])

    def test_claim_once(self):
        job = self.enqueue()
        store = OfflineJobStore(self.database)
        self.assertEqual(store.claim_job(job['job_id'])['state'],'running')
        self.assertIsNone(store.claim_job(job['job_id']))
        self.assertIsNone(store.claim_job('0'*32))
        self.assertEqual(store.get(job['job_id'])['attempts'],1)

    def test_copy_same_size_change(self):
        def corrupt(src, dst, length):
            data=src.read()
            dst.write(bytes([data[0]^1])+data[1:])
        with patch('local_ingest.shutil.copyfileobj',side_effect=corrupt), self.assertRaisesRegex(ValueError,'changed'):
            self.enqueue()
        self.assertEqual(list((self.root/'uploads').iterdir()),[])

    def test_preexisting_output_preserved(self):
        job=self.enqueue()
        folder=self.results/job['job_id']
        folder.mkdir(parents=True)
        (folder/'keep').write_text('keep')
        with self.assertRaisesRegex(ValueError,'already exists'):
            self.run_one(job)
        self.assertEqual((folder/'keep').read_text(),'keep')
        self.assertEqual(OfflineJobStore(self.database).get(job['job_id'])['state'],'queued')

    def test_report_tamper(self):
        job=self.enqueue()
        self.regions.write_text(json.dumps({'tables':[{'table_id':1,'x':0,'y':0,'width':128,'height':128}]}))
        result=self.run_one(job)
        bundle=Path(result['result_path']).parent
        self.assertEqual(read_bound_evidence(self.database,job['job_id'])['crops_pts_hash_audited'],3)
        (bundle/'evidence/pts_audit.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'report mismatch'):
            read_bound_evidence(self.database,job['job_id'])

    def test_duration_tail_policy(self):
        self.assertEqual(MAX_DURATION_SECONDS,3660)
        for duration, accepted in ((3610.1,True),(3660.,True),(3660.1,False)):
            with self.subTest(duration=duration), patch('video_validator.probe_video',return_value={'duration':duration,'width':128,'height':128}), patch('offline_video_ingest_probe.command',return_value=json.dumps({'format':{'duration':duration},'streams':[{'codec_type':'video','width':128,'height':128,'avg_frame_rate':'20/1'}]})):
                if accepted:
                    self.assertEqual(validate_recording(self.video)['duration_seconds'],duration)
                    self.assertEqual(probe(self.video)['duration_seconds'],duration)
                    self.assertLessEqual(len(sample_times(duration,'20/1',30))*4,512)
                else:
                    with self.assertRaises(ValueError):
                        validate_recording(self.video)
                    with self.assertRaises(ValueError):
                        probe(self.video)


class SpotcheckTests(unittest.TestCase):
    def test_nondivisible_budget_balanced(self):
        samples=[{'table_id':t,'file':f'{t}_{i}'} for t in (1,2,3,4) for i in range(3)]
        checked=choose_spotcheck(samples,[1,2,3,4],7, balanced=True)
        self.assertEqual(len(checked),4)
        self.assertEqual({s['table_id'] for s in checked},{1,2,3,4})

    def test_balanced_cap(self):
        samples=[{'table_id':t,'file':f'{t}_{i}'} for t in (1,2,3) for i in range(3)]
        self.assertEqual(len(choose_spotcheck(samples,[1,2,3],64, balanced=True)),9)


if __name__ == '__main__':
    unittest.main()
