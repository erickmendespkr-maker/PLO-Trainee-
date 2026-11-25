"""Versioned normalization for explicit PLO5/PLO6 decision snapshots."""
from decimal import Decimal, InvalidOperation, localcontext
import re

SCHEMA = 'plo-decision-v2'
POSITIONS = {2: ('SB', 'BB'), 3: ('BTN', 'SB', 'BB'),
             4: ('CO', 'BTN', 'SB', 'BB'), 5: ('UTG', 'CO', 'BTN', 'SB', 'BB'),
             6: ('UTG', 'MP', 'CO', 'BTN', 'SB', 'BB')}
STREETS = {'preflop': 0, 'flop': 3, 'turn': 4, 'river': 5}
FIELDS = {'schema', 'players', 'position', 'street', 'hero', 'board', 'amount_unit',
          'bb_size', 'stack', 'pot', 'to_call', 'rake_percent', 'rake_cap',
          'frequency_unit', 'ev_baseline', 'model', 'node'}


def number(value):
    if type(value) not in (int, float, str) or len(str(value)) > 64:
        raise ValueError('Expected explicit decimal number')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal') from exc
    if not result.is_finite() or abs(result) > Decimal('1e9') or (result and abs(result) < Decimal('1e-16')):
        raise ValueError('Nonfinite or out-of-range decimal')
    return result


def decimal_text(value):
    with localcontext() as ctx:
        ctx.prec = 40
        rounded = value.quantize(Decimal('0.00000001'))
    if rounded == 0:
        return '0'
    return format(rounded.normalize(), 'f')


def card(value):
    if not isinstance(value, str):
        raise ValueError('Invalid card')
    match = re.fullmatch(r'(10|[2-9TJQKA])([cdhs])', value.strip(), re.I)
    if match is None:
        raise ValueError('Invalid card rank or suit')
    rank, suit = match.groups()
    return ('T' if rank == '10' else rank.upper()) + suit.lower()


def normalize_scenario(variant, raw):
    if type(variant) is not int or variant not in (5, 6):
        raise ValueError('Invalid variant')
    if type(raw) is not dict or set(raw) != FIELDS or raw['schema'] != SCHEMA:
        raise ValueError('Expected complete versioned decision scenario')
    players = raw['players']
    if type(players) is not int or players not in POSITIONS:
        raise ValueError('Invalid table size')
    if not isinstance(raw['position'], str) or not isinstance(raw['street'], str):
        raise ValueError('Invalid position or street')
    position, street = raw['position'].strip().upper(), raw['street'].strip().lower()
    if position not in POSITIONS[players] or street not in STREETS:
        raise ValueError('Unsupported position or street')
    if type(raw['hero']) is not list or type(raw['board']) is not list:
        raise ValueError('Expected card lists')
    hero, board = list(map(card, raw['hero'])), list(map(card, raw['board']))
    if len(hero) != variant or len(board) != STREETS[street] or len(set(hero + board)) != len(hero + board):
        raise ValueError('Invalid card count or duplicate card')
    unit, bb = raw['amount_unit'], number(raw['bb_size'])
    if unit not in ('BB', 'chips') or bb <= 0 or (unit == 'BB' and bb != 1):
        raise ValueError('Explicit amount unit and positive big blind required')
    if raw['frequency_unit'] not in ('fraction', 'percent') or raw['ev_baseline'] != 'decision':
        raise ValueError('Explicit frequency unit and decision EV baseline required')
    def amount(value):
        with localcontext() as ctx:
            ctx.prec = 40
            return number(value) / bb
    stack, pot, call, cap = (amount(raw[k]) for k in ('stack', 'pot', 'to_call', 'rake_cap'))
    rake = number(raw['rake_percent'])
    if not (0 < stack <= Decimal('1e9') and 0 < pot <= Decimal('1e9') and
            0 <= call <= min(stack, pot) and 0 <= cap <= Decimal('1e9') and 0 <= rake <= 100):
        raise ValueError('Invalid stack, pot, call or rake')
    if any(value > 0 and number(decimal_text(value)) == 0 for value in (stack, pot, call, cap)):
        raise ValueError('Positive amount below supported precision')
    if any(not isinstance(raw[k], str) or not raw[k].strip() or len(raw[k]) > 256 for k in ('model', 'node')):
        raise ValueError('Explicit model and node identifiers required')
    return dict(schema=SCHEMA, players=players, position=position, street=street,
                hero=sorted(hero), board=sorted(board[:3])+board[3:], amount_unit='BB', bb_size='1',
                stack=decimal_text(stack), pot=decimal_text(pot), to_call=decimal_text(call),
                rake_percent=decimal_text(rake), rake_cap=decimal_text(cap), frequency_unit='fraction',
                ev_baseline='decision', model=raw['model'], node=raw['node'])


def normalize_record(variant, scenario, actions):
    context = normalize_scenario(variant, scenario)
    if type(actions) is not list or not actions or len(actions) > 100:
        raise ValueError('Expected explicit action list')
    bb = number(scenario['bb_size'])
    scale = 100 if scenario['frequency_unit'] == 'percent' else 1
    stack, pot, call = (number(context[k]) for k in ('stack', 'pot', 'to_call'))
    result, seen = [], set()
    total = Decimal(0)
    for entry in actions:
        if type(entry) is not dict or set(entry) != {'action', 'size', 'frequency', 'ev'}:
            raise ValueError('Unexpected action fields')
        if not isinstance(entry['action'], str):
            raise ValueError('Invalid action name')
        action = entry['action'].strip().lower()
        with localcontext() as ctx:
            ctx.prec = 40
            size = number(entry['size']) / bb
            frequency = number(entry['frequency']) / scale
            ev = None if entry['ev'] is None else number(entry['ev']) / bb
        if not 0 <= frequency <= 1 or not 0 <= size <= Decimal('1e9') or (ev is not None and abs(ev) > Decimal('1e9')):
            raise ValueError('Invalid action amount, frequency or EV')
        size = number(decimal_text(size))
        legal = ((action == 'fold' and size == 0 and call > 0) or
                 (action == 'check' and size == 0 and call == 0) or
                 (action == 'call' and size == call and call > 0) or
                 (action == 'bet' and call == 0 and 0 < size <= min(stack, pot)) or
                 (action == 'raise' and call > 0 and call < size <= min(stack, pot + 2*call)))
        if not legal or (action, size) in seen:
            raise ValueError('Incompatible or duplicate action')
        seen.add((action, size))
        total += frequency
        result.append(dict(action=action, size=decimal_text(size), frequency=decimal_text(frequency),
                           ev=None if ev is None else decimal_text(ev)))
    rounded_total = sum(number(entry['frequency']) for entry in result)
    if abs(total-1) > Decimal('0.000001') or abs(rounded_total-1) > Decimal('0.000001'):
        raise ValueError('Frequencies must sum to one')
    return context, sorted(result, key=lambda a: (a['action'], number(a['size'])))
