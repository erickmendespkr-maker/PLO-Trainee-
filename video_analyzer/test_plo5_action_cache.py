import unittest
from hashlib import sha256
from PIL import Image,ImageDraw
from plo5_action_cache import ActionCache


class ActionCacheTests(unittest.TestCase):
    def test_rebind_and_invalidation(self):
        im=Image.new('RGB',(40,20));d=ImageDraw.Draw(im);d.rectangle((1,1,3,3),fill='white');d.rectangle((21,1,23,3),fill='white')
        calls=[]
        def read(image,rect,threshold):
            calls.append((rect,threshold));x,y,w,h=rect
            return dict(roi=rect,roi_rgb_sha256=sha256(image.crop((x,y,x+w,y+h)).tobytes()).hexdigest(),candidate=None,status='uncertain_label',human_confirmed=False)
        c=ActionCache(read)
        a=c.read(im,[0,0,10,10],.75);b=c.read(im,[20,0,10,10],.75)
        self.assertEqual(len(calls),1);self.assertEqual(b['roi'],[20,0,10,10]);self.assertEqual(a['visual_code'],b['visual_code'])
        c.read(im,[20,0,10,10],.85);self.assertEqual(len(calls),2)
        im.putpixel((20,0),(1,0,0));c.read(im,[20,0,10,10],.75);self.assertEqual(len(calls),3)
        self.assertEqual(c.stats()['hits'],1)
    def test_invalid_roi_and_bad_decoder(self):
        c=ActionCache(lambda *a:dict(roi_rgb_sha256='0'*64));im=Image.new('RGB',(10,10))
        with self.assertRaises(ValueError):c.read(im,[0,0,20,20],.75)
        with self.assertRaises(ValueError):c.read(im,[0,0,2,2],float('nan'))
        with self.assertRaises(ValueError):c.read(im,[0,0,2,2],.75)

if __name__=='__main__':unittest.main()
