import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image,ImageChops
from plo5_fourcolor_cards import RANKS,distance
from plo5_mixed_cards_v2 import MixedCardReader,augment
from plo5_seat_evidence import ActionBank,action_patch,SeatReader,summarize,SEATS

class MixedVisualTests(unittest.TestCase):
    def test_distance_identity(self):
        import random
        r=random.Random(17)
        for _ in range(20):
            a=bytes(r.randrange(256) for _ in range(480));b=bytes(r.randrange(256) for _ in range(480))
            x,y=[Image.frombytes('L',(20,24),z) for z in (a,b)]
            delta=sum(i*n for i,n in enumerate(ImageChops.difference(x,y).histogram()))
            self.assertEqual(distance(a,b),delta/max(255,(sum(a)+sum(b)+delta)//2))
    def test_banks_and_inactive_layout(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bank.json';p.write_text(json.dumps({r:[['00'*480,1.,'hero']] for r in RANKS}))
            rr=MixedCardReader(p,p,seat_reader=SeatReader(decoder=lambda *x:None))
            rows=rr.scan(Image.new('RGB',(1504,696)))
            self.assertEqual(len(rows),4);self.assertTrue(all(x['hero_cards'] is None and x['seat_evidence']['seats']==[] for x in rows));self.assertIn('seat_cache',rr.stats())
            with self.assertRaises(ValueError):MixedCardReader()
            with self.assertRaises(ValueError):rr.scan(Image.new('RGB',(100,100)))
    def test_action_bank_conflict_and_unknown(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'action.json';a=Image.new('RGB',(44,15),'black');b=Image.new('RGB',(44,15),'white');c=Image.new('RGB',(44,15),'red')
            def entry(label,im):return [label,action_patch(im).tobytes().hex()]
            p.write_text(json.dumps({'pppoker':[entry('fold',a),entry('call',b)]}));bank=ActionBank(p)
            self.assertEqual(bank.match(a,'pppoker')['candidate'],'fold');self.assertIsNone(bank.match(c,'pppoker')['candidate']);self.assertIsNone(bank.match(a,'suprema')['candidate'])
            p.write_text(json.dumps({'pppoker':[entry('fold',a),entry('call',a)]}));self.assertIsNone(ActionBank(p).match(a,'pppoker')['candidate'])
    def test_repeated_observations_not_actions(self):
        row=dict(table_id=1,platform='pppoker',seat_evidence=dict(table_id=1,platform='pppoker',dealer={'seat':'top'},positions_verified=False,actions_verified=False,financial_result_verified=False,seats=[dict(seat=s,stack={'candidate':'100'},action={'candidate':'call'}) for s in SEATS]))
        r=summarize([dict(pts=str(i),cards=[row]) for i in range(3)])
        self.assertEqual(r['stack_candidates'],18);self.assertEqual(r['label_candidates'],18);self.assertFalse(r['actions_verified']);self.assertEqual(r['complete_stack_rosters'],3)
    def test_invalid_calibration_platform(self):
        with self.assertRaises(ValueError):augment({},[],'unknown')

if __name__=='__main__':unittest.main()
