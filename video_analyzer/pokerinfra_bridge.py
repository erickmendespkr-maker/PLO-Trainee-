"""Offline adapter to MIT-licensed pi-poker-eval (npm); no live-game integration."""
import json
import math
import os
from pathlib import Path
import re
import subprocess

VARIANTS = {'PLO': 4, 'PLO5': 5, 'PLO6': 6}
CARD = re.compile(r'^[2-9TJQKA][cdhs]$', re.I)

def _cards(cards, count=None):
    if not isinstance(cards, list) or (count is not None and len(cards) != count):
        raise ValueError('invalid card count')
    if any(not isinstance(c,str) or not CARD.fullmatch(c) for c in cards):
        raise ValueError('invalid card token')
    return [c[0].upper()+c[1].lower() for c in cards]

def _unique(*groups):
    cards = [c for group in groups for c in group]
    if len(cards) != len(set(cards)):
        raise ValueError('duplicate cards')

def request(operation, variant, *, hole=None, board=None, holes=None, dead=None, trials=10000, seed=1):
    if variant not in VARIANTS: raise ValueError('unsupported variant')
    board = _cards([] if board is None else board)
    if len(board) not in (0,3,4,5): raise ValueError('invalid board count')
    if operation == 'evaluate':
        hole = _cards(hole, VARIANTS[variant]); _unique(hole,board)
        return {'operation':operation,'variant':variant,'hole':hole,'board':board}
    if operation in ('showdown','equity'):
        if not isinstance(holes,list) or not 2 <= len(holes) <= 10:
            raise ValueError('invalid player count')
        holes = [_cards(h, None if operation == 'equity' and h == [] else VARIANTS[variant]) for h in holes]
        dead = _cards([] if dead is None else dead)
        _unique(board,dead,*holes)
        if operation == 'showdown':
            if dead: raise ValueError('dead cards not supported for showdown')
            return {'operation':operation,'variant':variant,'board':board,'holes':holes}
        if type(trials) is not int or not 100 <= trials <= 1000000 or type(seed) is not int or not 0 <= seed <= 4294967295:
            raise ValueError('invalid Monte Carlo settings')
        return {'operation':operation,'request':{'variant':variant,'players':holes,'board':board,'dead':dead,
            'method':{'type':'monteCarlo','trials':trials,'seed':seed}}}
    raise ValueError('unsupported operation')

def run(payload, *, npm_dir=None, timeout=90):
    if not isinstance(payload,dict) or payload.get('operation') not in ('evaluate','showdown','equity'):
        raise ValueError('invalid request')
    directory = Path(npm_dir) if npm_dir is not None else Path(__file__).resolve().parent
    if not (directory/'node_modules'/'pi-poker-eval').is_dir():
        raise RuntimeError('install pi-poker-eval in video_analyzer first')
    env = dict(os.environ, NODE_PATH=str(directory/'node_modules'))
    try:
        proc = subprocess.run(['node',str(Path(__file__).with_name('pokerinfra_cli.cjs'))],
            input=json.dumps(payload),text=True,capture_output=True,cwd=directory,
            env=env,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError('offline evaluator unavailable') from exc
    if proc.returncode or len(proc.stdout)>1048576:
        raise RuntimeError('offline evaluator failed')
    data=json.loads(proc.stdout)
    if data.get('engine')!='pi-poker-eval' or not isinstance(data.get('result'),dict):
        raise RuntimeError('invalid evaluator response')
    return data['result']

def pot_odds_and_call_ev(pot_bb,call_bb,equity_fraction):
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (pot_bb,call_bb,equity_fraction)):
        raise ValueError('nonfinite input')
    if pot_bb<0 or call_bb<=0 or not 0<=equity_fraction<=1:
        raise ValueError('invalid input')
    return {'required_equity':call_bb/(pot_bb+call_bb),
        'call_ev_bb':equity_fraction*(pot_bb+call_bb)-call_bb,
        'assumptions':'full equity realization; no rake, side pots or future bets',
        'is_gto':False}
