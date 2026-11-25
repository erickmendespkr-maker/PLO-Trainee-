import time, json, hashlib, resource
from plo5_postflop_draws import draws
from plo5_equity import equity
from test_plo5_action_ev import scenario
from plo5_evaluator import evaluate
import random
from offline_omaha_showdown import RANKS, SUITS
rng=random.Random(35);deck=[r+s for r in RANKS for s in SUITS];holdings=[rng.sample(deck,10) for _ in range(1000)]
for round in range(2):
    start=time.perf_counter();out=[evaluate(x[:5],x[5:]) for x in holdings];t1=time.perf_counter();out.append(draws(['As','Ks','Qh','Jh','Tc'],['9s','8s','2d']));t2=time.perf_counter();s=scenario();out.append(equity(s['hero'],[],s['range'],trials=1000,seed=35));t3=time.perf_counter()
    print(json.dumps({'round':round,'evaluate_seconds':t1-start,'draws_seconds':t2-t1,'equity_seconds':t3-t2,'total_seconds':t3-start,'rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'sha256':hashlib.sha256(json.dumps(out,sort_keys=True).encode()).hexdigest()}),flush=True)
