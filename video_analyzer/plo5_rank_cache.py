"""Bounded exact five-card rank memoization for the validated offline PLO5 core."""
from functools import lru_cache

if __package__:
    from .offline_omaha_showdown import _five as reference_five
else:
    from offline_omaha_showdown import _five as reference_five

# There are only 6175 legal rank multisets and 1287 flush signatures.
# A rank is entirely determined by the multiset and whether all suits match.
@lru_cache(maxsize=7462)
def _signature_rank(ranks, flush):
    suits = 'ccccc' if flush else 'cdhsc'
    return reference_five(tuple(r+s for r,s in zip(ranks,suits)))


def fast_five(cards):
    """Internal primitive: caller must already supply five distinct valid cards."""
    a,b,c,d,e=cards
    ranks=''.join(sorted((a[0],b[0],c[0],d[0],e[0])))
    flush=a[1]==b[1]==c[1]==d[1]==e[1]
    return _signature_rank(ranks,flush)


def cache_info():
    return _signature_rank.cache_info()


def clear_cache():
    _signature_rank.cache_clear()
