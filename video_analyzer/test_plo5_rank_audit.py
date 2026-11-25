import unittest
from plo5_rank_audit import oracle,signatures,audit_signatures,audit_omaha
from plo5_rank_cache import fast_five
from plo5_evaluator import evaluate,showdown

class AuditTests(unittest.TestCase):
    def test_categories(self):
        examples=['As Kd Jh 8c 2s','As Ad Kh 8c 2s','As Ad Kh Kc 2s','As Ad Ah Kc 2s','As 2d 3h 4c 5s','As Ks Js 8s 2s','As Ad Ah Kc Ks','As Ad Ah Ac Ks','As 2s 3s 4s 5s']
        self.assertEqual([oracle(x.split())[0] for x in examples],list(range(9)))
    def test_wheel(self):self.assertEqual(oracle('As 2s 3s 4s 5s'.split()),(8,5))
    def test_coverage(self):
        r=audit_signatures(fast_five);self.assertTrue(r['agreement']);self.assertEqual(r['rank_signatures'],7462);self.assertEqual(r['physical_combinations_represented'],2598960)
    def test_mutation(self):
        r=audit_signatures(lambda h:(0,));self.assertFalse(r['agreement']);self.assertEqual(len(r['mismatches']),7462)
    def test_omaha(self):
        r=audit_omaha(evaluate,showdown,32);self.assertTrue(r['agreement']);self.assertEqual(r['street_checks'],3*r['holdings'])
    def test_limit(self):
        with self.assertRaises(ValueError):audit_omaha(evaluate,showdown,0)

if __name__=='__main__':unittest.main()
