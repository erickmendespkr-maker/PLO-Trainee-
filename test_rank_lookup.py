import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import tempfile
import time
import unittest
import sys
from plo5_rank_lookup import RankLookup, build_catalog, HEADER


def shard(path, street, start, ranks):
    fields = struct.pack('<QQQ', street, start, len(ranks))
    payload = struct.pack('<' + 'H'*len(ranks), *ranks)
    h = 14695981039346656037
    for v in fields + payload:
        h = ((h ^ v)*1099511628211) & 0xffffffffffffffff
    path.write_bytes(b'P5RANK01' + fields + struct.pack('<Q',h) + payload)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shard(self.root/'a.bin', 3, 10, [1,7462,100])
        shard(self.root/'b.bin', 3, 20, [200,300])
        shard(self.root/'c.bin', 5, 10, [500])

    def tearDown(self):
        self.tmp.cleanup()

    def catalog(self):
        return build_catalog(self.root, ['b.bin','a.bin','c.bin'])

    def test_lookup_gaps_boundaries_lru(self):
        with RankLookup(self.catalog(), max_open=1) as db:
            self.assertEqual(db.coverage(), {3:5,4:0,5:1})
            for street,index,rank in [(3,9,None),(3,10,1),(3,11,7462),(3,12,100),(3,13,None),(3,19,None),(3,20,200),(3,21,300),(3,22,None),(5,10,500),(3,10,1),(4,10,None)]:
                self.assertEqual(db.lookup(street,index),rank)
                self.assertLessEqual(len(db.maps),1)
            for s,i in [(2,0),(3,-1),(3,1800975787),(3,True)]:
                with self.assertRaises(ValueError): db.lookup(s,i)
        with self.assertRaises(RuntimeError): db.lookup(3,10)

    def test_overlap(self):
        shard(self.root/'b.bin',3,12,[200])
        with self.assertRaises(ValueError): self.catalog()

    def test_original_corruption(self):
        p=self.root/'a.bin'; p.write_bytes(p.read_bytes()[:-1]+b'\x99')
        with self.assertRaises(ValueError): self.catalog()

    def test_after_catalog_corruption(self):
        c=self.catalog(); p=self.root/'a.bin'; p.write_bytes(p.read_bytes()[:-1]+b'\x99')
        with RankLookup(c) as db:
            with self.assertRaises(ValueError): db.lookup(3,10)

    def test_truncated(self):
        p=self.root/'a.bin'; p.write_bytes(p.read_bytes()[:-1])
        with self.assertRaises(ValueError): self.catalog()

    def test_invalid_rank(self):
        shard(self.root/'a.bin',3,10,[0])
        with self.assertRaises(ValueError): self.catalog()

    def test_version_and_path(self):
        p=self.catalog(); d=json.loads(p.read_text()); d['index']='wrong'; p.write_text(json.dumps(d))
        with self.assertRaises(ValueError): RankLookup(p)
        d['index']='canonical-matrix-v1'; d['shards'][0]['file']='../a.bin'; p.write_text(json.dumps(d))
        with self.assertRaises(ValueError): RankLookup(p)

    def test_no_overwrite(self):
        self.catalog()
        with self.assertRaises(FileExistsError): self.catalog()


def benchmark(source):
    with tempfile.TemporaryDirectory() as d:
        root=Path(d); files=sorted(Path(source).glob('*.bin'))
        for p in files: shutil.copyfile(p,root/p.name)
        t=time.perf_counter(); catalog=build_catalog(root,[p.name for p in files]); print('catalog_seconds',time.perf_counter()-t)
        rng=random.Random(42); queries=[]
        for p in files:
            data=p.read_bytes(); _,s,start,n,_=HEADER.unpack_from(data)
            for i in [0,n-1]+[rng.randrange(n) for _ in range(100000)]:
                queries.append((s,start+i,struct.unpack_from('<H',data,40+2*i)[0]))
        rng.shuffle(queries)
        with RankLookup(catalog,max_open=len(files)) as db:
            for s,g in db.groups.items():
                for e in g: db.lookup(s,e['start'])
            t=time.perf_counter()
            for s,i,v in queries:
                if db.lookup(s,i)!=v: raise AssertionError('lookup mismatch')
            sec=time.perf_counter()-t
            print('coverage',db.coverage(),'verified_queries',len(queries),'seconds',sec,'per_second',len(queries)/sec)

if __name__=='__main__':
    if len(sys.argv)==2: benchmark(sys.argv[1])
    else: unittest.main()
