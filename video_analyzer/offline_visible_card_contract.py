"""Strict visible-card and monetary checks for offline PLO5/PLO6 review."""
import math
import re

CARD = re.compile(r'^[2-9TJQKA][cdhs]$')

def validate_fields(values):
    hero = values['hero_cards']
    board = values['board_cards']
    if type(hero) is not list or len(hero) not in (5, 6):
        raise ValueError('hero must contain five or six visible cards')
    if type(board) is not list or len(board) not in (0, 3, 4, 5):
        raise ValueError('board must contain zero, three, four or five cards')
    cards = hero + board
    if any(type(c) is not str or not CARD.fullmatch(c) for c in cards):
        raise ValueError('invalid card notation')
    if len(set(cards)) != len(cards):
        raise ValueError('duplicate card')
    if type(values['action']) is not str or values['action'] not in ('fold', 'check', 'call', 'bet', 'raise', 'all-in'):
        raise ValueError('invalid action')
    for key in ('pot', 'call_cost'):
        v = values[key]
        if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
            raise ValueError('invalid monetary field: ' + key)
    if values['action'] == 'call' and values['call_cost'] <= 0:
        raise ValueError('call requires positive cost')
