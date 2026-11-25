import unittest
from plo5_external_check import cases, compare, checked


class ExternalCheckTests(unittest.TestCase):
    def test_cases(self):
        a=list(cases(12));self.assertEqual(a,list(cases(12)))
        for row in a:
            cards=row['board']+[c for h in row['hands'] for c in h]
            self.assertEqual(len(cards),len(set(cards)))
            self.assertTrue(all(len(h)==5 for h in row['hands']))
    def test_agreement_and_tie_order(self):
        rows=list(cases(2));r=compare(rows,lambda x:[[0,1],[1]],lambda x:[[1,0],[1]])
        self.assertTrue(r['winner_agreement']);self.assertFalse(r['production_backend_changed'])
    def test_disagreement(self):
        rows=list(cases(2));r=compare(rows,lambda x:[[0],[0]],lambda x:[[0],[1]])
        self.assertEqual(r['mismatches'],[1]);self.assertFalse(r['winner_agreement'])
    def test_invalid(self):
        rows=list(cases(1))
        for bad in ([],[[]],[[0,0]],[[2]],[[True]],['0']):
            with self.assertRaises(ValueError):checked(rows,bad)
    def test_case_limit(self):
        for n in (0,4097,True):
            with self.assertRaises(ValueError):list(cases(n))

if __name__=='__main__':unittest.main()
