import unittest
from poker_cortes_multitable_gate import route_evidence
H='a'*64

def hand(table, name, start=0, end=10):
    return dict(video_sha256=H, table_id=table, hand_id=name, start_seconds=start, end_seconds=end)

def obs(table, t, value=100, video=H):
    return dict(video_sha256=video, table_id=table, time_seconds=t, stack_bb=value, source_frame=f'{table}-{t}')

class RouterTests(unittest.TestCase):
    def test_four_tables(self):
        r=route_evidence([hand(i,str(i)) for i in range(1,5)], [obs(i,5) for i in range(1,5)])
        self.assertEqual([len(x['stack_samples']) for x in r['hands']], [1]*4)
    def test_no_cross_table(self):
        r=route_evidence([hand(1,'one')], [obs(2,5)])
        self.assertEqual(len(r['unresolved_observations']),1)
    def test_no_cross_video(self):
        r=route_evidence([hand(1,'one')], [obs(1,5,video='b'*64)])
        self.assertEqual(len(r['unresolved_observations']),1)
    def test_ambiguous_overlap(self):
        r=route_evidence([hand(1,'a'),hand(1,'b',5,15)],[obs(1,7)])
        self.assertEqual(r['unresolved_observations'][0]['reason'],'AMBIGUOUS_HAND')
        self.assertTrue(all(not x['stack_samples'] for x in r['hands']))
    def test_boundary(self):
        r=route_evidence([hand(1,'a')],[obs(1,0),obs(1,10)])
        self.assertEqual(len(r['hands'][0]['stack_samples']),2)
    def test_bad_table(self):
        with self.assertRaises(ValueError): route_evidence([hand(5,'x')],[])
    def test_duplicate_hand(self):
        with self.assertRaises(ValueError): route_evidence([hand(1,'a'),hand(1,'a')],[])
    def test_bad_hash(self):
        with self.assertRaises(ValueError): route_evidence([dict(hand(1,'a'),video_sha256='bad')],[])
    def test_nan_time(self):
        with self.assertRaises(ValueError): route_evidence([hand(1,'a')],[obs(1,float('nan'))])
    def test_financial_never_confirmed(self):
        r=route_evidence([dict(hand(1,'a'),status='CONFIRMADO')],[obs(1,1,320),obs(1,9,0)])
        self.assertIsNone(r['hands'][0]['confirmed_loss_bb'])
        self.assertFalse(r['financial_confirmation_authorized'])
        self.assertIn('LARGE_STACK_JUMP_RECHECK_OCR',r['hands'][0]['flags'])
    def test_unmatched_time(self):
        r=route_evidence([hand(1,'a')],[obs(1,11)])
        self.assertEqual(r['unresolved_observations'][0]['reason'],'NO_MATCHING_HAND')
    def test_invalid_observation_type(self):
        with self.assertRaises(ValueError): route_evidence([hand(1,'a')],[None])

    def test_uppercase_video_hash_matches(self):
        candidate = dict(hand(1, 'a'), video_sha256='A'*64)
        observation = obs(1, 5)
        result = route_evidence([candidate], [observation])
        self.assertEqual(len(result['hands'][0]['stack_samples']), 1)

    def test_uppercase_observation_hash_matches(self):
        result = route_evidence([hand(1, 'a')], [obs(1, 5, video='A'*64)])
        self.assertEqual(len(result['hands'][0]['stack_samples']), 1)

    def test_unmatched_bad_stack_rejected(self):
        with self.assertRaises(ValueError):
            route_evidence([hand(1, 'a')], [obs(2, 5, float('nan'))])

    def test_unmatched_missing_frame_rejected(self):
        observation = obs(2, 5)
        del observation['source_frame']
        with self.assertRaises(ValueError):
            route_evidence([hand(1, 'a')], [observation])

if __name__=='__main__': unittest.main()
