import copy
import unittest
from plo5_ev_comparison import compare
from test_plo5_action_ev import scenario


def action(kind,extra=0):
    return {'action':kind,'extra_chips':extra}


class ComparisonTests(unittest.TestCase):
    def test_exact_tie(self):
        r=compare({'base':scenario()},action('call'))
        a=r['scenarios']['base']
        self.assertEqual(a['status'],'BEST_OR_TIED_UNDER_BOUNDS')
        self.assertEqual(a['conditional_ev_loss_fraction_bb'],{'numerator':0,'denominator':1})
        self.assertEqual(a['point_best_actions'],[action('call'),action('raise',40)])
        self.assertEqual(a['loss_bounds_bb'],[0,0])
        self.assertEqual(r['sampling_interval_joint_coverage_lower_bound'],1)

    def test_inferior_fold_exact(self):
        r=compare({'base':scenario()},action('fold'))
        a=r['scenarios']['base']
        self.assertEqual(a['status'],'INFERIOR_UNDER_BOUNDS')
        self.assertEqual(a['conditional_ev_loss_fraction_bb'],{'numerator':41,'denominator':8})
        self.assertEqual(a['loss_bounds_bb'],[5.125,5.125])
        self.assertIsNone(r['financial_result_bb']);self.assertIsNone(r['variance_attribution'])
        self.assertIsNone(r['ev_loss_bb']);self.assertFalse(r['strategic_error_established'])

    def test_exact_sizing_no_match(self):
        r=compare({'base':scenario()},action('raise',41))
        self.assertEqual(r['scenarios']['base']['status'],'NO_MATCH')
        self.assertEqual(r['coverage']['no_match'],1)
        self.assertEqual(r['coverage']['hypotheses_comparable'],0)
        self.assertIsNone(r['conditional_loss_bounds_span_bb'])

    def test_no_alternative(self):
        s=scenario();s.update(hero_street=0,opponent_street=0,aggressions=[])
        r=compare({'base':s},action('check'))
        self.assertEqual(r['scenarios']['base']['status'],'INSUFFICIENT_DATA')
        self.assertEqual(r['coverage']['insufficient_data'],1)

    def test_sensitivity_response_hypotheses(self):
        a=scenario();b=copy.deepcopy(a);b['aggressions'][0]['call_bps']=[0,0,0]
        r=compare({'tie':a,'fold_all':b},action('call'))
        self.assertEqual(r['conditional_loss_bounds_span_bb'],[0,4.875])
        self.assertEqual(r['scenarios']['fold_all']['point_best_actions'],[action('raise',40)])
        self.assertFalse(r['span_is_calibrated_confidence_interval'])
        self.assertEqual(r['coverage']['hypotheses_comparable'],2)

    def test_context_mismatch(self):
        for key,val in [('pot',101),('bb',20),('rake_cap',11),('hero_stack',301),('min_increment',21)]:
            a=scenario();b=copy.deepcopy(a);b[key]=val
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Incompatible'):
                compare({'a':a,'b':b},action('call'))
        a=scenario();b=copy.deepcopy(a);b['aggressions'][0]['extra']=50
        with self.assertRaisesRegex(ValueError,'Incompatible'):compare({'a':a,'b':b},action('call'))

    def test_monte_carlo_uncertainty(self):
        r=compare({'base':scenario()},action('call'),method='monte_carlo',trials=20,seed=1)
        a=r['scenarios']['base']
        self.assertEqual(a['status'],'UNCERTAIN_UNDER_BOUNDS')
        self.assertEqual(a['loss_bounds_bb'][0],0)
        self.assertGreater(a['loss_bounds_bb'][1],0)
        self.assertEqual(r['stochastic_action_intervals'],2)
        self.assertAlmostEqual(r['sampling_interval_joint_coverage_lower_bound'],.9)
        self.assertFalse(r['range_or_response_uncertainty_included'])

    def test_two_sizings_are_distinct(self):
        s=scenario();s['aggressions'].append({'extra':60,'call_bps':[0,0,0]})
        r=compare({'base':s},action('raise',40))['scenarios']['base']
        self.assertEqual(r['point_best_actions'],[action('raise',60)])
        self.assertEqual(r['conditional_ev_loss_bb'],4.875)
        self.assertEqual(r['modeled_actions'],4)
        self.assertFalse(r['full_action_space_covered'])

    def test_invalid_actions_and_variants(self):
        for a in (action('raise'),action('call',1),action('fold',True),action('all-in'),action('bet',-1)):
            with self.assertRaises(ValueError):compare({'base':scenario()},a)
        s=scenario();s['variant']=6
        with self.assertRaises(ValueError):compare({'base':s},action('call'))
        with self.assertRaises(ValueError):compare({},action('call'))


if __name__=='__main__':unittest.main()
