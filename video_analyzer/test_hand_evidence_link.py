"""Synthetic-only tests: frame proximity is not validation of poker facts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from boundary_history_bridge import build as build_navigation
from boundary_hand_draft import build_template, validate_review
from hand_evidence_link import build, export
from test_boundary_history_bridge import fixture

PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082')


def example(root):
    root = Path(root)
    root.mkdir(exist_ok=True)
    packet, labels = fixture()
    packet['requires_manual_review'] = True
    evidence = root / 'evidence'
    evidence.mkdir()
    for task in packet['tasks']:
        table = task['table_id']
        i = int(task['task_id'][-4:])
        filename = f'table_{table:02d}_seek_{i:04d}.png'
        (evidence / filename).write_bytes(PNG)
        task['frames'][0].update({'filename': filename,
                                  'png_sha256': hashlib.sha256(PNG).hexdigest(),
                                  'decoded_pts_seconds': 1.1 if i == 0 else 3.1})
    packet_path = root / 'packet.json'
    packet_path.write_text(json.dumps(packet))
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    labels['packet_sha256'] = packet_sha
    navigation = build_navigation(packet, labels, packet_sha)
    nav_path = root / 'navigation.json'
    nav_path.write_text(json.dumps(navigation))
    nav_sha = hashlib.sha256(nav_path.read_bytes()).hexdigest()
    edited = build_template(navigation, nav_sha)
    row = edited['entries'][0]
    row['reviewer'] = 'synthetic human'
    row['fields']['variant'] = {'value': 'PLO5', 'confidence': .95,
        'source_pts_seconds': 1.1, 'source_kind': 'manual_video_review', 'human_confirmed': True}
    row['fields']['pot_observed'] = {'value': 10, 'confidence': .5,
        'source_pts_seconds': 2., 'source_kind': 'manual_video_review', 'human_confirmed': True}
    row['fields']['board_visible'] = {'value': ['As', 'Kd', 'Qc'], 'confidence': .3,
        'source_pts_seconds': None, 'source_kind': 'hypothesis', 'human_confirmed': False}
    row['actions'] = [{'timestamp_seconds': 3.05, 'actor': 'hero', 'action': 'call',
        'amount': 2., 'confidence': .8, 'source_kind': 'manual_video_review', 'human_confirmed': True}]
    review = validate_review(navigation, nav_sha, edited)
    review_path = root / 'review.json'
    review_path.write_text(json.dumps(review))
    return navigation, nav_sha, packet, packet_sha, review, evidence, (nav_path, packet_path, review_path)


class EvidenceLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.nav, self.nav_sha, self.packet, self.packet_sha, self.review, self.evidence, self.paths = example(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def run_build(self):
        return build(self.nav, self.nav_sha, self.packet, self.packet_sha, self.review, self.evidence)

    def test_nearby_match_and_no_math(self):
        result = self.run_build()
        self.assertEqual(len(result['entries']), 4)
        row = result['entries'][0]
        self.assertEqual(row['field_links']['variant']['status'], 'nearby_frame_for_human_claim_not_content_verified')
        self.assertEqual(row['field_links']['variant']['candidate_frames'][0]['decoded_pts_seconds'], 1.1)
        self.assertEqual(row['action_links'][0]['candidate_frames'][0]['decoded_pts_seconds'], 3.1)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['cards_or_actions_verified'])

    def test_missing_and_hypothesis_distinguished(self):
        row = self.run_build()['entries'][0]
        self.assertEqual(row['field_links']['pot_observed']['status'], 'no_nearby_byte_matched_frame')
        self.assertEqual(row['field_links']['board_visible']['status'], 'hypothesis_not_evidence')
        self.assertEqual(row['field_links']['hero_cards_visible']['status'], 'unknown')

    def test_no_cross_table_frame_match(self):
        result = self.run_build()
        self.assertTrue(all(f['filename'].startswith('table_01_') for f in result['entries'][0]['field_links']['variant']['candidate_frames']))

    def test_reject_packet_digest_mismatch(self):
        with self.assertRaises(ValueError):
            build(self.nav, self.nav_sha, self.packet, 'a'*64, self.review, self.evidence)

    def test_reject_recording_mismatch(self):
        self.packet['recording_sha256'] = 'f'*64
        with self.assertRaises(ValueError):
            self.run_build()

    def test_reject_png_tamper(self):
        (self.evidence / 'table_01_seek_0000.png').write_bytes(b'bad')
        with self.assertRaises(ValueError):
            self.run_build()

    def test_reject_symlink_png(self):
        img = self.evidence / 'table_01_seek_0000.png'
        img.unlink()
        img.symlink_to(self.evidence / 'table_02_seek_0000.png')
        with self.assertRaises(ValueError):
            self.run_build()

    def test_reject_forged_authority_in_review(self):
        self.review['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            self.run_build()

    def test_reject_cross_table_task(self):
        self.packet['tasks'][0]['table_id'] = 2
        with self.assertRaises(ValueError):
            self.run_build()

    def test_reject_frame_missing_pts(self):
        self.packet['tasks'][0]['frames'][0]['decoded_pts_seconds'] = None
        with self.assertRaises(ValueError):
            self.run_build()

    def test_unmatched_pts_not_used(self):
        self.packet['tasks'][0]['frames'][0]['pts_byte_matched'] = False
        result = self.run_build()
        self.assertEqual(result['entries'][0]['field_links']['variant']['status'], 'no_nearby_byte_matched_frame')

    def test_file_roundtrip_no_overwrite(self):
        output = self.root / 'links.json'
        result = export(*self.paths, self.evidence, output)
        self.assertEqual(json.loads(output.read_text()), result)
        with self.assertRaises(ValueError):
            export(*self.paths, self.evidence, output)

    def test_reject_duplicate_json_keys(self):
        nav = self.paths[0]
        nav.write_text('{"schema_version":2,"schema_version":2}')
        with self.assertRaises(ValueError):
            export(*self.paths, self.evidence, self.root / 'out.json')

    def test_reject_output_inside_evidence(self):
        with self.assertRaises(ValueError):
            export(*self.paths, self.evidence, self.evidence / 'links.json')


if __name__ == '__main__':
    unittest.main()
