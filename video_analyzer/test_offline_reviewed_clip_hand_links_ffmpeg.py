"""Actual FFmpeg/FFprobe integration using synthetic non-poker video, four crops."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_reviewed_clip_hand_links as links


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')
    return path


class RealMp4Integration(unittest.TestCase):
    def test_four_ffmpeg_crops_and_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            video = root / 'synthetic.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                            '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=10',
                            '-t', '4', '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                            '-pix_fmt', 'yuv420p', str(video)],
                           check=True, capture_output=True, timeout=30)
            video_sha = links.sha(video)
            folder = root / 'batch'
            folder.mkdir()
            hands, requests, entries = [], [], []
            for table in range(1, 5):
                hid = f'hand{table}'
                crop = {'x': (table-1) % 2 * 320, 'y': (table-1) // 2 * 180,
                        'width': 320, 'height': 180}
                hands.append({'hand_id': hid, 'table_id': table, 'declared_game_type': 'PLO5',
                              'start_pts_seconds': 1.25, 'end_pts_seconds': 2.75,
                              'boundaries_human_declared_and_visually_checked': True,
                              'complete_hand_reconstructed': False,
                              'ready_for_equity_or_ev': False, 'observations': []})
                req = {'schema_version': 1, 'hand_id': hid, 'table_id': table,
                       'start_seconds': 1.0, 'end_seconds': 3.0, 'crop': crop,
                       'explanation': 'Synthetic visual test only',
                       'source_video_sha256': video_sha,
                       'reviewer_confirmed_offline': True}
                requests.append(req)
                filename = f'{table:02d}_table{table}_{hid}.mp4'
                clip = folder / filename
                subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                                '-ss', '1', '-i', str(video), '-t', '2', '-map', '0:v:0',
                                '-an', '-vf', f'crop=320:180:{crop["x"]}:{crop["y"]}',
                                '-c:v', 'libx264', '-preset', 'ultrafast',
                                '-pix_fmt', 'yuv420p', str(clip)],
                               check=True, capture_output=True, timeout=30)
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                        'stream=width,height:format=duration', '-of', 'json',
                                        str(clip)], capture_output=True, text=True,
                                       check=True, timeout=30)
                info = json.loads(probe.stdout)
                self.assertEqual((info['streams'][0]['width'], info['streams'][0]['height']),
                                 (320, 180))
                self.assertAlmostEqual(float(info['format']['duration']), 2.0, delta=0.15)
                request = dump(folder / f'{table:02d}_request.json', req)
                meta = {'analysis_status': 'manually_selected_offline_clip',
                        'hand_id': hid, 'table_id': table,
                        'source_video_sha256': video_sha,
                        'source_request_sha256': links.sha(request),
                        'clip_sha256': links.sha(clip), 'start_seconds': 1.0,
                        'end_seconds': 3.0, 'crop': crop,
                        'explanation': req['explanation'],
                        'video_evidence_verified': False,
                        'automatic_clip_selection_authorized': False}
                dump(folder / (filename + '.json'), meta)
                entries.append({'hand_id': hid, 'table_id': table, 'clip_file': filename,
                                'sidecar_file': filename + '.json',
                                'request_file': request.name, 'clip_sha256': links.sha(clip),
                                'request_sha256': links.sha(request),
                                'start_seconds': 1.0, 'end_seconds': 3.0})
            hand_file = dump(root / 'hands.json', {
                'schema_version': 1,
                'analysis_status': 'human_declared_incomplete_hand_candidates',
                'recording_sha256': video_sha, 'complete_hand_reconstructed': False,
                'automatic_clip_selection_authorized': False, 'hands': hands})
            manifest = dump(root / 'manifest.json', {
                'schema_version': 1, 'source_video_sha256': video_sha,
                'reviewer_confirmed_offline': True,
                'reviewer_note': 'Synthetic four-table test', 'clips': requests})
            dump(folder / 'batch_report.json', {
                'schema_version': 1,
                'analysis_status': 'manually_selected_offline_clip_batch_only',
                'source_video_sha256': video_sha,
                'source_manifest_sha256': links.sha(manifest),
                'automatic_clip_selection_authorized': False,
                'video_evidence_verified': False,
                'clip_count': 4, 'clips': entries})
            output = root / 'linked.json'
            result = links.link(video, hand_file, manifest, folder, output)
            self.assertEqual(result['clip_count'], 4)
            self.assertEqual(len(result['linked_clips']), 4)
            self.assertFalse(result['ev_verified'])
            self.assertTrue(output.is_file())
            (folder / entries[0]['clip_file']).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                links.link(video, hand_file, manifest, folder, root / 'blocked.json')
            self.assertFalse((root / 'blocked.json').exists())


if __name__ == '__main__':
    unittest.main()
