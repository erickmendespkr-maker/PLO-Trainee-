import copy
import json
import tempfile
import unittest
from pathlib import Path

from plo5_preflop_context import analyze, main
from strategic_normalize import POSITIONS

H=['As','Ks','Qh','Jh','Tc']
V=['Ac','Ad','Kh','Kd','7c']


def event(position,action,amount=0):
    return {'position':position,'action':action,'amount':amount}


def scenario(n=6,hero='UTG',history=None,action='raise',amount=35):
    return {'variant':5,'hero':H,'position':hero,'stacks':{p:1000 for p in POSITIONS[n]},
            'sb':5,'bb':10,'history':history or [],'chosen':{'action':action,'amount':amount},
            'rake_bps':500,'rake_cap':10,'rake_on_fold':False,'hypotheses':{}}


class PreflopTests(unittest.TestCase):
    def test_rfi_all_positions_before_bb(self):
        for n,order in POSITIONS.items():
            for i,p in enumerate(order[:-1]):
                s=scenario(n,p,[event(x,'fold') for x in order[:i]],amount=25 if p=='SB' else 35)
                r=analyze(s)
                self.assertEqual((r['spot'],r['chosen_class']),('unopened','rfi'))
                self.assertTrue(r['rfi_opportunity']);self.assertEqual(r['pending_after_hero'],list(order[i+1:]))
                self.assertEqual(r['pot_chips'],15);self.assertEqual(r['to_call_chips'],5 if p=='SB' else 10)
                self.assertEqual(r['hand_structure']['straight_capable_pairs'],10)
                self.assertIsNone(r['frequency']);self.assertIsNone(r['ev_bb']);self.assertFalse(r['gto_solution'])

    def test_bb_defense_pot_odds_and_stacks(self):
        s=scenario(6,'BB',[event('UTG','raise',35)]+[event(p,'fold') for p in ('MP','CO','BTN','SB')],action='call',amount=25)
        s['stacks']['UTG']=600
        r=analyze(s)
        self.assertEqual((r['spot'],r['chosen_class']),('facing_open','blind_call'))
        self.assertTrue(r['blind_defense_context']);self.assertEqual(r['pot_chips'],50)
        self.assertEqual(r['to_call_chips'],25);self.assertEqual(r['pot_limit_payment_cap_chips'],100)
        self.assertEqual(r['effective_initial_stack_bb'],{'UTG':60.0});self.assertEqual(r['effective_remaining_stack_bb'],{'UTG':56.5})
        self.assertAlmostEqual(r['pot_odds_without_rake'],1/3);self.assertAlmostEqual(r['terminal_call_equity_with_rake'],25/72)
        self.assertEqual(r['opponents_hero_has_postflop_position_on'],[])

    def test_cold_call_and_squeeze(self):
        history=[event('UTG','raise',35),event('MP','call',35)]
        r=analyze(scenario(6,'CO',history,amount=110))
        self.assertEqual(r['chosen_class'],'squeeze');self.assertEqual(r['callers_since_last_raise'],['MP'])
        self.assertEqual(r['pot_chips'],85);self.assertEqual(r['pot_limit_payment_cap_chips'],155)
        self.assertEqual(analyze(scenario(6,'CO',history,action='call',amount=35))['chosen_class'],'cold_call')

    def test_three_bet_and_facing_three_bet(self):
        r=analyze(scenario(6,'MP',[event('UTG','raise',35)],amount=100))
        self.assertEqual(r['chosen_class'],'three_bet')
        h=[event('UTG','raise',35),event('MP','raise',100)]+[event(p,'fold') for p in ('CO','BTN','SB','BB')]
        r=analyze(scenario(6,'UTG',h,action='call',amount=65))
        self.assertEqual((r['spot'],r['chosen_class']),('facing_3bet','call_after_prior_action'))
        self.assertFalse(r['first_hero_action']);self.assertEqual(r['min_full_raise_increment_chips'],65)

    def test_limp_isolation_and_bb_option(self):
        h=[event('UTG','call',10)]
        r=analyze(scenario(6,'MP',h,amount=35));self.assertEqual(r['chosen_class'],'isolation_raise');self.assertFalse(r['rfi_opportunity'])
        h=[event('BTN','call',10),event('SB','call',5)]
        r=analyze(scenario(3,'BB',h,action='check',amount=0));self.assertEqual(r['spot'],'bb_option');self.assertFalse(r['rfi_opportunity'])
        self.assertEqual(analyze(scenario(3,'BB',h,amount=30))['chosen_class'],'isolation_raise')

    def test_heads_up_position_and_rake(self):
        s=scenario(2,'SB',action='call',amount=5);r=analyze(s)
        self.assertEqual(r['chosen_class'],'limp');self.assertEqual(r['opponents_hero_has_postflop_position_on'],['BB'])
        self.assertEqual(r['pot_odds_without_rake'],.25);self.assertAlmostEqual(r['terminal_call_equity_with_rake'],5/19)
        s['rake_cap']=0;self.assertEqual(analyze(s)['terminal_call_equity_with_rake'],.25)

    def test_incompatible_history_and_action(self):
        for s in (scenario(6,'MP',[]),scenario(6,'UTG',[event('MP','fold')]),scenario(amount=36),scenario(amount=19),scenario(action='check',amount=0),scenario(action='call',amount=9),scenario(action='fold',amount=1)):
            with self.subTest(s=s),self.assertRaises(ValueError):analyze(s)
        s=scenario(2,'BB',[event('SB','fold')],action='check',amount=0)
        with self.assertRaises(ValueError):analyze(s)
        s=scenario(2,'SB',[event('SB','call',5),event('BB','check')],action='check',amount=0)
        with self.assertRaises(ValueError):analyze(s)

    def test_reject_all_in_and_wrong_variant(self):
        for change in ('variant','hero','stack','blind','allin','prior_allin'):
            s=scenario()
            if change=='variant':s['variant']=6
            elif change=='hero':s['hero']=H+['2c']
            elif change=='stack':s['stacks']['UTG']=True
            elif change=='blind':s['stacks']['BB']=10
            elif change=='allin':s['stacks']['UTG']=35
            else:s['stacks']['UTG']=35;s['position']='MP';s['history']=[event('UTG','raise',35)]
            with self.subTest(change=change),self.assertRaises(ValueError):analyze(s)

    def test_conditional_model_exact_context(self):
        s=scenario(2,'SB',action='call',amount=5)
        model={'variant':5,'hero':H,'board':[],'range':[{'cards':V,'weight':1}],
               'pot':15,'hero_street':5,'opponent_street':10,'hero_stack':995,'opponent_stack':990,
               'bb':10,'min_increment':10,'rake_bps':500,'rake_cap':10,'rake_on_fold':False,
               'aggressions':[{'extra':20,'call_bps':[0]}]}
        s['hypotheses']={'assumed':model}
        r=analyze(s,trials=20,seed=7)
        self.assertEqual(r['model_status'],'CONDITIONAL_MODEL_ONLY');self.assertFalse(r['conditional_model']['gto_solution'])
        self.assertIsNone(r['ev_loss_bb']);self.assertIsNone(r['financial_result_bb'])
        for k,v in [('pot',16),('hero_street',4),('opponent_stack',989),('rake_cap',11),('min_increment',11),('board',['2c','3d','4h'])]:
            b=copy.deepcopy(s);b['hypotheses']['assumed'][k]=v
            with self.subTest(key=k),self.assertRaisesRegex(ValueError,'context mismatch'):analyze(b,trials=10)
        s['chosen']={'action':'raise','amount':20}
        self.assertEqual(analyze(s,trials=10)['model_status'],'NO_MATCH')

    def test_multiway_not_extrapolated(self):
        s=scenario();s['hypotheses']={'unsupported':{}}
        r=analyze(s);self.assertIsNone(r['conditional_model']);self.assertEqual(r['model_status'],'UNSUPPORTED_MULTIPLAYER_CONTEXT')

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'in.json';q=Path(tmp)/'out.json';p.write_text(json.dumps(scenario()))
            self.assertEqual(main([str(p),str(q)]),0)
            self.assertEqual(json.loads(q.read_text())['chosen_class'],'rfi')
            with self.assertRaises(ValueError):main([str(p),str(q)])


if __name__=='__main__':unittest.main()
