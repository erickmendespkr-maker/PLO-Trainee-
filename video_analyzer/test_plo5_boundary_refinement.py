import unittest
from plo5_boundary_refinement import refine

class RefineTests(unittest.TestCase):
    def test_narrow(self):
        r=refine([(0,'a'),('1/4','a'),('1/2',None),('3/4','b'),(1,'b')],'a','b',4)
        self.assertEqual(r['width_seconds'],.5);self.assertFalse(r['boundary_verified'])
    def test_gap(self):
        self.assertIsNone(refine([(0,'a'),(1,'a'),('5/4','b'),('3/2','b')],'a','b',4)['width_seconds'])
    def test_reversal(self):
        self.assertIsNone(refine([(0,'a'),('1/4','a'),('1/2','b'),('3/4','b'),(1,'a'),('5/4','a')],'a','b',4)['width_seconds'])
    def test_single(self):
        self.assertIsNone(refine([(0,'a'),('1/4','b'),('1/2','b')],'a','b',4)['width_seconds'])
    def test_gap_between_supported_endpoints(self):
        self.assertIsNone(refine([(0,'a'),('1/4','a'),(1,'b'),('5/4','b')],'a','b',4)['width_seconds'])
    def test_single_reversal(self):
        self.assertIsNone(refine([(0,'a'),('1/4','a'),('1/2','b'),('3/4','a'),(1,'b'),('5/4','b')],'a','b',4)['width_seconds'])
    def test_duplicate(self):
        with self.assertRaises(ValueError):refine([(0,'a'),(0,'b')],'a','b',4)
if __name__=='__main__':unittest.main()
