"""Synthetic contract tests; no OCR or real-session claims."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import offline_math_mc_bridge as bridge
import offline_reviewed_math_clip_report as join


def candidate(variant='PLO5'):
    n = 5 if variant == 'PLO5' else 6
    return {'schema_version': 1,
            'status': 'timestamp_scoped_reviewed_math_candidate_not_computed',
            'variant': variant, 'table_id': 't1', 'hand_id': 'h1',
            'hero_cards': ['As','Kd','Qc','Jh','Ts'] + (['9s'] if n == 6 else []),
            'board': ['2c','3d','4h'],
            'villain_combos': [{'cards': ['7c','8d','9h','Tc','Js'] + (['6c'] if n == 6 else []), 'weight': 1}],
            'pot_before_call': 100, 'to_call': 20, 'seed': 42, 'trials': 100,
            'model': 'heads_up_call_all_in_no_future_betting_no_rake',
            'range_source': 'Explicit synthetic opponent range',
            'source_review_sha256': 'a'*64, 'source_full_review_sha256': 'a'*64,
            'source_assumptions_sha256': 'b'*64, 'source_full_assumptions_sha256': 'b'*64,
            'automatic_ocr_math_authorization': False,
            'confidence_note': 'Manually asserted synthetic cards and ranges',
            'decision_timestamp_seconds': 25, 'decision_street': 'flop',
            'decision_board_cards': 3}


def manifest(variant='PLO5', digest='c'*64):
    return {'schema_version': 1, 'status': 'offline_reviewed_clip_navigation_only',
            'variant': variant, 'source_reviewed_report_sha256': 'a'*64,
            'automatic_math_authorization': False, 'confidence_calibrated': False,
            'table_identity_verified': False,
            'hands': [{'table_id': 't1', 'hand_id': 'h1', 'start_seconds': 20,
                       'end_seconds': 30, 'automatic_math_authorization': False,
                       'card_evidence_consistent_claim': True, 'review_flags': [],
                       'clips': [{'filename': 'clip.mp4', 'sha256': digest,
                                  'start_seconds': 24, 'end_seconds': 26,
                                  'decision_in_part': True, 'clip_id': 'clip1',
                                  'segment_index': 0}]}]}


class JoinTests(unittest.TestCase):
    def make(self, variant='PLO5'):
        c = candidate(variant)
        sha = hashlib.sha256(json.dumps(c).encode()).hexdigest()
        r = bridge.build(c, sha)
        m = manifest(variant)
        return m, c, r, sha

    def test_plo5(self):
        m,c,r,sha = self.make()
        out = join.build(m,c,r,sha)
        self.assertEqual(out['status'], join.STATUS)
        self.assertEqual(out['clip']['filename'], 'clip.mp4')
        self.assertFalse(out['strategic_correctness_verified'])

    def test_plo6(self):
        m,c,r,sha = self.make('PLO6')
        self.assertEqual(join.build(m,c,r,sha)['variant'], 'PLO6')

    def test_determinism(self):
        m,c,r,sha = self.make()
        self.assertEqual(join.build(m,c,r,sha), join.build(m,c,r,sha))

    def test_wrong_review_digest(self):
        m,c,r,sha = self.make();m['source_reviewed_report_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'provenance'):
            join.build(m,c,r,sha)

    def test_wrong_candidate_digest(self):
        m,c,r,sha = self.make()
        with self.assertRaisesRegex(ValueError,'provenance'):
            join.build(m,c,r,'e'*64)

    def test_math_report_tamper(self):
        m,c,r,sha = self.make();r['ev_call_estimate']+=10
        with self.assertRaisesRegex(ValueError,'recomputed'):
            join.build(m,c,r,sha)

    def test_wrong_hand(self):
        m,c,r,sha = self.make();m['hands'][0]['hand_id']='other'
        with self.assertRaisesRegex(ValueError,'missing or ambiguous'):
            join.build(m,c,r,sha)

    def test_missing_clip(self):
        m,c,r,sha = self.make();m['hands'][0]['clips']=[]
        with self.assertRaisesRegex(ValueError,'clip missing'):
            join.build(m,c,r,sha)

    def test_ambiguous_clips(self):
        m,c,r,sha = self.make();m['hands'][0]['clips'].append(copy.deepcopy(m['hands'][0]['clips'][0]))
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            join.build(m,c,r,sha)

    def test_decision_omitted(self):
        m,c,r,sha = self.make();m['hands'][0]['clips'][0]['decision_in_part']=False
        with self.assertRaisesRegex(ValueError,'clip missing'):
            join.build(m,c,r,sha)

    def test_unresolved_conflicts(self):
        m,c,r,sha = self.make();m['hands'][0]['review_flags']=['board conflict']
        with self.assertRaisesRegex(ValueError,'clean hand'):
            join.build(m,c,r,sha)

    def test_unsafe_filename(self):
        m,c,r,sha = self.make();m['hands'][0]['clips'][0]['filename']='../escape.mp4'
        with self.assertRaisesRegex(ValueError,'metadata'):
            join.build(m,c,r,sha)

    def test_html_escaped(self):
        m,c,r,sha = self.make();m['hands'][0]['table_id']='<script>'
        c['table_id']='<script>'
        r['table_id']='<script>'
        with patch.object(join.bridge, 'build', return_value=r):
            page=join.html_page(join.build(m,c,r,sha), '..')
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('<script>',page)

    def test_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); media=root/'media';out=root/'out';media.mkdir();out.mkdir()
            (media/'clip.mp4').write_bytes(b'fake synthetic bytes')
            digest=hashlib.sha256((media/'clip.mp4').read_bytes()).hexdigest()
            m,c,r,sha=self.make();m['hands'][0]['clips'][0]['sha256']=digest
            files=[root/f'{x}.json' for x in ('manifest','candidate','report')]
            for p,obj in zip(files,(m,c,r)):
                p.write_text(json.dumps(obj))
            # Rebind report to exact bytes of the candidate on disk.
            r=bridge.build(c,hashlib.sha256(files[1].read_bytes()).hexdigest())
            files[2].write_text(json.dumps(r))
            result=join.export(*files,media,out)
            self.assertEqual(result['status'],join.STATUS)
            self.assertTrue((out/join.HTML_NAME).is_file())
            self.assertEqual(json.loads((out/join.JSON_NAME).read_text())['clip']['sha256'],digest)
            with self.assertRaisesRegex(ValueError,'collision'):
                join.export(*files,media,out)

    def test_modified_media_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);media=root/'media';out=root/'out';media.mkdir();out.mkdir()
            (media/'clip.mp4').write_bytes(b'tampered')
            m,c,r,sha=self.make()
            files=[root/f'{x}.json' for x in ('manifest','candidate','report')]
            for p,obj in zip(files,(m,c,r)):
                p.write_text(json.dumps(obj))
            r=bridge.build(c,hashlib.sha256(files[1].read_bytes()).hexdigest())
            files[2].write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'modified'):
                join.export(*files,media,out)
            self.assertEqual(list(out.iterdir()),[])


if __name__ == '__main__': unittest.main()
