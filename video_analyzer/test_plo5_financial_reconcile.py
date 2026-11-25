import copy
import unittest
from plo5_financial_reconcile import reconcile, build

FRAMES={f'f{i}':{'file':f'f{i}','pts':i,'hero_seat_declared':1,'crop_sha256':f'{i:064x}'} for i in range(8)}


def review(events,after,*,before='100',complete=True):
    return {'draft_id':'d1','hero_seat':1,'complete':complete,'reviewer':'fixture',
            'before':{'file':'f0','bb':before},'after':{'file':'f7','bb':after},
            'events':[{'file':f'f{i+1}','kind':k,'bb':v} for i,(k,v) in enumerate(events)]}


def fixture(row):
    identity={'job_id':'a'*32,'variant':5,'source_sha256':'b'*64,'manifest_sha256':'c'*64}
    binding={**identity,'reports':{'evidence/ingest/manifest.json':'c'*64}}
    manifest={'source_sha256':'b'*64,'samples':[{'file':f['file'],'table_id':1,'actual_frame_timestamp_seconds':f['pts'],'sha256':f['crop_sha256']} for f in FRAMES.values()]}
    drafts={**identity,'status':'unverified_hand_timeline_drafts','equity_ev_authorized':False,'hands_reconstructed':False,
            'drafts':[{'draft_id':'d1','table_id':1,'hand_id':None,'complete_hand_verified':False,'frames':list(FRAMES.values())}],'unassigned':[]}
    results={**identity,'status':'unverified_result_label_episodes','equity_ev_authorized':False,'hands_reconstructed':False,
             'draft_sha256':'d'*64,'financial_result_bb':None,'payouts_verified':False}
    reviews={'variant':5,'job_id':'a'*32,'draft_sha256':'d'*64,'result_sha256':'e'*64,'reviews':[row]}
    return binding,manifest,drafts,results,reviews,'d'*64,'e'*64


class FinancialTests(unittest.TestCase):
    def test_fold_loss_strict_threshold(self):
        for amount,after,flag in [('30','70',False),('30.000001','69.999999',True),('45','55',True)]:
            r=reconcile(review([('contribution',amount)],after),FRAMES)
            self.assertEqual(r['conditional_loss_over_30bb'],flag)
            self.assertEqual(r['conditional_net_bb'],'-'+amount)
            self.assertFalse(r['automatic_clip_selection_authorized'])

    def test_payouts_returns_and_rebuy(self):
        r=reconcile(review([('contribution','60'),('return','5'),('payout','80'),('payout','20'),('rebuy','100')],'245'),FRAMES)
        self.assertEqual(r['conditional_net_bb'],'45')
        self.assertEqual(r['external_adjustment_bb'],'100')
        self.assertEqual(r['residual_bb'],'0')
        self.assertIsNone(r['ev_loss_bb'])

    def test_rebuy_masks_loss_and_withdrawal(self):
        r=reconcile(review([('contribution','80'),('rebuy','100'),('withdrawal','10')],'110'),FRAMES)
        self.assertEqual(r['conditional_net_bb'],'-80')
        self.assertTrue(r['conditional_loss_over_30bb'])

    def test_unresolved_missing_and_mismatch(self):
        for row in [review([('contribution','40')],'61'),review([('contribution','40')],'60',complete=False)]:
            r=reconcile(row,FRAMES)
            self.assertEqual(r['status'],'unresolved');self.assertIsNone(r['conditional_net_bb']);self.assertIsNone(r['conditional_loss_over_30bb'])
        row=review([],'100');row['before']=None
        self.assertIsNone(reconcile(row,FRAMES)['residual_bb'])

    def test_impossible_running_balance_or_return(self):
        for row in (review([('contribution','110'),('payout','20')],'10'),review([('contribution','10'),('return','11')],'101')):
            self.assertEqual(reconcile(row,FRAMES)['status'],'unresolved')

    def test_reject_duplicate_order_units_and_hero(self):
        base=review([('contribution','10'),('return','5')],'95')
        for change in ('duplicate','order','unit','float','negative','outside','hero'):
            row=copy.deepcopy(base)
            if change=='duplicate':row['events'][1]['file']='f1'
            elif change=='order':row['events'].reverse()
            elif change=='unit':row['events'][0]['bb']='10 BB'
            elif change=='float':row['events'][0]['bb']=10.0
            elif change=='negative':row['events'][0]['bb']='-10'
            elif change=='outside':row['events'][0]['file']='f7'
            else:row['hero_seat']=2
            with self.subTest(change=change),self.assertRaises(ValueError):reconcile(row,FRAMES)

    def test_bound_review_and_unreviewed(self):
        args=fixture(review([('contribution','40')],'60'))
        r=build(*args);self.assertEqual(r['reviews'][0]['conditional_net_bb'],'-40');self.assertFalse(r['financial_results_verified'])
        args[4]['reviews']=[]
        self.assertEqual(build(*args)['unreviewed_draft_ids'],['d1'])

    def test_reject_mixed_provenance_and_duplicate_review(self):
        base=fixture(review([('contribution','40')],'60'))
        for change in ('source','manifest','review','frame','variant','duplicate'):
            args=copy.deepcopy(base)
            if change=='source':args[3]['source_sha256']='f'*64
            elif change=='manifest':args[3]['manifest_sha256']='f'*64
            elif change=='review':args[4]['result_sha256']='f'*64
            elif change=='frame':args[2]['drafts'][0]['frames'][0]['crop_sha256']='f'*64
            elif change=='variant':args[2]['variant']=6
            else:args[4]['reviews']*=2
            with self.subTest(change=change),self.assertRaises(ValueError):build(*args)


if __name__=='__main__':unittest.main()
