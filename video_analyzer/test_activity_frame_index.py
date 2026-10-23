"""Pure synthetic tests for decoded-PTS frame indexing and rejection paths."""
import copy
import unittest
from activity_frame_index import index_activity_frames


def fixture():
    frame = {'table_id': 1, 'image': 'table_01/frame_00000.png',
             'source_pts_ticks': 3, 'timestamp_seconds': .75,
             'requested_seek_seconds': .51, 'seek_reason': 'baseline_grid',
             'status': 'unverified_visual_evidence', 'sha256': 'a'*64}
    return {'schema_version': 1, 'analysis_status': 'unverified_activity_pts_evidence_only',
            'timestamp_semantics': 'decoded_filtergraph_pts_not_capture_time',
            'requires_manual_review': True, 'source_time_base': '1/4',
            'requested_count': 2,
            'frames': [frame, {**frame, 'requested_seek_seconds': .52}],
            'unresolved': []}


class FrameIndexTests(unittest.TestCase):
    def test_group_identical_decoded_frames(self):
        rows = index_activity_frames(fixture())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['requested_seeks'], [.51, .52])
        self.assertEqual(rows[0]['timestamp'], .75)
        self.assertEqual(rows[0]['source_sha256'], 'a'*64)

    def test_unresolved_kept_out_of_frame_index(self):
        manifest = fixture()
        manifest['unresolved'].append({'table_id': 1, 'requested_seek_seconds': 3.,
                                       'reason': 'no_decoded_frame_within_seek_drift'})
        manifest['requested_count'] += 1
        self.assertEqual(len(index_activity_frames(manifest)), 1)

    def test_reject_conflicting_shared_image(self):
        for change in (
            {'source_pts_ticks': 4}, {'sha256': 'b'*64},
            {'timestamp_seconds': 1.}, {'image': '../bad.png'},
            {'status': 'verified_poker_action'}, {'table_id': True},
            {'seek_reason': 'confirmed_fold'}, {'requested_seek_seconds': .51},
            {'source_pts_ticks': True}, {'requested_seek_seconds': float('nan')},
        ):
            with self.subTest(change=change):
                raw = fixture()
                raw['frames'][1].update(change)
                with self.assertRaises(ValueError):
                    index_activity_frames(raw)

    def test_reject_invalid_metadata(self):
        for change in (
            {'schema_version': 2}, {'requires_manual_review': False},
            {'source_time_base': '0'}, {'source_time_base': 'not_fraction'},
            {'requested_count': 4}, {'frames': 'bad'},
            {'unresolved': [{'table_id': 1, 'requested_seek_seconds': .51,
                             'reason': 'no_decoded_frame_within_seek_drift'}], 'requested_count': 3},
        ):
            with self.subTest(change=change):
                raw = fixture()
                raw.update(change)
                with self.assertRaises(ValueError):
                    index_activity_frames(raw)

    def test_cross_table_separation_and_order(self):
        raw = fixture()
        third = {**raw['frames'][0], 'table_id': 2,
                 'image': 'table_02/frame_00000.png', 'requested_seek_seconds': .51}
        raw['frames'].insert(0, third)
        raw['requested_count'] += 1
        rows = index_activity_frames(raw)
        self.assertEqual([r['table_id'] for r in rows], [1, 2])
        self.assertEqual([len(r['requested_seeks']) for r in rows], [2, 1])


if __name__ == '__main__':
    unittest.main()
