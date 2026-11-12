import copy
import unittest
from offline_review_decision_gate import assess


def sample():
    fields = ('table', 'hand_boundary', 'hero_cards', 'board_cards', 'action', 'pot', 'call')
    return dict(schema_version=1, hand_id='synthetic_01', variant='PLO5', table_id=1,
                start_seconds=10., end_seconds=20., hero_cards=['As','Ks','Qs','Js','Ts'],
                board_cards=['2c','3d','4h'], action='call', pot_bb=15., call_bb=5.,
                ranges_assumed=True, source_video_sha256='a'*64,
                field_evidence={k:dict(status='human_confirmed',confidence=1.,timestamp_seconds=15.) for k in fields})

class GateTests(unittest.TestCase):
    def test_ready(self):
        result=assess(sample())
        self.assertEqual(result['analysis_status'],'READY_FOR_CONDITIONAL_MODEL')
        self.assertFalse(result['strategic_error_established'])
        self.assertFalse(result['source_hand_reconstruction_verified'])
    def test_ocr_never_promoted(self):
        s=sample();s['field_evidence']['hero_cards']['status']='ocr_candidate'
        self.assertEqual(assess(s)['analysis_status'],'INSUFFICIENT_DATA')
    def test_missing_range(self):
        s=sample();s['ranges_assumed']=False
        self.assertIn('ranges_not_supplied',assess(s)['missing_or_unconfirmed'])
    def test_hidden_cards(self):
        s=sample();s['hero_cards']=[]
        self.assertIn('hero_cards_not_visible',assess(s)['missing_or_unconfirmed'])
    def test_missing_board(self):
        s=sample();s['board_cards']=['2c','3d']
        self.assertIn('insufficient_board',assess(s)['missing_or_unconfirmed'])
    def test_duplicate_cards(self):
        s=sample();s['board_cards'][0]='As'
        with self.assertRaises(ValueError):assess(s)
    def test_invalid_timestamp(self):
        s=sample();s['end_seconds']=9.
        with self.assertRaises(ValueError):assess(s)
    def test_evidence_outside_interval(self):
        s=sample();s['field_evidence']['pot']['timestamp_seconds']=30.
        with self.assertRaises(ValueError):assess(s)
    def test_bool_money(self):
        s=sample();s['pot_bb']=True
        with self.assertRaises(ValueError):assess(s)
    def test_invalid_sha(self):
        s=sample();s['source_video_sha256']='fake'
        with self.assertRaises(ValueError):assess(s)
    def test_plo6(self):
        s=sample();s['variant']='PLO6';s['hero_cards'].append('9s')
        self.assertEqual(assess(s)['analysis_status'],'READY_FOR_CONDITIONAL_MODEL')
    def test_plo6_wrong_count(self):
        s=sample();s['variant']='PLO6'
        with self.assertRaises(ValueError):assess(s)
    def test_call_without_cost(self):
        s=sample();s['call_bb']=0
        self.assertIn('call_cost_missing',assess(s)['missing_or_unconfirmed'])
    def test_unknown_action(self):
        s=sample();s['action']='unknown'
        self.assertIn('action_unknown',assess(s)['missing_or_unconfirmed'])
    def test_invalid_confidence(self):
        s=sample();s['field_evidence']['pot']['confidence']=1.1
        with self.assertRaises(ValueError):assess(s)
    def test_bad_field_schema(self):
        s=sample();del s['field_evidence']['pot']
        with self.assertRaises(ValueError):assess(s)

if __name__=='__main__':unittest.main()
