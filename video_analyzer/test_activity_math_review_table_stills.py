"""Synthetic four-table crop tests. No recognition or strategy claims."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from activity_hand_review_packet import build_hand_review_packet
from activity_math_readiness_triage import build_math_readiness_triage
from activity_math_review_handoff import build_math_review_handoff
from activity_math_review_frames import export_math_review_frames
from activity_math_review_table_stills import export_math_review_table_stills
from test_activity_consistency_frame_review import changed


class TableStillsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'synthetic_four_tables.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=6:duration=5',
                        '-c:v', 'mpeg4', '-y', str(cls.video)], check=True, capture_output=True)
        sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()
        queue, timeline = changed()
        queue['recording_sha256'] = sha
        timeline['recording_sha256'] = sha
        packet = build_hand_review_packet(queue, timeline)
        triage = build_math_readiness_triage(packet, timeline)
        handoff = build_math_review_handoff(triage, packet, timeline)
        cls.sources = []
        for name, data in [('handoff', handoff), ('triage', triage),
                           ('packet', packet), ('timeline', timeline)]:
            path = cls.root / (name + '.json')
            path.write_text(json.dumps(data), encoding='utf-8')
            cls.sources.append(path)
        cls.frames_dir = cls.root / 'frames'
        export_math_review_frames(cls.video, *cls.sources, cls.frames_dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.test_tmp = tempfile.TemporaryDirectory(dir=self.root)
        self.dir = Path(self.test_tmp.name)
        self.regions = self.dir / 'regions.json'
        self.regions.write_text(json.dumps({'schema_version': 1, 'layout': 'grid',
                                            'rows': 2, 'columns': 2}))

    def tearDown(self):
        self.test_tmp.cleanup()

    def export(self, name='out'):
        return export_math_review_table_stills(
            self.video, self.frames_dir, *self.sources, self.regions, self.dir / name)

    def test_grid_four_tables_shared_full_frame(self):
        report = self.export()
        self.assertEqual(report['counts']['table_crops'], 4)
        self.assertEqual(report['counts']['review_tasks'], 4)
        self.assertEqual(len({x['source_frame_filename'] for x in report['crops']}), 1)
        self.assertEqual({x['table_id'] for x in report['crops']}, {1, 2, 3, 4})
        for row in report['crops']:
            self.assertEqual(row['region']['width'], 80)
            self.assertEqual(row['region']['height'], 60)
            self.assertEqual(hashlib.sha256((self.dir/'out'/row['filename']).read_bytes()).hexdigest(), row['sha256'])
            self.assertIsNone(row['decoded_frame_pts_seconds'])
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        self.assertFalse(report['cards_or_actions_verified'])
        self.assertEqual(json.loads((self.dir/'out'/'math_review_table_stills.json').read_text()), report)
        with self.assertRaises(ValueError):
            self.export()

    def test_manual_regions(self):
        config = {'schema_version': 1, 'layout': 'manual', 'regions': [
            {'table_id': t, 'x': (t - 1) % 2 * 80, 'y': (t - 1) // 2 * 60,
             'width': 80, 'height': 60} for t in (4, 2, 1, 3)]}
        self.regions.write_text(json.dumps(config))
        report = self.export()
        self.assertEqual([r['table_id'] for r in report['regions']], [1, 2, 3, 4])

    def test_reject_invalid_regions_without_output(self):
        bad = [
            {'schema_version': 1, 'layout': 'grid', 'rows': 2, 'columns': 3},
            {'schema_version': 1, 'layout': 'grid', 'rows': True, 'columns': 4},
            {'schema_version': 1, 'layout': 'grid', 'rows': 1, 'columns': 2},
            {'schema_version': 1, 'layout': 'manual', 'regions': [
                {'table_id': i, 'x': 0, 'y': 0, 'width': 100, 'height': 100} for i in range(1, 5)]},
            {'schema_version': 1, 'layout': 'manual', 'regions': [
                {'table_id': i, 'x': 0, 'y': 0, 'width': True, 'height': 10} for i in range(1, 5)]},
        ]
        for i, config in enumerate(bad):
            with self.subTest(i=i):
                self.regions.write_text(json.dumps(config))
                with self.assertRaises(ValueError):
                    self.export(f'out_{i}')
                self.assertFalse((self.dir / f'out_{i}').exists())

    def test_reject_manifest_tamper_and_source_frame_tamper(self):
        manifest = json.loads((self.frames_dir/'math_review_frames.json').read_text())
        alt = self.dir/'altered_frames'
        alt.mkdir()
        (alt/'frame_0000.png').write_bytes((self.frames_dir/'frame_0000.png').read_bytes())
        manifest['frames'][0]['requested_seek_pts_seconds'] += .1
        (alt/'math_review_frames.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            export_math_review_table_stills(self.video, alt, *self.sources,
                                            self.regions, self.dir/'out1')
        manifest['frames'][0]['requested_seek_pts_seconds'] -= .1
        (alt/'math_review_frames.json').write_text(json.dumps(manifest))
        with (alt/'frame_0000.png').open('ab') as stream:
            stream.write(b'tamper')
        with self.assertRaises(ValueError):
            export_math_review_table_stills(self.video, alt, *self.sources,
                                            self.regions, self.dir/'out2')

    def test_reject_symlink_frames_and_changed_video(self):
        link = self.dir/'linked'
        link.symlink_to(self.frames_dir, target_is_directory=True)
        with self.assertRaises(ValueError):
            export_math_review_table_stills(self.video, link, *self.sources,
                                            self.regions, self.dir/'out1')
        fake = self.dir/'other.mp4'
        fake.write_bytes(self.video.read_bytes() + b'change')
        with self.assertRaises(ValueError):
            export_math_review_table_stills(fake, self.frames_dir, *self.sources,
                                            self.regions, self.dir/'out2')

    def test_cli(self):
        command = [sys.executable, str(Path(__file__).with_name('activity_math_review_table_stills.py')),
                   str(self.video), str(self.frames_dir), *map(str, self.sources),
                   str(self.regions), str(self.dir/'cli')]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['table_crops'], 4)


if __name__ == '__main__':
    unittest.main()
