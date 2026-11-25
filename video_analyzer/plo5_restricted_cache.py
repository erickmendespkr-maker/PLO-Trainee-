"""Local cache for explicitly prepared restricted river games, not a GTO database."""
import hashlib
import json
import math
import sqlite3
from plo5_cfr_restricted import optimize, certificate

VERSION='restricted-river-cfr-v1'


def connect(path):
    db=sqlite3.connect(path)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS restricted_solutions (key TEXT PRIMARY KEY, input TEXT NOT NULL, policy TEXT NOT NULL)')
        db.commit()
        return db
    except BaseException:
        db.close();raise


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False)


def validated_policy(pairs,na,nv,policy,target):
    if type(policy) is not dict or set(policy)!={'hero_bet_probabilities','opponent_call_probabilities','iterations'}:
        raise ValueError('Invalid cached policy')
    x,y=policy['hero_bet_probabilities'],policy['opponent_call_probabilities']
    if (type(x) is not list or len(x)!=na or type(y) is not list or len(y)!=nv
            or any(type(z) not in (float,int) or not math.isfinite(z) or not 0<=z<=1 for z in x+y)):
        raise ValueError('Invalid policy probabilities')
    cert=certificate(pairs,x,y,na,nv)
    if cert['gap']>target:
        raise ValueError('Cached policy does not meet requested gap')
    return cert


def resolve(db,pairs,na,nv,*,iterations=10000,algorithm='cfr_plus',target=.01,check_every=50):
    # Keep the precise prepared payoff matrix, configuration and version in the key.
    options=dict(iterations=iterations,algorithm=algorithm,target=target,check_every=check_every)
    # Validate even on a hit. One iteration is enough to run the core's input guards;
    # preserve the original full budget guard rather than accepting an oversized hit.
    if type(iterations) is not int or not 1<=iterations<=50000 or type(pairs) not in (list,tuple) or iterations*len(pairs)>4000000:
        raise ValueError('Invalid pairing budget')
    optimize(pairs,na,nv,iterations=1,algorithm=algorithm,target=target,check_every=check_every)
    payload=canonical([VERSION,pairs,na,nv,options]);key=hashlib.sha256(payload.encode()).hexdigest()
    row=db.execute('SELECT input,policy FROM restricted_solutions WHERE key=?',(key,)).fetchone()
    if row is not None:
        if row[0]!=payload:raise ValueError('Cache key mismatch')
        policy=json.loads(row[1]);cert=validated_policy(pairs,na,nv,policy,target)
        if type(policy['iterations']) is not int or not 1<=policy['iterations']<=iterations:
            raise ValueError('Invalid cached iteration count')
        return {**policy,**cert,'algorithm':algorithm,'target_gap_fraction_of_pot':target,'target_reached':True,
                'gto_solution':False,'scope':'restricted_river_game_only','cache_hit':True}
    report=optimize(pairs,na,nv,**options)
    if report['target_reached']:
        policy={k:report[k] for k in ('hero_bet_probabilities','opponent_call_probabilities','iterations')}
        validated_policy(pairs,na,nv,policy,target)
        with db:db.execute('INSERT INTO restricted_solutions VALUES (?,?,?) ON CONFLICT(key) DO NOTHING',(key,payload,canonical(policy)))
    return {**report,'cache_hit':False}
