import copy
import unittest
from offline_ev_monetary_binding import bind_monetary_assumptions, audit_monetary_binding

class MonetaryBindingTests(unittest.TestCase):
    def setUp(self):
        self.args = dict(pot_before_call=100, call_cost=40, rake=2)
        self.bound = bind_monetary_assumptions(**self.args)
    def test_reproducible(self):
        self.assertEqual(self.bound, bind_monetary_assumptions(**self.args))
    def test_audit(self):
        self.assertTrue(audit_monetary_binding(self.bound, **self.args)['monetary_assumptions_integrity_verified'])
    def test_modified_call(self):
        with self.assertRaises(ValueError):
            audit_monetary_binding(self.bound, pot_before_call=100, call_cost=41, rake=2)
    def test_modified_rake(self):
        with self.assertRaises(ValueError):
            audit_monetary_binding(self.bound, pot_before_call=100, call_cost=40, rake=3)
    def test_modified_hash(self):
        b = copy.deepcopy(self.bound); b['sha256'] = '0'*64
        with self.assertRaises(ValueError): audit_monetary_binding(b, **self.args)
    def test_modified_record(self):
        b = copy.deepcopy(self.bound); b['assumptions']['call_cost'] = 41
        with self.assertRaises(ValueError): audit_monetary_binding(b, **self.args)
    def test_reject_bool_nan(self):
        for bad in (True, float('nan'), float('inf')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bind_monetary_assumptions(pot_before_call=bad, call_cost=10)
    def test_invalid_bounds(self):
        for args in (dict(pot_before_call=-1, call_cost=2), dict(pot_before_call=2, call_cost=0), dict(pot_before_call=2, call_cost=1, rake=4)):
            with self.subTest(args=args), self.assertRaises(ValueError): bind_monetary_assumptions(**args)
    def test_unit_mismatch(self):
        with self.assertRaises(ValueError): audit_monetary_binding(self.bound, **self.args, currency_unit='bb')
    def test_reject_unit(self):
        with self.assertRaises(ValueError): bind_monetary_assumptions(**self.args, currency_unit='USD')
if __name__ == '__main__': unittest.main()
