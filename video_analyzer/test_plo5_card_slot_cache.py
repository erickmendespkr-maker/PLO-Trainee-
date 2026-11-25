import unittest
from PIL import Image
from plo5_card_slot_cache import SlotCache

P={k+suffix:v for k in ('hero','board') for suffix,v in [('_x',[0,10,20,30,40]),('_y',0),('_w',8),('_rank_h',8),('_suit_h',5)]}

class SlotTests(unittest.TestCase):
    def setUp(self):
        self.calls=0;self.im=Image.new('RGB',(50,30));self.cache=SlotCache({self.im.size:P},self.reader,2)
    def reader(self,im,field,i):
        self.calls+=1;return [im.getpixel((2,2))]
    def test_reuse(self):
        self.cache.read(self.im,'hero',0);self.im.putpixel((49,29),(1,2,3));self.cache.read(self.im,'hero',0);self.assertEqual(self.calls,1)
    def test_changed_pixel(self):
        self.cache.read(self.im,'hero',0);self.im.putpixel((2,2),(1,2,3));self.assertEqual(self.cache.read(self.im,'hero',0),[(1,2,3)]);self.assertEqual(self.calls,2)
    def test_isolation(self):
        self.cache.read(self.im,'hero',0).clear();self.assertEqual(self.cache.read(self.im,'hero',0),[(0,0,0)]);self.cache.read(self.im,'board',0);self.cache.read(self.im,'hero',1);self.assertEqual(self.cache.stats()['entries'],2)
    def test_disabled(self):
        c=SlotCache({self.im.size:P},self.reader,0);c.read(self.im,'hero',0);c.read(self.im,'hero',0);self.assertEqual(self.calls,2)
    def test_invalid(self):
        for field,i in [('other',0),('hero',5),('hero',True)]:
            with self.assertRaises(ValueError):self.cache.read(self.im,field,i)

if __name__=='__main__':unittest.main()
