import unittest
from fractions import Fraction
from PIL import Image
from plo5_visual_continuity import continuity_flags, continuity_chain_flags, seat_ocr_key


class VisualContinuityTests(unittest.TestCase):
    def setUp(self):
        self.old = dict(pts='0', platform='pppoker', profile='p', button='top', holding=['As','Ks','Qh','Jd','Tc'])

    def flags(self, **changes):
        return continuity_flags(self.old, dict(self.old, pts='1', **changes) if 'pts' not in changes else dict(self.old, **changes), Fraction(2))

    def test_missing_dealer_is_not_conflict(self):
        self.assertEqual(self.flags(button=None), ())
        self.assertEqual(self.flags(button='hero_bottom'), ('DEALER_CONFLICT',))

    def test_gap_and_positive_conflicts(self):
        self.assertEqual(self.flags(pts='3', platform='suprema', profile='q', button='hero_bottom', holding=['2s']), ('PTS_GAP','PLATFORM_CHANGE','PROFILE_CHANGE','DEALER_CONFLICT','HOLDING_CONFLICT'))
        self.assertEqual(self.flags(pts='0'), ('PTS_GAP',))
        self.assertEqual(self.flags(pts='2'), ())

    def test_missing_holding_is_not_positive_conflict(self):
        self.assertEqual(self.flags(holding=None), ())
        self.assertEqual(self.flags(holding=['2s']), ('HOLDING_CONFLICT',))

    def test_partial_chain_preserves_temporal_continuity(self):
        partial=dict(self.old,pts='1',profile=None,button=None,holding=None)
        restored=dict(self.old,pts='3')
        self.assertEqual(continuity_chain_flags(self.old,partial,restored,Fraction(2)),())
        self.assertEqual(continuity_chain_flags(self.old,partial,dict(restored,pts='4'),Fraction(2)),('PTS_GAP',))

    def test_partial_chain_rejects_identity_conflicts(self):
        partial=dict(self.old,pts='1',profile=None,button=None,holding=None)
        for field,value,flag in [('button','hero_bottom','DEALER_CONFLICT'),('holding',['2s'],'HOLDING_CONFLICT'),('profile','q','PROFILE_CHANGE')]:
            bad=dict(self.old,pts='2',**{field:value})
            self.assertEqual(continuity_chain_flags(self.old,partial,bad,Fraction(2)),(flag,))
        self.assertEqual(continuity_flags(partial,dict(self.old,pts='2'),Fraction(2)),())

    def test_effective_input_key(self):
        a=Image.new('RGB',(20,12),'black');b=a.copy();b.putpixel((0,0),(255,255,255))
        key=lambda x:seat_ocr_key(x,'pppoker','stack',effective_gray=True)
        self.assertEqual(key(a),key(b))
        self.assertNotEqual(seat_ocr_key(a,'pppoker','stack'),seat_ocr_key(b,'pppoker','stack'))
        b.putpixel((5,5),(255,255,255));self.assertNotEqual(key(a),key(b))

    def test_low_contrast_equivalence(self):
        a=Image.new('RGB',(20,12),(40,40,40));b=Image.new('RGB',(20,12),(200,200,200))
        k=lambda x:seat_ocr_key(x,'pppoker','stack',effective_gray=True)
        b.putpixel((5,5),(214,214,214));self.assertEqual(k(a),k(b))
        b.putpixel((5,5),(215,215,215));self.assertNotEqual(k(a),k(b))

    def test_scope_and_gray_parity(self):
        a=Image.new('RGB',(20,12),(255,0,0));b=Image.new('RGB',(20,12),(76,76,76))
        k=lambda x,p='pppoker',f='stack':seat_ocr_key(x,p,f,effective_gray=True)
        self.assertEqual(k(a),k(b));self.assertNotEqual(k(a),k(b,'suprema'));self.assertNotEqual(k(a),k(b,f='action'))
        self.assertNotEqual(k(a),seat_ocr_key(a,'pppoker','stack'))


if __name__=='__main__':unittest.main()
