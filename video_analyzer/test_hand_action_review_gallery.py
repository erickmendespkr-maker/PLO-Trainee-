"""Synthetic offline integration tests; never assert poker decisions from images."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from boundary_hand_draft import build_template, validate_review
from hand_action_pts_evidence import export as export_stills
from hand_action_review_gallery import export as export_gallery
from test_hand_evidence_link import example


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class GalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_video = tempfile.TemporaryDirectory()
        cls.video = Path(cls.temp_video.name) / 'recording.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=5:duration=4',
                        '-c:v', 'mpeg4', '-y', str(cls.video)],
                       capture_output=True, check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temp_video.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        nav, _, _, _, _, _, _ = example(self.root)
        nav['recording_sha256'] = sha(self.video)
        self.nav_path = self.root / 'navigation.json'
        self.nav_path.write_text(json.dumps(nav))
        edited = build_template(nav, sha(self.nav_path))
        for entry in edited['entries']:
            entry['reviewer'] = 'synthetic reviewer'
            entry['fields']['variant'] = {'value': 'PLO5', 'confidence': 0.9,
                'source_pts_seconds': 1.1, 'source_kind': 'manual_video_review',
                'human_confirmed': True}
            entry['fields']['board_visible'] = {'value': ['As', 'Kd', 'Qc'],
                'confidence': 0.3, 'source_pts_seconds': None,
                'source_kind': 'hypothesis', 'human_confirmed': False}
            entry['actions'] = [{'timestamp_seconds': 2.0, 'actor': 'hero',
                'action': 'call', 'amount': 2, 'confidence': 0.7,
                'source_kind': 'manual_video_review', 'human_confirmed': True}]
        self.review_path = self.root / 'review.json'
        self.review_path.write_text(json.dumps(validate_review(nav, sha(self.nav_path), edited)))
        self.regions = self.root / 'regions.json'
        self.regions.write_text(json.dumps({str(i): {
            'x': ((i-1) % 2) * 160, 'y': ((i-1) // 2) * 120,
            'width': 160, 'height': 120} for i in range(1, 5)}))
        self.stills = self.root / 'stills'
        self.gallery = self.root / 'gallery'
        export_stills(self.video, self.nav_path, self.review_path, self.stills,
                      regions_json=self.regions)

    def generate(self, **kwargs):
        return export_gallery(self.video, self.nav_path, self.review_path,
                              self.stills, self.gallery, regions_json=self.regions, **kwargs)

    def manifest(self):
        return json.loads((self.stills / 'action_pts_evidence.json').read_text())

    def overwrite_manifest(self, manifest):
        (self.stills / 'action_pts_evidence.json').write_text(json.dumps(manifest))

    def test_four_tables_gallery_and_html(self):
        report = self.generate()
        self.assertEqual(report['counts']['entries'], 4)
        self.assertEqual(report['counts']['nearby_audited_links'], 8)
        self.assertEqual(report['counts']['frames_hashed'], 8)
        self.assertEqual(report['counts']['annotations'], 24)  # five fields plus one action per entry
        self.assertEqual({r['table_id'] for r in report['entries']}, {1, 2, 3, 4})
        self.assertEqual(json.loads((self.gallery / 'review_gallery.json').read_text()), report)
        html = (self.gallery / 'review_gallery.html').read_text()
        self.assertIn('action_table_01_', html)
        self.assertIn('Quadros auditados não confirmam cartas', html)
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        self.assertFalse(report['cards_or_actions_verified'])

    def test_hypothesis_unknown_and_human_claim(self):
        row = self.generate()['entries'][0]['links']
        self.assertEqual(row[0]['status'], 'nearby_audited_frame_not_content_verified')
        self.assertEqual(row[1]['status'], 'unknown')
        self.assertEqual(row[2]['status'], 'hypothesis_not_evidence')
        self.assertIsNone(row[2]['frame'])
        self.assertTrue(row[-1]['frame']['filename'].startswith('action_table_01_'))

    def test_no_overwrite(self):
        self.generate()
        with self.assertRaises(ValueError):
            self.generate()

    def test_png_tamper_rejected(self):
        name = self.manifest()['frames'][0]['filename']
        (self.stills / name).write_bytes(b'bad')
        with self.assertRaises(ValueError):
            self.generate()
        self.assertFalse(self.gallery.exists())

    def test_png_symlink_rejected(self):
        a, b = [r['filename'] for r in self.manifest()['frames'][:2]]
        (self.stills / a).unlink()
        (self.stills / a).symlink_to(self.stills / b)
        with self.assertRaises(ValueError):
            self.generate()

    def test_report_sha_tamper_rejected(self):
        report = self.manifest()
        report['frames'][0]['png_sha256'] = '0' * 64
        self.overwrite_manifest(report)
        with self.assertRaises(ValueError):
            self.generate()

    def test_report_forged_nearby_flag_rejected(self):
        report = self.manifest()
        report['frames'][0]['within_requested_pts_tolerance'] = False
        self.overwrite_manifest(report)
        with self.assertRaisesRegex(ValueError, 'status'):
            self.generate()

    def test_report_forged_pts_rejected(self):
        report = self.manifest()
        report['frames'][0]['decoded_pts_seconds'] += 1
        self.overwrite_manifest(report)
        with self.assertRaisesRegex(ValueError, 'PTS'):
            self.generate()

    def test_report_forged_association_rejected(self):
        report = self.manifest()
        report['associations'][0]['frame_id'] = 999
        self.overwrite_manifest(report)
        with self.assertRaisesRegex(ValueError, 'source'):
            self.generate()

    def test_report_forged_authority_rejected(self):
        report = self.manifest()
        report['ready_for_equity_or_ev'] = True
        self.overwrite_manifest(report)
        with self.assertRaises(ValueError):
            self.generate()

    def test_review_tamper_rejected(self):
        review = json.loads(self.review_path.read_text())
        review['entries'][0]['hand_reconstruction_verified'] = True
        self.review_path.write_text(json.dumps(review))
        with self.assertRaises(ValueError):
            self.generate()

    def test_regions_mismatch_rejected(self):
        regions = json.loads(self.regions.read_text())
        regions['1']['x'] = 10
        self.regions.write_text(json.dumps(regions))
        with self.assertRaises(ValueError):
            self.generate()

    def test_no_regions_multitable_rejected(self):
        with self.assertRaises(ValueError):
            export_gallery(self.video, self.nav_path, self.review_path,
                           self.stills, self.gallery)

    def test_output_inside_evidence_rejected(self):
        with self.assertRaises(ValueError):
            export_gallery(self.video, self.nav_path, self.review_path,
                           self.stills, self.stills / 'subfolder', regions_json=self.regions)

    def test_unmatched_frame_does_not_become_visual_evidence(self):
        report = self.manifest()
        row = report['frames'][0]
        row['pts_byte_matched'] = False
        row['decoded_pts_seconds'] = None
        row['decoded_pts_ticks'] = None
        row['decoded_pts_time_base'] = None
        row['requested_to_decoded_delta_seconds'] = None
        row['within_requested_pts_tolerance'] = False
        row['status'] = 'no_usable_nearby_audited_frame'
        report['counts']['pts_byte_matched'] -= 1
        report['counts']['near_requested_pts'] -= 1
        self.overwrite_manifest(report)
        result = self.generate()
        link = result['entries'][0]['links'][0]
        self.assertEqual(link['status'], 'no_usable_nearby_audited_frame')
        self.assertIsNone(link['frame'])
        self.assertEqual(result['counts']['nearby_audited_links'], 7)

    def test_budget_skipped_is_explicit(self):
        import shutil
        shutil.rmtree(self.stills)
        export_stills(self.video, self.nav_path, self.review_path, self.stills,
                      regions_json=self.regions, max_frames=1)
        result = self.generate()
        self.assertEqual(result['counts']['nearby_audited_links'], 1)
        self.assertEqual(result['counts']['frames_hashed'], 1)
        self.assertEqual(sum(l['status'] == 'frame_budget_exceeded'
                             for e in result['entries'] for l in e['links']), 7)

    def test_html_escapes_untrusted_text(self):
        # Change a human annotation, then regenerate corresponding stills and gallery.
        review = json.loads(self.review_path.read_text())
        review['entries'][0]['actions'][0]['actor'] = '<img src=x onerror=alert(1)>'
        self.review_path.write_text(json.dumps(review))
        import shutil
        shutil.rmtree(self.stills)
        export_stills(self.video, self.nav_path, self.review_path, self.stills,
                      regions_json=self.regions)
        self.generate()
        page = (self.gallery / 'review_gallery.html').read_text()
        self.assertNotIn('<img src=x onerror=alert(1)>', page)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', page)


if __name__ == '__main__':
    unittest.main()
