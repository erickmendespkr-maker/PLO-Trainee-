import itertools
import math
import os
import sqlite3
import unittest
from collections import Counter
from contextlib import closing

from plo5_hand_classes import classify, enumerate_orbits, orbit_size, audit_source, SUITS


class ClassTests(unittest.TestCase):
    def test_global_permutation_and_order(self):
        h=['As','Ad','Ks','Qd','Tc']; ref=classify(h)
        for perm in itertools.permutations(SUITS):
            mapping=dict(zip(SUITS,perm))
            self.assertEqual(classify([c[0]+mapping[c[1]] for c in reversed(h)]),ref)
        self.assertEqual(classify(ref['canonical_cards']),ref)

    def test_same_descriptor_distinct_classes(self):
        a=classify(['As','Ks','Qh','Jh','Tc']);b=classify(['As','Qs','Kh','Jh','Tc'])
        self.assertEqual((a['rank_descriptor'],a['suit_descriptor'],a['physical_combinations']),
                         (b['rank_descriptor'],b['suit_descriptor'],b['physical_combinations']))
        self.assertNotEqual(a['class_id'],b['class_id'])

    def test_all_partitions(self):
        for suits,label in [('sshhc','ds'),('sshcd','ss'),('ssshc','3-suit'),('ssshh','3+2'),('ssssh','4-suit'),('sssss','mono')]:
            self.assertEqual(classify([r+s for r,s in zip('AKQJT',suits)])['suit_descriptor'],label)

    def test_orbit_size_actual_permutations(self):
        for h in [['As','Ks','Qh','Jh','Tc'],['As','Ah','Ac','Ad','Ks'],['As','Ah','Ks','Kh','Tc'],['As','Ks','Qs','Js','Ts']]:
            holdings={tuple(sorted(c[0]+dict(zip(SUITS,p))[c[1]] for c in h)) for p in itertools.permutations(SUITS)}
            self.assertEqual(classify(h)['physical_combinations'],len(holdings))

    def test_exhaustive_orbits_burnside(self):
        # Independent Burnside count using fixed subsets under each suit cycle type.
        def fixed(cycles):
            coeff=[1,0,0,0,0,0]
            for n in cycles*13:
                for i in range(5,n-1,-1):coeff[i]+=coeff[i-n]
            return coeff[5]
        burnside=sum(n*fixed(c) for n,c in [(1,[1,1,1,1]),(6,[2,1,1]),(3,[2,2]),(8,[3,1]),(6,[4])])//24
        seen=set(); sizes=Counter()
        for masks in enumerate_orbits():
            self.assertNotIn(masks,seen);seen.add(masks)
            self.assertEqual(sum(m.bit_count() for m in masks),5)
            sizes[orbit_size(masks)]+=1
        self.assertEqual(len(seen),burnside)
        self.assertEqual(len(seen),134459)
        self.assertEqual(sum(k*v for k,v in sizes.items()),math.comb(52,5))
        self.assertEqual(set(sizes),{4,12,24})

    def test_invalid_inputs(self):
        for h in (['As']*5,['As','Ks','Qs','Js'],['As','Ks','Qs','Js','Ts','9s'],['As','Ks','Qs','Js','XX']):
            with self.assertRaises(ValueError):classify(h)

    def test_mismatch_and_no_row_identity(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE equity(hand,suits,combos)')
            db.execute("INSERT INTO equity VALUES ('A-A-A-A-K','ss',4)")
            r=audit_source(db)
            self.assertEqual(r['status'],'AGGREGATE_COUNTS_MISMATCH')
            self.assertFalse(r['exact_equity_mapping_available'])
            self.assertEqual(r['missing_class_mass'],134458)

    @unittest.skipUnless(os.environ.get('PLO5_REVIEWED_EQUITY_DB'),'Reviewed equity snapshot required')
    def test_complete_snapshot(self):
        from plo5_decision_analysis import EQUITY_DB_SHA256, sha256, open_readonly, descriptor_reference
        path=os.environ['PLO5_REVIEWED_EQUITY_DB']
        self.assertEqual(sha256(path),EQUITY_DB_SHA256)
        with closing(open_readonly(path,immutable=True)) as db:
            r=audit_source(db)
            self.assertEqual(r['status'],'AGGREGATE_COUNTS_MATCH')
            self.assertEqual((r['expected_groups'],r['descriptor_count'],r['ambiguous_descriptors']),(36790,28496,20449))
            self.assertFalse(r['source_row_identity_verified'])
            a=descriptor_reference(db,{'street':'preflop','hero':['As','Ks','Qh','Jh','Tc']})
            b=descriptor_reference(db,{'street':'preflop','hero':['As','Qs','Kh','Jh','Tc']})
            self.assertNotEqual(a['hand_class']['class_id'],b['hand_class']['class_id'])
            self.assertEqual(a['rows'],b['rows']);self.assertFalse(a['exact_suit_match']);self.assertIsNone(a['ev_bb'])
        self.assertEqual(sha256(path),EQUITY_DB_SHA256)


if __name__=='__main__':unittest.main()
