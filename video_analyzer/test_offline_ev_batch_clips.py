"""Synthetic four-table batch selection, fail-closed preflight and FFmpeg export."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_ev_batch_clips as batch
import offline_ev_decision_clip as single
import offline_mc_input_contract as contract
from test_offline_ev_decision_clip import ClipTests


class BatchTests(unittest.TestCase):
    def setUp(self):
        ClipTests.setUpClass()
        self.fixture = ClipTests('test_valid_gap_and_clip_interval')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.out = self.root / 'batch_out'
        self.out.mkdir()
        self.batch_path = self.root / 'batch.json'
        self.summary_path = self.fixture.summary_path
        self.video = self.fixture.video
        self.has_ffmpeg = self.fixture.has_ffmpeg
        if not self.has_ffmpeg:
            self.skipTest('ffmpeg/ffprobe required for preflight')

    def make(self, specs=None, *, max_clips=10, min_gap=0):
        # (table, hand, pts, action, before, after) -- all independently manual.
        specs = specs or [('T1', 'H1', 2.0, 'raise', 1.0, 2.0)]
        summary = copy.deepcopy(self.fixture.summary)
        summary['hands'] = []
        for table, hand, pts, action, before, after in specs:
            summary['hands'].append({'hand_id': hand, 'table_id': table,
                                     'math_ready': False, 'eligible_for_equity': False,
                                     'declared_fields': [{'field': 'action', 'street': 'river',
                                                          'visual_status_unverified': 'seen_by_reviewer',
                                                          'evidence_pts_seconds': [pts]}]})
        summary['hand_count'] = len(summary['hands'])
        self.fixture.dump(self.summary_path, summary)
        entries = []
        for i, (table, hand, pts, action, before, after) in enumerate(specs):
            ev = copy.deepcopy(self.fixture.ev)
            ev['hand_id'], ev['table_id'] = hand, table
            ev['source_summary_sha256'] = contract.sha256(self.summary_path)
            ev_path = self.root / f'ev_{i}.json'
            self.fixture.dump(ev_path, ev)
            decision = copy.deepcopy(self.fixture.decision)
            decision.update({'hand_id': hand, 'table_id': table,
                             'source_summary_sha256': contract.sha256(self.summary_path),
                             'source_ev_sha256': contract.sha256(ev_path),
                             'decision_pts_seconds': pts, 'action_taken_claim': action,
                             'clip_before_seconds': before, 'clip_after_seconds': after})
            dec_path = self.root / f'dec_{i}.json'
            self.fixture.dump(dec_path, decision)
            entries.append({'ev_json': ev_path.name, 'decision_json': dec_path.name,
                            'clip_id': f'clip-{i}'})
        doc = {'schema_version': 1, 'status': 'manual_offline_decision_batch_unverified',
               'max_clips': max_clips, 'min_gap_chips': min_gap, 'entries': entries}
        self.fixture.dump(self.batch_path, doc)
        return doc

    def plan(self):
        return batch.prepare(self.summary_path, self.video, self.batch_path, self.out)

    def test_single_preflight(self):
        self.make()
        chosen, skipped, _, _, _, _ = self.plan()
        self.assertEqual(len(chosen), 1)
        self.assertEqual(skipped, [])
        self.assertEqual(chosen[0][1]['conditional_priority_score_chips_not_strategy_verdict'], 50)

    def test_four_tables_sorted_by_gap(self):
        self.make([('T1','H1',1.0,'call',.5,.5), ('T2','H2',2.0,'raise',.5,.5),
                   ('T3','H3',3.0,'fold',.5,.5), ('T4','H4',4.0,'raise',.5,.5)])
        chosen, skipped, *_ = self.plan()
        self.assertEqual([x[0] for x in chosen], ['clip-2','clip-1','clip-3','clip-0'])
        self.assertFalse(skipped)
        self.assertEqual([x[1]['table_id'] for x in chosen], ['T3','T2','T4','T1'])

    def test_stable_tie_order(self):
        self.make([('T2','H2',2.0,'raise',.5,.5), ('T1','H1',2.0,'raise',.5,.5)])
        chosen, *_ = self.plan()
        self.assertEqual([x[0] for x in chosen], ['clip-1','clip-0'])

    def test_same_table_overlap_skipped(self):
        self.make([('T1','H1',2.0,'fold',1,1), ('T1','H2',2.2,'raise',1,1)])
        chosen, skipped, *_ = self.plan()
        self.assertEqual([x[0] for x in chosen], ['clip-0'])
        self.assertEqual(skipped[0]['reason'], 'overlapping_clip_same_table')

    def test_other_table_overlap_allowed(self):
        self.make([('T1','H1',2.0,'raise',1,1), ('T2','H2',2.0,'raise',1,1)])
        chosen, skipped, *_ = self.plan()
        self.assertEqual(len(chosen), 2)
        self.assertFalse(skipped)

    def test_threshold_and_max(self):
        self.make([('T1','H1',1.0,'fold',.5,.5), ('T2','H2',2.0,'raise',.5,.5),
                   ('T3','H3',3.0,'call',.5,.5)], max_clips=1, min_gap=10)
        chosen, skipped, *_ = self.plan()
        self.assertEqual(len(chosen), 1)
        self.assertEqual({x['reason'] for x in skipped}, {'max_clips_reached','below_conditional_gap_threshold'})

    def test_confidence_does_not_weight_ranking(self):
        self.make([('T1','H1',1.0,'fold',.5,.5), ('T2','H2',2.0,'raise',.5,.5)])
        path = self.root / 'dec_0.json'
        dec = contract.read_json(path); dec['reviewer_confidence_claim'] = 0
        self.fixture.dump(path, dec)
        chosen, *_ = self.plan()
        self.assertEqual(chosen[0][0], 'clip-0')

    def test_duplicate_clip_id(self):
        doc = self.make([('T1','H1',1.0,'fold',.5,.5), ('T2','H2',2.0,'raise',.5,.5)])
        doc['entries'][1]['clip_id'] = 'clip-0'
        self.fixture.dump(self.batch_path, doc)
        with self.assertRaisesRegex(ValueError, 'duplicate or unsafe'): self.plan()
        self.assertFalse(list(self.out.iterdir()))

    def test_duplicate_decision_timestamp(self):
        doc = self.make([('T1','H1',1.0,'fold',.5,.5)])
        shutil.copyfile(self.root / 'ev_0.json', self.root / 'ev_1.json')
        shutil.copyfile(self.root / 'dec_0.json', self.root / 'dec_1.json')
        doc['entries'].append({'ev_json': 'ev_1.json', 'decision_json': 'dec_1.json', 'clip_id': 'clip-1'})
        self.fixture.dump(self.batch_path, doc)
        with self.assertRaisesRegex(ValueError, 'duplicate table/hand'): self.plan()

    def test_invalid_entry_path(self):
        doc = self.make(); doc['entries'][0]['ev_json'] = '../secret.json'
        self.fixture.dump(self.batch_path, doc)
        with self.assertRaisesRegex(ValueError, 'basename'): self.plan()

    def test_symlinked_ev_rejected(self):
        self.make()
        ev = self.root / 'ev_0.json'
        data = ev.read_bytes(); ev.unlink()
        (self.root / 'real_ev.json').write_bytes(data)
        ev.symlink_to(self.root / 'real_ev.json')
        with self.assertRaisesRegex(ValueError, 'symlinked'): self.plan()

    def test_ocr_promotion_rejected_before_render(self):
        self.make()
        ev_path = self.root / 'ev_0.json'
        ev = contract.read_json(ev_path); ev['automatic_ocr_math_authorization'] = True
        self.fixture.dump(ev_path, ev)
        with self.assertRaisesRegex(ValueError, 'EV report'): self.plan()
        self.assertEqual(list(self.out.iterdir()), [])

    def test_existing_output_rejected(self):
        self.make(); (self.out / 'clip-0.mp4').write_text('existing')
        with self.assertRaisesRegex(ValueError, 'already exists'): self.plan()
        self.assertEqual((self.out / 'clip-0.mp4').read_text(), 'existing')

    def test_batch_bool_max_rejected(self):
        doc = self.make(); doc['max_clips'] = True
        self.fixture.dump(self.batch_path, doc)
        with self.assertRaisesRegex(ValueError, 'batch parameters'): self.plan()

    def test_nan_gap_rejected(self):
        doc = self.make(); doc['min_gap_chips'] = float('nan')
        self.fixture.dump(self.batch_path, doc)
        with self.assertRaises(ValueError): self.plan()

    def test_more_than_four_tables(self):
        specs = [(f'T{i}',f'H{i}',.5+i*.7,'call',.5,.5) for i in range(1,6)]
        self.make(specs)
        with self.assertRaisesRegex(ValueError, 'more than four tables'): self.plan()

    def test_empty_output_with_threshold_writes_ledger(self):
        self.make(min_gap=999)
        ledger = batch.export(self.summary_path, self.video, self.batch_path, self.out)
        self.assertEqual(ledger['rendered_count'], 0)
        self.assertEqual(ledger['skipped_count'], 1)
        self.assertEqual([p.name for p in self.out.iterdir()], ['batch_report.json'])

    def test_two_mp4s_and_hashes(self):
        self.make([('T1','H1',1.0,'fold',.5,.5), ('T2','H2',3.0,'raise',.5,.5)])
        ledger = batch.export(self.summary_path, self.video, self.batch_path, self.out)
        self.assertEqual(ledger['rendered_count'], 2)
        self.assertEqual(ledger['candidate_count'], 2)
        self.assertFalse(ledger['automatic_ocr_math_authorization'])
        self.assertEqual(len(list(self.out.glob('*.mp4'))), 2)
        for clip in ledger['clips']:
            mp4 = self.out / clip['clip_filename']
            report = contract.read_json(self.out / clip['clip_report_filename'])
            self.assertEqual(clip['clip_sha256'], contract.sha256(mp4))
            self.assertEqual(report['rendered_clip_sha256'], clip['clip_sha256'])
            self.assertGreater(single.video_duration(mp4), .5)
        self.assertEqual(contract.read_json(self.out/'batch_report.json')['rendered_count'], 2)

    def test_partial_failure_rolls_back_own_outputs(self):
        self.make([('T1','H1',1.0,'fold',.5,.5), ('T2','H2',3.0,'raise',.5,.5)])
        original = single.render
        count = [0]
        def broken(*args, **kwargs):
            count[0] += 1
            if count[0] == 2: raise RuntimeError('synthetic renderer failure')
            return original(*args, **kwargs)
        with mock.patch.object(batch.single, 'render', side_effect=broken):
            with self.assertRaisesRegex(RuntimeError, 'synthetic renderer failure'):
                batch.export(self.summary_path, self.video, self.batch_path, self.out)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_input_mutation_rolls_back(self):
        self.make()
        original = single.render
        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            path = self.root / 'dec_0.json'
            path.write_text(path.read_text() + '\n')
            return result
        with mock.patch.object(batch.single, 'render', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'input changed'):
                batch.export(self.summary_path, self.video, self.batch_path, self.out)
        self.assertEqual(list(self.out.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
