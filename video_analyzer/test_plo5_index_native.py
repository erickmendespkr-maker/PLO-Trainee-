import itertools
import os
import random
import subprocess
import unittest
from plo5_index_native import rank_batch,unrank_batch,SIZES,CARD_ID

EXE=os.environ.get('PLO5_INDEX_EXE')


@unittest.skipUnless(EXE,'native index executable absent')
class IndexTests(unittest.TestCase):
    def test_counts_and_roundtrip(self):
        rng=random.Random(27112026)
        for s,size in SIZES.items():
            p=subprocess.run([EXE],input=f'{s} size 0\n',text=True,capture_output=True,check=True)
            self.assertEqual(int(p.stdout),size)
            ids=[0,size-1]+[rng.randrange(size) for _ in range(100)]
            self.assertEqual(rank_batch(EXE,s,unrank_batch(EXE,s,ids)),ids)
    def test_suit_permutations_and_order(self):
        h=['As','Kd','Qh','Jc','Ts'];b=['2c','3d','4h','5s','6c']
        def rename(cards,m):return [x[0]+m[x[1]] for x in cards]
        states=[]
        for suits in itertools.permutations('cdhs'):
            m=dict(zip('cdhs',suits));states.append((rename(h[::-1],m),rename(b[:3][::-1]+b[3:],m)))
        self.assertEqual(len(set(rank_batch(EXE,5,states))),1)
        a,z=rank_batch(EXE,5,[(h,b),(h,b[:3]+b[3:][::-1])]);self.assertNotEqual(a,z)
    def test_invalid(self):
        with self.assertRaises(ValueError):rank_batch(EXE,3,[(['As','Kd','Qh','Jc','Ts'],['As','2c','3d'])])
        with self.assertRaises(ValueError):unrank_batch(EXE,5,[SIZES[5]])
        for payload in ('2 size 0\n','5 unrank 1\n-1\n','3 rank 1\n0 1 2 3 4 4 5 6\n'):
            self.assertNotEqual(subprocess.run([EXE],input=payload,text=True,capture_output=True).returncode,0)

if __name__=='__main__':unittest.main()
