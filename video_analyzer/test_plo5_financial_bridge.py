import unittest
from decimal import Decimal
from plo5_financial_bridge import terminal_accounting, display_balance


class FinancialBridgeTests(unittest.TestCase):
    def setUp(self):
        self.b=dict(A=100,B=200,C=250,D=500)
        self.c=dict(A=100,B=200,C=250,D=100)
        self.f=dict(A=False,B=False,C=False,D=True)
        self.a=dict(A=390,B=190,C=150,D=400)
        self.e=dict(A=0,B=0,C=100,D=0)

    def run_case(self, rake=20):
        return terminal_accounting(self.b,self.c,self.f,self.a,self.e,rake=rake)

    def test_side_pots_rebuy_return_rake(self):
        r=self.run_case();self.assertEqual(r['status'],'CONDITIONAL_AGGREGATE_ACCOUNTING')
        self.assertEqual(r['returned']['C'],50);self.assertEqual(r['gross'],600)
        self.assertEqual(r['aggregate_awards'],dict(A=390,B=190,C=0,D=0))
        self.assertEqual(r['conditional_net']['C'],-200)
        self.assertEqual(sum(r['conditional_net'].values()),-20)
        self.assertFalse(r['financial_result_verified'])

    def test_unknown_transfer(self):
        self.e['C']=None;r=self.run_case();self.assertEqual(r['status'],'MISSING_BALANCE_OR_TRANSFER');self.assertIsNone(r['conditional_net'])

    def test_unknown_balance(self):
        self.a['A']=None;self.assertEqual(self.run_case()['status'],'MISSING_BALANCE_OR_TRANSFER')

    def test_unknown_rake(self):
        r=self.run_case(None);self.assertEqual(r['status'],'RAKE_UNDECLARED');self.assertEqual(r['rake_residual'],20);self.assertIsNone(r['aggregate_awards'])

    def test_impossible_side_pot(self):
        self.a['A']=580;self.a['B']=0;self.assertEqual(self.run_case()['status'],'SIDE_POT_ELIGIBILITY_CONFLICT')

    def test_folded_award(self):
        self.a['D']+=10;self.a['A']-=10;self.assertEqual(self.run_case()['status'],'BALANCE_CONFLICT')

    def test_wrong_rake(self):
        self.assertEqual(self.run_case(19)['status'],'BALANCE_CONFLICT')

    def test_unknown_roster(self):
        del self.a['C'];self.assertRaises(ValueError,self.run_case)

    def test_bool_chips(self):
        self.c['A']=True;self.assertRaises(ValueError,self.run_case)

    def test_display_total(self):
        d=Decimal;self.assertEqual(display_balance({'A':d('10.1')},{'A':d('12.2')},d('2.1'),d('0'))['residual_bb'],[0,1])
        self.assertEqual(display_balance({'A':d('10')},{'A':d('12')},d('3'),d('0'))['residual_bb'],[-1,1])
        self.assertIsNone(display_balance({'A':None},{'A':d('12')},d('3'),d('0'))['residual_bb'])

    def test_single_fold_winner(self):
        r=terminal_accounting(dict(A=100,B=100),dict(A=40,B=10),dict(A=False,B=True),dict(A=110,B=90),dict(A=0,B=0),rake=0)
        self.assertEqual(r['aggregate_awards'],dict(A=20,B=0));self.assertEqual(r['returned']['A'],30)

if __name__=='__main__':unittest.main()
