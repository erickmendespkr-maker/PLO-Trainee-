"""Synthetic file-identity and ROI-contract tests (no poker inference)."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if (HERE / "baseline").is_dir():
    sys.path.insert(0, str(HERE / "baseline"))
import offline_visual_review_contract as contract
import offline_four_table_visual_timeline as core


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.video = self.base / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', 'color=c=black:s=320x192:r=1:d=2',
            '-f', 'lavfi', '-i', 'color=c=white:s=320x192:r=1:d=4',
            '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0',
            '-c:v', 'mpeg4', '-q:v', '3', str(self.video)],
            check=True, timeout=30)
        self.rois = {'schema_version': 1, 'tables': [
            {'table_id': f'table_{i+1}', 'normalized_rect': r}
            for i, r in enumerate(([0,0,.5,.5],[.5,0,.5,.5],
                                    [0,.5,.5,.5],[.5,.5,.5,.5]))]}
        import offline_manual_roi_review as review
        self.timeline = review.custom_timeline(self.video, self.rois)
        self.assertTrue(self.timeline['tables'][0]['candidate_windows'])
        self.decisions = {'schema_version': 1, 'video_sha256': self.timeline['video_sha256'],
                          'reviews': [{'table_id': 'table_1', 'candidate_index': 0,
                                       'decision': 'confirmed_hand', 'hand_id': 'H001',
                                       'start_seconds': 1.2, 'end_seconds': 3.4}]}
        self.paths = [self.base / n for n in ('rois.json', 'timeline.json', 'decisions.json')]
        self.write()

    def write(self):
        for p, value in zip(self.paths, (self.rois, self.timeline, self.decisions)):
            p.write_text(json.dumps(value), encoding='utf-8')
        self.timeline['roi_config_sha256'] = core.sha256_file(self.paths[0])
        self.paths[1].write_text(json.dumps(self.timeline), encoding='utf-8')

    def run_contract(self):
        return contract.validate_bundle(self.video, *self.paths)

    def test_valid_review(self):
        result = self.run_contract()
        self.assertEqual('H001', result['clips'][0]['hand_id'])
        self.assertEqual(core.sha256_file(self.paths[0]), result['source_roi_config_sha256'])

    def test_reject_modified_roi(self):
        self.write()
        self.rois['tables'][0]['normalized_rect'] = [0, 0, .45, .5]
        self.paths[0].write_text(json.dumps(self.rois))
        with self.assertRaises(core.TimelineError): self.run_contract()

    def test_reject_table_order(self):
        self.timeline['tables'].reverse(); self.write()
        with self.assertRaises(core.TimelineError): self.run_contract()

    def test_reject_review_video_hash(self):
        self.decisions['video_sha256'] = '0' * 64; self.write()
        with self.assertRaises(core.TimelineError): self.run_contract()

    def test_reject_duplicate_review(self):
        self.decisions['reviews'].append(copy.deepcopy(self.decisions['reviews'][0])); self.write()
        with self.assertRaises(core.TimelineError): self.run_contract()

    def test_reject_outside_video(self):
        self.decisions['reviews'][0]['end_seconds'] = 100; self.write()
        with self.assertRaises(core.TimelineError): self.run_contract()

    def test_no_overwrite(self):
        self.write()
        output = self.base / 'plan.json'
        self.assertEqual(0, contract.main([str(self.video), *(str(p) for p in self.paths), str(output)]))
        with self.assertRaises(core.TimelineError):
            contract.main([str(self.video), *(str(p) for p in self.paths), str(output)])


if __name__ == '__main__': unittest.main()
