"""Exact, manually labelled card-slot codebook; existing recognizers handle misses."""
from plo5_visual_codes import pixels, labeled_row, need

RANKS='23456789TJQKA'
SUITS='cdhs'


def valid_card(value):
    return type(value) is str and len(value)==2 and value[0] in RANKS and value[1] in SUITS


def label_slot(profile,field,rank,suit,card):
    need(field in ('hero','board') and valid_card(card),'Invalid card annotation')
    return [labeled_row(profile,field+'/rank',rank,(0,0,*rank.size),card),
            labeled_row(profile,field+'/suit',suit,(0,0,*suit.size),card[1])]


def read_slot(bank,profile,field,rank,suit,*,guard=True):
    """Return existing classifier-shaped candidate, or None to use existing fallback.
    False guard means existing special-geometry classifier must handle the slot.
    No inference from the rank alone, no near matching, no verified card claim.
    """
    need(field in ('hero','board') and type(guard) is bool,'Invalid field or guard')
    if bank is None or not guard:return None
    a=bank.match(profile,field+'/rank',pixels(rank,(0,0,*rank.size)))
    b=bank.match(profile,field+'/suit',pixels(suit,(0,0,*suit.size)))
    blank=dict(card=None,rank=None,suit_color=None,rank_color=None,status='uncertain',distance=None,margin=None)
    if 'CONFLICT' in (a['status'],b['status']):return dict(blank,source='VISUAL_CODE_CONFLICT')
    if 'UNKNOWN' in (a['status'],b['status']):return None
    card=a['label'];color=b['label']
    if not valid_card(card) or card[1]!=color:return dict(blank,source='VISUAL_CODE_CONFLICT')
    return dict(card=card,rank=card[0],suit_color=color,rank_color=color,status='candidate_unverified',
                distance=None,margin=None,source='MANUAL_VISUAL_CODE',rank_code=a['code'],suit_code=b['code'])
