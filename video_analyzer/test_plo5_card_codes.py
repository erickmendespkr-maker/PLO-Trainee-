import unittest
from PIL import Image,ImageDraw
from plo5_visual_codes import Codebook
from plo5_card_codes import label_slot,read_slot


class CardCodeTests(unittest.TestCase):
    def setUp(self):
        self.r=Image.new('RGB',(15,17),'white');self.s=Image.new('RGB',(13,12),'white')
        ImageDraw.Draw(self.r).text((1,1),'7',fill='black');ImageDraw.Draw(self.s).rectangle((2,2,5,7),fill='black')
        self.rows=label_slot('p','hero',self.r,self.s,'7s')
    def test_exact_two_regions(self):
        b=Codebook(self.rows);r=read_slot(b,'p','hero',self.r,self.s)
        self.assertEqual(r['card'],'7s');self.assertEqual(r['status'],'candidate_unverified')
        self.assertIsNone(read_slot(b,'p','board',self.r,self.s))
        self.assertIsNone(read_slot(b,'z','hero',self.r,self.s))
        self.assertIsNone(read_slot(b,'p','hero',self.r,self.s,guard=False))
        self.s.putpixel((0,0),(0,0,0));self.assertIsNone(read_slot(b,'p','hero',self.r,self.s))
    def test_conflicts_and_invalid_labels(self):
        for rows in (self.rows+[dict(self.rows[0],label='8s')], [self.rows[0],dict(self.rows[1],label='h')],[dict(self.rows[0],label='invalid'),self.rows[1]]):
            r=read_slot(Codebook(rows),'p','hero',self.r,self.s)
            self.assertIsNone(r['card']);self.assertEqual(r['source'],'VISUAL_CODE_CONFLICT')
        with self.assertRaises(ValueError):label_slot('p','hero',self.r,self.s,'1s')
    def test_partial_bank_never_guesses(self):
        self.assertIsNone(read_slot(Codebook(self.rows[:1]),'p','hero',self.r,self.s))
        self.assertIsNone(read_slot(Codebook(self.rows[1:]),'p','hero',self.r,self.s))

if __name__=='__main__':unittest.main()
