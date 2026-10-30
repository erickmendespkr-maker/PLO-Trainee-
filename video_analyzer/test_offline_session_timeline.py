"""Synthetic tests for the offline four-table timeline; no real hand claims."""
import copy
from pathlib import Path
import shutil
import unittest

import offline_session_timeline as timeline
import test_offline_reviewed_math_clip_gallery as gallery_tests


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.fx = gallery_tests.MathClipGalleryTests(methodName='test_two_table_mixed_math_and_blocked')
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fx.generate()

    def build(self):
        return timeline.prepare(timeline.bridge.assemble(
            self.fx.plan_path, self.fx.ann_path, self.fx.queue_path, self.fx.workspace))

    def create(self):
        return timeline.process(self.fx.plan_path, self.fx.ann_path,
                                self.fx.queue_path, self.fx.workspace)

    def verify(self):
        return timeline.process(self.fx.plan_path, self.fx.ann_path,
                                self.fx.queue_path, self.fx.workspace, verify=True)

    def test_real_verified_two_table_fixture(self):
        result = self.create()
        self.assertEqual((result['tables'], result['clips']), (2, 2))
        self.assertFalse(result['recognition_verified'])
        self.assertFalse(result['action_graded'])
        self.assertTrue(self.verify()['verified'])

    def test_timeline_html_links_to_mp4_and_dashboard(self):
        self.create()
        html = (self.fx.workspace / 'timeline.html').read_text()
        self.assertIn('clips/H001.mp4', html)
        self.assertIn('href="index.html"', html)
        self.assertIn('href="#table-T1"', html)
        self.assertIn('IC 95% amostral', html)
        self.assertIn('Sem cálculo', html)
        self.assertIn('preload="none"', html)

    def test_repeated_build_is_byte_identical(self):
        self.create()
        original = (self.fx.workspace / 'timeline.html').read_bytes()
        self.assertEqual(original, timeline.render(self.build()).encode('utf-8'))

    def test_no_overwrite(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.create()

    def test_tampered_timeline_is_rejected(self):
        self.create()
        p = self.fx.workspace / 'timeline.html'
        p.write_text(p.read_text() + '<!--changed-->')
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.verify()

    def test_symlink_output_is_rejected(self):
        dest = self.fx.workspace / 'timeline.html'
        try:
            dest.symlink_to(self.fx.workspace / 'index.html')
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.create()

    def test_tampered_dashboard_is_rejected(self):
        p = self.fx.workspace / 'index.html'
        p.write_text(p.read_text() + '<!-- changed -->')
        with self.assertRaisesRegex(ValueError, 'dashboard differs'):
            self.create()

    def test_missing_dashboard_is_rejected(self):
        (self.fx.workspace / 'index.html').unlink()
        with self.assertRaisesRegex(ValueError, 'dashboard'):
            self.create()

    def test_changed_source_clip_is_rejected(self):
        (self.fx.clips / 'H001.mp4').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'MP4 hash mismatch'):
            self.create()

    def test_changed_math_result_is_rejected(self):
        (self.fx.math / 'hands/H001.json').write_text('not json')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.create()

    def test_xss_in_human_explanation_is_escaped(self):
        p = self.fx.clips / 'H001.mp4.json'
        obj = timeline.bridge.q.read(p)
        obj['explanation'] = '<img src=x onerror=alert(1)> & teste'
        from test_offline_reviewed_math_clip_gallery import dump
        dump(p, obj)
        (self.fx.workspace / 'index.html').unlink()
        self.fx.generate()
        self.create()
        html = (self.fx.workspace / 'timeline.html').read_text()
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;img src=x', html)
        self.assertIn('&amp; teste', html)

    def test_four_tables_end_to_end_with_blocked_hands(self):
        for n, table, start, end in [(3, 'T3', 20, 26), (4, 'T4', 40, 50)]:
            self.fx.plan['clips'].append({
                'hand_id': f'H{n:03d}', 'table_id': table,
                'start_seconds': start, 'end_seconds': end,
                'review_basis': 'human_declared_boundaries_not_automatic_detection'})
        shutil.rmtree(self.fx.math)
        shutil.rmtree(self.fx.clips)
        (self.fx.workspace / 'index.html').unlink()
        self.fx.clips.mkdir()
        self.fx.prepare()
        self.fx.generate()
        self.assertEqual(self.create()['tables'], 4)
        self.assertTrue(self.verify()['verified'])
        html = (self.fx.workspace / 'timeline.html').read_text()
        self.assertIn('Mesa T4', html)
        self.assertIn('4 corte(s)', html)

    def test_more_than_four_tables_rejected(self):
        d = self.build()
        base = copy.deepcopy(d['tables'][0]['rows'][0])
        rows = [base]
        for n in range(2, 6):
            x = copy.deepcopy(base)
            x['hand_id'] = f'H{n:03d}'
            x['table_id'] = f'T{n}'
            x['video'] = f'H{n:03d}.mp4'
            rows.append(x)
        with self.assertRaisesRegex(ValueError, 'more than four'):
            timeline.prepare({'rows': rows, 'source_video_sha256_claim': 'a'*64})

    def test_overlapping_hands_on_same_table_rejected(self):
        d = self.build()
        a = copy.deepcopy(d['tables'][0]['rows'][0])
        b = copy.deepcopy(a)
        b['hand_id'] = 'H999'
        b['video'] = 'H999.mp4'
        b['start'] = a['end'] - 1
        b['end'] = a['end'] + 5
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            timeline.prepare({'rows': [a,b], 'source_video_sha256_claim':'a'*64})

    def test_adjacent_hands_same_table_allowed(self):
        d = self.build()
        a = copy.deepcopy(d['tables'][0]['rows'][0])
        b = copy.deepcopy(a)
        b['hand_id'] = 'H999'
        b['video'] = 'H999.mp4'
        b['start'] = a['end']
        b['end'] = a['end'] + 10
        self.assertEqual(timeline.prepare({'rows':[a,b],
            'source_video_sha256_claim':'a'*64})['total_hands'],2)

    def test_overlapping_across_tables_allowed(self):
        self.assertEqual(self.build()['total_hands'], 2)

    def test_duplicate_hand_id_rejected(self):
        d = self.build()
        a = copy.deepcopy(d['tables'][0]['rows'][0])
        b = copy.deepcopy(a)
        b['table_id'] = 'T9'
        with self.assertRaisesRegex(ValueError, 'duplicate hand'):
            timeline.prepare({'rows':[a,b], 'source_video_sha256_claim':'a'*64})

    def test_session_over_60_minutes_rejected(self):
        d = self.build()
        a = copy.deepcopy(d['tables'][0]['rows'][0])
        a['start'], a['end'] = 3590, 3601
        with self.assertRaisesRegex(ValueError, '60-minute'):
            timeline.prepare({'rows':[a], 'source_video_sha256_claim':'a'*64})

    def test_exact_60_minute_boundary_allowed(self):
        d = self.build()
        a = copy.deepcopy(d['tables'][0]['rows'][0])
        a['start'], a['end'] = 3590, 3600
        self.assertEqual(timeline.prepare({'rows':[a],
            'source_video_sha256_claim':'a'*64})['max_declared_timestamp'],3600)

    def test_boolean_timestamp_rejected(self):
        d = self.build()
        a = copy.deepcopy(d['tables'][0]['rows'][0])
        a['start'] = True
        with self.assertRaisesRegex(ValueError, '60-minute'):
            timeline.prepare({'rows':[a], 'source_video_sha256_claim':'a'*64})

    def test_nan_timestamp_rejected(self):
        d = self.build()
        a = copy.deepcopy(d['tables'][0]['rows'][0])
        a['start'] = float('nan')
        with self.assertRaisesRegex(ValueError, '60-minute'):
            timeline.prepare({'rows':[a], 'source_video_sha256_claim':'a'*64})

    def test_wrong_video_filename_rejected(self):
        d = self.build()
        a = copy.deepcopy(d['tables'][0]['rows'][0])
        a['video'] = '../outside.mp4'
        with self.assertRaisesRegex(ValueError, 'filename'):
            timeline.prepare({'rows':[a], 'source_video_sha256_claim':'a'*64})

    def test_no_rows_rejected(self):
        with self.assertRaisesRegex(ValueError, '1..100'):
            timeline.prepare({'rows':[], 'source_video_sha256_claim':'a'*64})

    def test_100_reviewed_rows_four_tables(self):
        d = self.build()
        base = d['tables'][0]['rows'][0]
        rows=[]
        for n in range(100):
            x=copy.deepcopy(base)
            x['hand_id']=f'H{n:03d}'
            x['table_id']=f'T{n%4+1}'
            x['video']=x['hand_id']+'.mp4'
            x['start']=(n//4)*120
            x['end']=x['start']+90
            rows.append(x)
        out=timeline.prepare({'rows':rows, 'source_video_sha256_claim':'a'*64})
        self.assertEqual(len(out['tables']),4)
        self.assertEqual(out['total_hands'],100)
        self.assertEqual(out['max_declared_timestamp'],2970)
        self.assertIn('H099',timeline.render(out))


if __name__ == '__main__':
    unittest.main()
