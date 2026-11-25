import copy
import unittest
from fractions import Fraction
from plo5_stackoff import analyze

H=['As','Ks','Qh','Jh','Tc']
V=['Ac','Ad','Kh','Kd','7c']
V2=['Ac','Ah','9s','8d','7h']
BLOCKED=['As','Ad','2c','3c','4c']


def scenario():
    return {'variant':5,'hero':H,'position':'SB','stacks':{'SB':270,'BB':180},'sb':5,'bb':10,
            'history':[{'position':'SB','action':'raise','amount':25},{'position':'BB','action':'raise','amount':80}],
            'chosen':{'action':'raise','amount':240},'range':[{'cards':V,'weight':3},{'cards':V2,'weight':1},{'cards':BLOCKED,'weight':4}],
            'range_kind':'AAxxx_at_least_two','raises':[{'amount':240,'call_bps':[10000,10000,10000]}],
            'rake_bps':500,'rake_cap':10,'rake_on_fold':False}


def run(s): return analyze(s,trials=40,seed=27)


class StackoffTests(unittest.TestCase):
    def test_four_bet_shove_return_and_rake(self):
        r=run(scenario()); a=r['actions'][-1]; st=a['settlement']
        self.assertEqual((r['raise_count_before'],r['chosen_raise_number'],r['pot_limit_payment_cap_chips']),(2,4,240))
        self.assertTrue(r['chosen_all_in']); self.assertEqual(r['initial_effective_stack_bb'],18)
        self.assertEqual(st,{'hero_payment_chips':240,'opponent_payment_chips':90,'hero_return_chips':90,'opponent_return_chips':0,'contested_pot_chips':360,'rake_chips':10,'terminal_by_stack':True})
        q=Fraction(**a['equity']['equity_fraction']);self.assertEqual(Fraction(**a['ev_fraction_bb']),(q*350-150)/10)
        self.assertEqual(r['range_audit']['blocked_weight_fraction'],.5)
        self.assertFalse(r['gto_solution']);self.assertIsNone(r['ev_loss_bb'])

    def test_short_all_in_call(self):
        s=scenario();s['stacks']['SB']=80;s['raises']=[];s['chosen']={'action':'call','amount':50}
        r=run(s);a=r['actions'][1];st=a['settlement']
        self.assertEqual(r['to_call_chips'],60);self.assertEqual(r['actual_call_payment_chips'],50)
        self.assertEqual((st['opponent_return_chips'],st['contested_pot_chips'],st['rake_chips']),(10,160,8))
        self.assertAlmostEqual(r['terminal_call_equity_required'],50/152)
        self.assertTrue(st['terminal_by_stack'])

    def test_opponent_already_all_in(self):
        s=scenario();s['stacks']['BB']=90;s['chosen']={'action':'call','amount':60};s['raises']=[]
        r=run(s);self.assertTrue(r['opponent_already_all_in']);self.assertEqual(r['actions'][1]['settlement']['contested_pot_chips'],180)
        s['raises']=[{'amount':130,'call_bps':[0,0,0]}]
        with self.assertRaises(ValueError):run(s)

    def test_short_all_in_raise(self):
        s=scenario();s['stacks']['SB']=100;s['chosen']={'action':'raise','amount':70};s['raises']=[{'amount':70,'call_bps':[10000]*3}]
        r=run(s);self.assertTrue(r['chosen_all_in']);self.assertEqual(r['min_full_raise_increment_chips'],60)
        self.assertEqual(r['actions'][-1]['settlement']['contested_pot_chips'],200)
        s['stacks']['SB']=110
        with self.assertRaises(ValueError):run(s)

    def test_fold_branch_rake_and_return(self):
        s=scenario();s['rake_on_fold']=True;s['raises'][0]['call_bps']=[0,0,10000]
        a=run(s)['actions'][-1]
        self.assertEqual(a['fold_probability_fraction'],{'numerator':1,'denominator':1});self.assertIsNone(a['equity'])
        self.assertEqual((a['fold_rake_chips'],a['fold_hero_return_chips'],a['ev_bb']),(9,180,11.1))

    def test_two_sizings_and_weighted_response(self):
        s=scenario();s['raises'].append({'amount':120,'call_bps':[5000,10000,10000]})
        r=run(s);a=r['actions'][2];self.assertEqual(a['extra_chips'],60)
        self.assertEqual(a['fold_probability_fraction'],{'numerator':3,'denominator':8})
        self.assertFalse(a['settlement']['terminal_by_stack']);self.assertFalse(r['future_betting_modeled'])
        self.assertEqual(r['comparison']['modeled_actions'],4)
        self.assertAlmostEqual(r['sampling_joint_coverage_lower_bound'],.85)

    def test_unmodeled_sizing(self):
        s=scenario();s['raises']=[];r=run(s)
        self.assertEqual(r['comparison']['status'],'NO_MATCH');self.assertIsNone(r['comparison']['conditional_ev_loss_bb'])

    def test_invalid_history_and_raise(self):
        for change in ('order','overpot','underraise','completed','short_call','variant','multiway','bad_range','bad_weight','bad_response'):
            s=scenario()
            if change=='order':s['history'].reverse()
            elif change=='overpot':s['stacks']['SB']=300;s['chosen']['amount']=241
            elif change=='underraise':s['chosen']['amount']=119
            elif change=='completed':s['history'].append({'position':'SB','action':'call','amount':60})
            elif change=='short_call':s['chosen']={'action':'call','amount':59}
            elif change=='variant':s['variant']=6
            elif change=='multiway':s['stacks']['BTN']=100
            elif change=='bad_range':s['range'][0]['cards']=['2s','3s','4s','5s','6s']
            elif change=='bad_weight':s['range'][0]['weight']=100001
            else:s['raises'][0]['call_bps']=[10000]
            with self.subTest(change=change),self.assertRaises(ValueError):run(s)

    def test_short_raise_from_opponent_not_reopened(self):
        s=scenario();s['stacks']['BB']=45;s['history'][1]['amount']=35;s['chosen']={'action':'call','amount':15};s['raises']=[]
        r=run(s);self.assertTrue(r['opponent_already_all_in']);self.assertEqual(r['min_full_raise_increment_chips'],20)
        self.assertEqual(r['actions'][1]['settlement']['contested_pot_chips'],90)
        s['chosen']={'action':'raise','amount':40}
        with self.assertRaises(ValueError):run(s)

    def test_legacy_compatible_matched_sizings(self):
        from plo5_action_ev import analyze as legacy
        s=scenario();s['stacks']={'SB':1000,'BB':1000};s['chosen']['amount']=120
        s['raises']=[{'amount':120,'call_bps':[5000,10000,10000]}, {'amount':240,'call_bps':[10000]*3}]
        old={'variant':5,'hero':H,'board':[],'range':s['range'],'pot':120,'hero_street':30,
             'opponent_street':90,'hero_stack':970,'opponent_stack':910,'bb':10,'min_increment':60,
             'rake_bps':500,'rake_cap':10,'rake_on_fold':False,
             'aggressions':[{'extra':a['amount']-60,'call_bps':a['call_bps']} for a in s['raises']]}
        a=run(s); b=legacy(old,trials=40,seed=27)
        self.assertEqual([x['ev_fraction_bb'] for x in a['actions']],[x['ev_fraction_bb'] for x in b['actions']])
        self.assertFalse(a['chosen_all_in']);self.assertEqual(a['chosen_raise_number'],4)

    def test_facing_four_bet_all_in_short_call(self):
        s=scenario();s['position']='BB';s['history'].append({'position':'SB','action':'raise','amount':240})
        s['chosen']={'action':'call','amount':90};s['raises']=[]
        r=run(s);st=r['actions'][1]['settlement']
        self.assertEqual(r['raise_count_before'],3);self.assertTrue(r['opponent_already_all_in'])
        self.assertTrue(r['chosen_all_in']);self.assertEqual((st['opponent_return_chips'],st['contested_pot_chips']),(90,360))

    def test_determinism_and_model_only(self):
        s=scenario();a=run(s);self.assertEqual(a,run(copy.deepcopy(s)))
        self.assertFalse(a['video_verified']);self.assertIsNone(a['frequency']);self.assertIsNone(a['financial_result_bb'])
        self.assertFalse(a['comparison']['full_action_space_covered'])


if __name__=='__main__':unittest.main()
