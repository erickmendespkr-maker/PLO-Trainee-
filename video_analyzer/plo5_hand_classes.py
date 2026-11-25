"""Exact PLO5 preflop suit orbits; source descriptors are deliberately lossy."""
from collections import Counter
from itertools import combinations, combinations_with_replacement, groupby, product
from math import factorial, prod

if __package__:
    from .offline_omaha_showdown import _cards
else:
    from offline_omaha_showdown import _cards

RANKS = 'AKQJT98765432'
SUITS = 'cdhs'
PARTITIONS = {(2,2,1):'ds',(2,1,1,1):'ss',(3,1,1):'3-suit',
              (3,2):'3+2',(4,1):'4-suit',(5,):'mono'}
BITS = {r:1<<i for i,r in enumerate(RANKS)}


def orbit_size(masks):
    return factorial(4)//prod(factorial(n) for n in Counter(masks).values())


def descriptor(masks):
    ranks = '-'.join(r for r in RANKS for m in masks if m & BITS[r])
    partition = tuple(sorted((m.bit_count() for m in masks if m),reverse=True))
    return ranks,PARTITIONS[partition]


def classify(cards):
    """Unordered five cards modulo a global permutation of the four suits."""
    cards = _cards(cards,5)
    masks = tuple(sorted(sum(BITS[c[0]] for c in cards if c[1]==s) for s in SUITS))
    hand,suits = descriptor(masks)
    return {'variant':5,'class_id':'plo5-suit-v1:'+':'.join(f'{m:04x}' for m in masks),
            'canonical_cards':[r+s for s,m in zip(SUITS,masks) for r in RANKS if m & BITS[r]],
            'suit_masks':list(masks),'rank_descriptor':hand,'suit_descriptor':suits,
            'suit_partition':sorted((m.bit_count() for m in masks if m),reverse=True),
            'physical_combinations':orbit_size(masks),
            'scope':'preflop_global_suit_permutation_only','gto':False}


def enumerate_orbits():
    """Generate each orbit once by unordered suit rank masks of total size five."""
    masks_by_size={n:[sum(BITS[r] for r in rs) for rs in combinations(RANKS,n)] for n in range(6)}
    for partition in PARTITIONS:
        sizes=sorted((0,)*(4-len(partition))+partition)
        pools=[combinations_with_replacement(masks_by_size[n],len(list(group))) for n,group in groupby(sizes)]
        for groups in product(*pools):
            yield tuple(sorted(m for group in groups for m in group))


def audit_source(db):
    """Compare the complete multiset of descriptor/orbit-size counts, not row identities."""
    expected=Counter(( *descriptor(masks),orbit_size(masks)) for masks in enumerate_orbits())
    actual=Counter({(hand,suits,combos):n for hand,suits,combos,n in db.execute(
        'SELECT hand,suits,combos,count(*) FROM equity GROUP BY hand,suits,combos')})
    by_descriptor=Counter()
    for (hand,suits,_),n in expected.items():
        by_descriptor[hand,suits]+=n
    return {'variant':5,'status':'AGGREGATE_COUNTS_MATCH' if expected==actual else 'AGGREGATE_COUNTS_MISMATCH',
            'exact_orbits':sum(expected.values()),'physical_combinations':sum(k[2]*n for k,n in expected.items()),
            'descriptor_count':len(by_descriptor),'ambiguous_descriptors':sum(n>1 for n in by_descriptor.values()),
            'expected_groups':len(expected),'source_groups':len(actual),'source_rows':sum(actual.values()),
            'missing_class_mass':sum((expected-actual).values()),'unexpected_class_mass':sum((actual-expected).values()),
            'source_row_identity_verified':False,'exact_equity_mapping_available':False,'gto':False}
