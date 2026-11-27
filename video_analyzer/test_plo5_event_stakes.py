import unittest
from plo5_event_stakes import associate,positive

class EventStakeTests(unittest.TestCase):
    def stakes(self,value,table=1,seat='upper_right'):
        return {'table_id':table,'platform':'suprema','stakes':[{'seat':seat,'value_bb':value}]}
    def labels(self,label='raise'):
        return [{'seat':'upper_right','label_candidate':label,'action_verified':False}]
    def test_agreement_not_action_size(self):
        r=associate(self.labels(),self.stakes('15.5'),self.stakes('15.5'))[0]
        self.assertEqual(r['displayed_stake_bb_candidate'],'15.5');self.assertEqual(r['association_status'],'SAME_SEAT_CO_VISIBLE_CANDIDATE');self.assertIsNone(r['action_amount_bb']);self.assertFalse(r['amount_verified'])
    def test_mismatch_or_missing(self):
        for v in (None,'0','1','NaN','Infinity'):
            r=associate(self.labels(),self.stakes('15.5'),self.stakes(v))[0];self.assertIsNone(r['displayed_stake_bb_candidate']);self.assertEqual(r['association_status'],'INCONCLUSIVE')
    def test_wrong_seat(self):
        self.assertIsNone(associate(self.labels(),self.stakes('1',seat='top'),self.stakes('1',seat='top'))[0]['displayed_stake_bb_candidate'])
    def test_no_label(self):
        self.assertEqual(associate(self.labels(None),self.stakes('1'),self.stakes('1'))[0]['association_status'],'INCONCLUSIVE')
    def test_context_and_duplicates(self):
        with self.assertRaises(ValueError):associate(self.labels(),self.stakes('1'),self.stakes('1',table=2))
        a=self.stakes('1');a['stakes']*=2
        with self.assertRaises(ValueError):associate(self.labels(),a,a)
    def test_invalid_amount(self):
        for x in (None,1,'NaN','Inf','-1','0','bad'):self.assertFalse(positive(x))
        self.assertTrue(positive('0.5'))
if __name__=='__main__':unittest.main()
