import unittest
from unittest.mock import patch
from PIL import Image
from plo5_recognition_cache import ExactReader


class CacheTests(unittest.TestCase):
    def test_exact_roi_reuse_and_isolation(self):
        r=ExactReader(8);a=Image.new('RGB',(402,748));b=a.copy();b.putpixel((0,0),(1,2,3))
        with patch('plo5_recognition_cache.read_money',return_value={'candidate':{'value':'1'}}) as read:
            x=r.read(a,'pot');x['candidate']['value']='bad';self.assertEqual(r.read(b,'pot')['candidate']['value'],'1');self.assertEqual(read.call_count,1)
            b.putpixel((168,249),(1,2,3));r.read(b,'pot');self.assertEqual(read.call_count,2)
        self.assertEqual(r.stats()['hits'],1)

    def test_fields_layout_and_bound(self):
        r=ExactReader(1);a=Image.new('RGB',(402,748));b=Image.new('RGB',(432,800))
        with patch('plo5_recognition_cache.read_money',return_value={}) as money,patch('plo5_recognition_cache.read_gold_stack',return_value={}) as gold:
            r.read(a,'pot');r.read(a,'stack');r.read(b,'pot');r.read(a,'pot');self.assertEqual(money.call_count,3);self.assertEqual(gold.call_count,1)
        self.assertEqual(r.stats()['entries'],1)

    def test_disabled_and_blank(self):
        r=ExactReader(0);a=Image.new('RGB',(402,748))
        with patch('plo5_recognition_cache.read_action',return_value=None) as action:
            r.read(a,'action');r.read(a,'action');self.assertEqual(action.call_count,2)
        self.assertIsNone(r.scan(a)['pot']);self.assertEqual(r.stats()['entries'],0)
        with self.assertRaises(ValueError):r.read(a,'other')
        with self.assertRaises(ValueError):ExactReader(-1)

    def test_failed_reader_not_cached(self):
        r=ExactReader();a=Image.new('RGB',(402,748))
        with patch('plo5_recognition_cache.read_money',side_effect=[RuntimeError('failed'),{}]) as money:
            with self.assertRaises(RuntimeError):r.read(a,'pot')
            self.assertEqual(r.read(a,'pot'),{});self.assertEqual(money.call_count,2)

if __name__=='__main__':unittest.main()
