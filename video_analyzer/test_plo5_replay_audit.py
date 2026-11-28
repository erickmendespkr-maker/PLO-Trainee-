import unittest
from plo5_replay_audit import audit_auto_events

H=['As','Ks','Qh','Jd','Tc']
B=['2c','3d','4h','5s','6s']


def seed():
    return dict(hand_id='h',table_id=1,dealt=['hero_bottom','top'],
                button='hero_bottom',initial={'hero_bottom':40,'top':40},
                sb=1,bb=2,pot_includes_pending=True,holding=H)


class ReplayAuditTests(unittest.TestCase):
    def test_fold_terminal_is_legal_prefix_not_verified_hand(self):
        events=[dict(position='SB',action='raise',amount=3),
                dict(position='BB',action='fold',amount=0)]
        result=audit_auto_events(seed(),events,'fold_terminal')
        self.assertEqual(result['status'],'LEGAL_PREFIX_CONSISTENT')
        self.assertEqual(result['terminal_candidate'],'fold_terminal')
        self.assertFalse(result['hand_verified'])
        self.assertFalse(result['financial_result_verified'])
        self.assertFalse(result['strategy_authorized'])

    def test_replay_through_all_streets(self):
        events=[dict(position='SB',action='call',amount=1),
                dict(position='BB',action='check',amount=0),
                dict(cards=B[:3])]
        events.extend(dict(position=p,action='check',amount=0) for p in ('BB','SB'))
        events.append(dict(cards=B[3:4]))
        events.extend(dict(position=p,action='check',amount=0) for p in ('BB','SB'))
        events.append(dict(cards=B[4:]))
        events.extend(dict(position=p,action='check',amount=0) for p in ('BB','SB'))
        result=audit_auto_events(seed(),events,'river_showdown')
        self.assertEqual(result['status'],'LEGAL_PREFIX_CONSISTENT')
        self.assertEqual(result['board'],B)
        self.assertEqual(result['terminal_candidate'],'river_showdown')

    def test_action_order_rejected(self):
        result=audit_auto_events(seed(),[dict(position='BB',action='fold',amount=0)])
        self.assertEqual(result['status'],'INVALID_LEGAL_PREFIX')

    def test_unclosed_preflop_cannot_reveal_flop(self):
        result=audit_auto_events(seed(),[dict(cards=B[:3])])
        self.assertEqual(result['status'],'INVALID_LEGAL_PREFIX')

    def test_hero_card_duplicate_rejected(self):
        result=audit_auto_events(seed(),[dict(cards=['As','3d','4h'])])
        self.assertEqual(result['status'],'INVALID_LEGAL_PREFIX')

    def test_terminal_mismatch_rejected(self):
        events=[dict(position='SB',action='raise',amount=3),
                dict(position='BB',action='fold',amount=0)]
        result=audit_auto_events(seed(),events,'river_showdown')
        self.assertEqual(result['status'],'TERMINAL_MISMATCH')

    def test_event_budget_and_schema(self):
        self.assertEqual(audit_auto_events(seed(),[{}])['status'],'INVALID_LEGAL_PREFIX')
        self.assertEqual(audit_auto_events(seed(),[{}]*513)['status'],'INVALID_LEGAL_PREFIX')


if __name__=='__main__':
    unittest.main()
