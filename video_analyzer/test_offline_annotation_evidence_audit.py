"""Synthetic regression tests for annotation/evidence audit."""
import copy
import unittest
from offline_annotation_evidence_audit import audit_annotation_evidence
H = 'a'*64
B = {'status':'UNREVIEWED_EVIDENCE_REVIEW_BUNDLE','evidence_json_sha256':H,
     'timeline':{'status':'UNREVIEWED_TIMELINE','absolute_source_pts_verified':False,
                 'hand_boundaries_verified':False,'ocr_verified':False,'equity_ev_verified':False,
                 'events':[{'table_id':i,'frame_index':0,'crop_pts_seconds':2.0,
                            'rgb_sha256':H,'review_status':'UNREVIEWED'} for i in range(1,5)]}}
A = {'evidence_json_sha256':H,'hands':[{'table_id':str(i),'hand_id':'h1','variant':'PLO5',
     'start_seconds':1,'end_seconds':3,'hero_cards':[],'board_cards':[]} for i in range(1,5)]}
class AuditTests(unittest.TestCase):
    def run_audit(self,b=None,a=None,**kwargs):
        return audit_annotation_evidence(copy.deepcopy(B if b is None else b),
                                         copy.deepcopy(A if a is None else a),**kwargs)
    def test_four_tables(self):
        r=self.run_audit()
        self.assertEqual([h['sample_count'] for h in r['hands']],[1]*4)
        self.assertFalse(r['hands_verified'])
    def test_unknown_table(self):
        a=copy.deepcopy(A);a['hands'][0]['table_id']='5'
        with self.assertRaises(ValueError):self.run_audit(a=a)
    def test_noncanonical_table(self):
        a=copy.deepcopy(A);a['hands'][0]['table_id']='01'
        with self.assertRaises(ValueError):self.run_audit(a=a)
    def test_missing_sample(self):
        a=copy.deepcopy(A);a['hands'][0]['start_seconds']=4;a['hands'][0]['end_seconds']=5
        with self.assertRaises(ValueError):self.run_audit(a=a)
        self.assertFalse(self.run_audit(a=a,require_samples=False)['hands'][0]['temporal_sample_coverage_only'])
    def test_duplicate_frame(self):
        b=copy.deepcopy(B);b['timeline']['events'].append(copy.deepcopy(b['timeline']['events'][0]))
        with self.assertRaises(ValueError):self.run_audit(b=b)
    def test_verified_flag_rejected(self):
        b=copy.deepcopy(B);b['timeline']['ocr_verified']=True
        with self.assertRaises(ValueError):self.run_audit(b=b)
    def test_nan_pts(self):
        b=copy.deepcopy(B);b['timeline']['events'][0]['crop_pts_seconds']=float('nan')
        with self.assertRaises(ValueError):self.run_audit(b=b)
    def test_nonmonotonic_pts(self):
        b=copy.deepcopy(B);e=copy.deepcopy(b['timeline']['events'][0]);e['frame_index']=1
        b['timeline']['events'].append(e)
        with self.assertRaises(ValueError):self.run_audit(b=b)
    def test_nominal_source_offset_not_crop_pts(self):
        b=copy.deepcopy(B)
        for event in b['timeline']['events']:
            event['nominal_source_seconds']=102.0
            event['nominal_source_seconds_verified']=False
        a=copy.deepcopy(A)
        for hand in a['hands']:
            hand['start_seconds']=101
            hand['end_seconds']=103
        self.assertEqual(self.run_audit(b=b,a=a)['hands'][0]['sample_count'],1)
        with self.assertRaises(ValueError):
            self.run_audit(b=b)

    def test_mixed_time_coordinates_rejected(self):
        b=copy.deepcopy(B)
        e=copy.deepcopy(b['timeline']['events'][0])
        e['frame_index']=1
        e['crop_pts_seconds']=3.0
        e['nominal_source_seconds']=103.0
        e['nominal_source_seconds_verified']=False
        b['timeline']['events'].append(e)
        with self.assertRaises(ValueError):
            self.run_audit(b=b)

    def test_unverified_nominal_claim_rejected(self):
        b=copy.deepcopy(B)
        b['timeline']['events'][0]['nominal_source_seconds']=102.0
        b['timeline']['events'][0]['nominal_source_seconds_verified']=True
        with self.assertRaises(ValueError):
            self.run_audit(b=b)

    def test_digest_mismatch(self):
        a=copy.deepcopy(A);a['evidence_json_sha256']='b'*64
        with self.assertRaises(ValueError):self.run_audit(a=a)
if __name__=='__main__':unittest.main()
