import unittest
from test_plo5_reconstruction_candidates import frame,B
from plo5_seat_evidence import SEATS
from plo5_temporal_evidence import inspect


def sample(t,stack='100',pot='2',*,board=None,dealer='top',missing=False,label='call',hero_other=None):
    f=frame(t,stack,pot,b=board);c=f['cards'][0]
    c['seat_evidence']=dict(table_id=1,platform='pppoker',dealer={'seat':dealer},positions_verified=False,actions_verified=False,financial_result_verified=False,seats=[dict(seat=s,stack={'candidate':(hero_other or stack) if s=='hero_bottom' else None if missing and s=='top' else '100'},action={'candidate':label}) for s in SEATS]);return f


class TemporalTests(unittest.TestCase):
    def test_conserved_display_not_action(self):
        r=inspect([sample(0),sample(1,'98','4')]);p=r['intervals'][0]
        self.assertEqual(p['status'],'CONSISTENT_DISPLAY_DELTAS');self.assertEqual(p['stack_display_deltas_bb']['hero_bottom'],'-2');self.assertEqual(p['label_changes'],{});self.assertFalse(r['strategy_authorized'])
    def test_blockers_and_rebuy(self):
        p=inspect([sample(0,missing=True),sample(1,'110','0',hero_other='109')])['intervals'][0]
        self.assertEqual(p['status'],'SAME_STREET_BLOCKED');self.assertIn('STACK_INCREASE_UNRESOLVED',p['blockers']);self.assertIn('INCOMPLETE_STACK_OR_POT',p['blockers']);self.assertIn('HERO_STACK_NOT_CORROBORATED',p['blockers'])
        p=inspect([sample(0),sample(1,'90','3')])['intervals'][0];self.assertIn('DISPLAY_NOT_CONSERVED',p['blockers'])
    def test_street_gap_dealer(self):
        for a,b,status in ((sample(0),sample(1,board=B),'STREET_ADVANCE_CANDIDATE'),(sample(0),sample(2),'GAP'),(sample(0),sample(1,dealer='upper_left'),'DEALER_CONTINUITY_UNKNOWN')):
            self.assertEqual(inspect([a,b])['intervals'][0]['status'],status)
    def test_unknown_cards_and_reset(self):
        a,b=sample(0),sample(1);b['cards'][0]['hero_cards']=None
        self.assertEqual(inspect([a,b])['intervals'][0]['status'],'CARD_CONTINUITY_UNKNOWN')
        a,b=sample(0),sample(1);b['cards'][0]['hero_cards']=['Ah','Kh','Qs','Jc','Td']
        self.assertEqual(inspect([a,b])['intervals'][0]['status'],'HAND_BOUNDARY_OR_CARD_CONFLICT')
    def test_no_bridge_absent(self):
        a,b,c=sample(0),frame(1,platform=None),sample(2)
        self.assertEqual(inspect([a,b,c])['intervals'],[])

if __name__=='__main__':unittest.main()
