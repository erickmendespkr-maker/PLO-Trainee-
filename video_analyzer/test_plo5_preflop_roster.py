import unittest
from copy import deepcopy
from plo5_preflop_roster import snapshot,candidates,OPP
from test_plo5_card_review import frame


def sample(t,platform='pppoker',empty=()):
    f=frame(t,platform=platform)
    if platform=='suprema':f['cards'][0]['rank_profile']='suprema-soft-1504x696-v2'
    f['seats']=[{'table_id':i,'platform':platform if i==1 else None,'positions_verified':False,'dealt_roster_verified':False,'dealer_seat_candidate':'top' if i==1 else None,'hero_seat_candidate':'hero_bottom' if i==1 else None,'opponents':[{'seat':s,'status':'explicit_empty_marker_candidate' if s in empty else 'card_backs_visible_candidate','dealt_verified':False} for s in sorted(OPP)] if i==1 else []} for i in range(1,5)]
    return f


class RosterTests(unittest.TestCase):
    def test_repeated_six(self):
        r=candidates([sample(1),sample(2),sample(3)])[0];self.assertEqual(r['samples'],3);self.assertEqual(r['positions_if_standard_blinds_and_full_roster']['hero_bottom'],'UTG');self.assertIsNone(r['hero_position']);self.assertFalse(r['strategy_authorized']);self.assertFalse(r['blinds_verified'])
    def test_short_handed(self):
        f=[sample(i,empty=('upper_right','lower_right')) for i in (1,2)]
        r=candidates(f)[0];self.assertEqual(len(r['visible_dealt_seats']),4);self.assertEqual(r['positions_if_standard_blinds_and_full_roster']['hero_bottom'],'SB')
    def test_ambiguous(self):
        for status in ('unknown','conflicting_visual_evidence'):
            f=sample(2);f['seats'][0]['opponents'][0]['status']=status
            self.assertEqual(candidates([sample(1),f,sample(3)]),[])
    def test_board_absence_not_proven(self):
        for b in (None,['2c','3d','4h']):
            f=sample(2);f['cards'][0]['board_cards']=b
            self.assertEqual(candidates([sample(1),f]),[])
    def test_gap_and_changes(self):
        self.assertEqual(candidates([sample(1),sample(3)]),[])
        f=sample(2);f['seats'][0]['dealer_seat_candidate']='hero_bottom'
        self.assertEqual(candidates([sample(1),f]),[])
        self.assertEqual(candidates([sample(1),sample(2,platform='suprema')]),[])
    def test_missing_dealer_or_hero(self):
        for key in ('dealer_seat_candidate','hero_seat_candidate'):
            f=sample(2);f['seats'][0][key]=None
            self.assertEqual(candidates([sample(1),f]),[])
    def test_inconsistent_roster(self):
        f=sample(1);f['seats'][0]['opponents'][0]['seat']=f['seats'][0]['opponents'][1]['seat']
        self.assertIsNone(snapshot(f['cards'][0],f['seats'][0]));f['seats'].pop()
        with self.assertRaises(ValueError):candidates([f])
    def test_duplicate_sample(self):
        with self.assertRaises(ValueError):candidates([sample(1),sample(1)])

if __name__=='__main__':unittest.main()
