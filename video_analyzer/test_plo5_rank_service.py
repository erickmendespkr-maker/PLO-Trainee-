import itertools
import os
import random
import unittest
from offline_omaha_showdown import _five,RANKS
from plo5_index_native import unrank_batch,SIZES
from plo5_rank_service import lookup_states,calculate_missing

INDEX=os.environ.get('PLO5_INDEX_EXE');RANK=os.environ.get('PLO5_RANK_EXE');CATALOG=os.environ.get('PLO5_RANK_CATALOG')


def independent_ordinals():
    rows=set()
    for ranks in itertools.combinations_with_replacement(RANKS,5):
        if len(set(ranks))==1:continue
        rows.add(_five(tuple(r+s for r,s in zip(ranks,'cdhsc'))))
        if len(set(ranks))==5:rows.add(_five(tuple(r+'c' for r in ranks)))
    return {v:i for i,v in enumerate(sorted(rows),1)}


@unittest.skipUnless(INDEX and RANK,'native index/rank executable absent')
class RankServiceTests(unittest.TestCase):
    def test_independent_ranks(self):
        ordinals=independent_ordinals();self.assertEqual(len(ordinals),7462)
        rng=random.Random(27112026)
        for s in (3,4,5):
            ids=[0,SIZES[s]-1]+[rng.randrange(SIZES[s]) for _ in range(200)]
            states=unrank_batch(INDEX,s,ids);rows=lookup_states(INDEX,None,s,states,rank_executable=RANK)
            for i,(h,b),r in zip(ids,states,rows):
                expected=max(_five(x+y) for x in itertools.combinations(h,2) for y in itertools.combinations(b,3))
                self.assertEqual((r['index'],r['rank'],r['source']),(i,ordinals[expected],'NATIVE_COMPUTED'))
    def test_miss_and_duplicate(self):
        states=unrank_batch(INDEX,5,[0,0,1]);r=lookup_states(INDEX,None,5,states)
        self.assertEqual([x['source'] for x in r],['UNSTORED']*3);self.assertTrue(all(x['rank'] is None for x in r))
        r=lookup_states(INDEX,None,5,states,rank_executable=RANK);self.assertEqual(r[0],r[1]);self.assertIsNot(r[0],r[1])
        with self.assertRaises(ValueError):calculate_missing(RANK,5,[SIZES[5]])
    @unittest.skipUnless(CATALOG,'real shard catalog absent')
    def test_real_shards(self):
        from plo5_rank_lookup import RankLookup
        with RankLookup(CATALOG,max_open=2) as reader:
            self.assertEqual(reader.coverage(),{3:100000,4:100000,5:100000})
            rng=random.Random(42)
            for s in (3,4,5):
                ids=[1000000,1099999]+[rng.randrange(1000000,1100000) for _ in range(200)]+[0]
                states=unrank_batch(INDEX,s,ids);r=lookup_states(INDEX,reader,s,states,rank_executable=RANK)
                self.assertEqual([x['rank'] for x in r],calculate_missing(RANK,s,ids))
                self.assertEqual([x['source'] for x in r],['SHARD']*202+['NATIVE_COMPUTED'])
                self.assertLessEqual(len(reader.maps),2)

if __name__=='__main__':unittest.main()
