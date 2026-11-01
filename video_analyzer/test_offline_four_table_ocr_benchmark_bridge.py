import json
from pathlib import Path
import tempfile
import unittest

from offline_four_table_ocr_benchmark_bridge import adapt, build, parse, run

SHA = 'a' * 64


def original(*candidates):
    return {'schema_version': 1, 'analysis_status': 'unverified_four_table_ocr_proposals_only',
            'ready_for_equity_or_ev': False, 'requires_manual_review': True,
            'automatic_hand_or_action_inference': False,
            'engine_confidence_is_calibrated_probability': False,
            'recording_sha256': SHA, 'source_region_samples_sha256': SHA,
            'candidates': list(candidates)}


def c(field='pot', text='12.50', table=1, sample=0, pts=1.0):
    return {'table_id': table, 'sample_index': sample, 'field': field,
            'decoded_source_pts_seconds': pts, 'status': 'needs_manual_review',
            'parsed_candidate': None, 'source_crop_sha256': SHA,
            'source_crop_path': 'table_1/frame_1.png', 'raw_ocr_text': text}


def g(field='pot', value=12.5, table=1, pts=1.0):
    return {'table_id': table, 'field': field, 'timestamp': pts, 'expected': value}


class BridgeTests(unittest.TestCase):
    def test_exact_numeric(self):
        self.assertEqual(parse('pot', '12.50'), 12.5)
        self.assertEqual(parse('bet', '0'), 0.0)

    def test_ambiguous_numeric_abstains(self):
        for text in ('R$ 12', '1,234', '-2', '1e3', 'nan', '12 chips', '01', '1000000000'):
            with self.subTest(text=text):
                self.assertIsNone(parse('pot', text))

    def test_cards_strict(self):
        self.assertEqual(parse('hero_cards', 'As Kh Qd Jc Ts'), ['As','Kh','Qd','Jc','Ts'])
        self.assertEqual(parse('hero_cards', 'As Kh Qd Jc Ts 9s'), ['As','Kh','Qd','Jc','Ts','9s'])
        self.assertEqual(parse('board', 'As Kh Qd'), ['As','Kh','Qd'])
        self.assertIsNone(parse('hero_cards', 'As Kh Qd'))
        self.assertIsNone(parse('board', 'As As'))
        self.assertIsNone(parse('board', 'AS Kh'))

    def test_four_table_mixed_outcomes(self):
        s = original(c(), c('board','As Kh Qd',2,1,2),
                     c('bet','R$ 10',3,2,3), c('pot','11',4,3,4))
        labels = [g(),g('board',['As','Kh','Qd'],2,2),g('bet',10,3,3),g('pot',12,4,4)]
        r = build(s,labels,SHA,SHA)
        self.assertEqual((r['summary']['correct'],r['summary']['incorrect'],
                          r['summary']['abstained_or_missing']), (2,1,1))
        self.assertEqual(r['unparseable_or_ambiguous_abstentions'], 1)
        self.assertFalse(r['ready_for_equity_or_ev'])

    def test_unsupported_excluded_explicitly(self):
        r=build(original(c('action','fold'),c('stack','100',2,1)),[],SHA,SHA)
        self.assertEqual(r['excluded_unsupported_fields'],{'action':1,'stack':1})
        self.assertEqual(r['evaluated_candidate_count'],0)

    def test_cross_table_isolation(self):
        r=build(original(c(table=2)),[g(table=1)],SHA,SHA)
        self.assertEqual(r['summary']['correct'],0)
        self.assertEqual(r['summary']['unmatched_answered_predictions'],1)

    def test_duplicate_source_rejected(self):
        with self.assertRaises(ValueError): adapt(original(c(),c()))

    def test_promoted_source_rejected(self):
        s=original(c());s['ready_for_equity_or_ev']=True
        with self.assertRaises(ValueError): adapt(s)

    def test_bad_source_types_rejected(self):
        for key,value in [('table_id',True),('decoded_source_pts_seconds',float('nan')),
                          ('source_crop_sha256','wrong'),('parsed_candidate',12)]:
            s=original(c());s['candidates'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): adapt(s)

    def test_unknown_ground_truth_field_rejected(self):
        with self.assertRaises(ValueError): build(original(c()),[g('stack',10)],SHA,SHA)

    def test_timestamp_mismatch(self):
        r=build(original(c()),[g(pts=4)],SHA,SHA)
        self.assertEqual(r['summary']['correct'],0)

    def test_create_only_and_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);o=root/'ocr.json';gpath=root/'gold.json';out=root/'result.json'
            o.write_text(json.dumps(original(c())));gpath.write_text(json.dumps([g()]))
            r=run(o,gpath,out)
            self.assertEqual(r['summary']['correct'],1)
            self.assertEqual(len(r['source_original_ocr_sha256']),64)
            with self.assertRaises(ValueError):run(o,gpath,out)
            self.assertEqual(json.loads(out.read_text())['summary']['correct'],1)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);o=root/'ocr.json';gpath=root/'gold.json';out=root/'result.json'
            o.write_text('{"candidates":[],"candidates":[]}');gpath.write_text('[]')
            with self.assertRaises(ValueError):run(o,gpath,out)
            self.assertFalse(out.exists())

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);o=root/'ocr.json';alias=root/'alias.json';gpath=root/'gold.json';out=root/'result.json'
            o.write_text(json.dumps(original(c())));alias.symlink_to(o)
            gpath.write_text('[]')
            with self.assertRaises(ValueError):run(alias,gpath,out)

    def test_large_raw_ocr_abstains(self):
        self.assertIsNone(parse('pot','x'*4096))

    def test_bool_tolerance_rejected(self):
        with self.assertRaises(ValueError):build(original(c()),[],SHA,SHA,tolerance_seconds=True)


if __name__=='__main__':
    unittest.main()
