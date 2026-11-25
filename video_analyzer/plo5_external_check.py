"""Optional offline differential checks; external engines never replace production automatically."""
import argparse
import json
import random
import subprocess
import time

DECK = tuple(r+s for r in '23456789TJQKA' for s in 'cdhs')


def cases(count=256, seed=20261125):
    if type(count) is not int or not 1 <= count <= 4096:
        raise ValueError('Invalid case count')
    rng=random.Random(seed)
    for i in range(count):
        n=2+i%5
        cards=rng.sample(DECK,5+5*n)
        yield {'board':cards[:5],'hands':[cards[5+5*j:10+5*j] for j in range(n)]}


def native(rows):
    from plo5_evaluator import showdown
    return [showdown(x['hands'],x['board'])['winner_indices'] for x in rows]


def pokerkit(rows):
    from pokerkit import OmahaHoldemHand
    result=[]
    for x in rows:
        ranks=[OmahaHoldemHand.from_game(''.join(h),''.join(x['board'])) for h in x['hands']]
        best=max(ranks)
        result.append([i for i,h in enumerate(ranks) if h==best])
    return result


JS = '''import {showdown} from 'pi-poker-eval';
let input=''; for await(const c of process.stdin) input+=c;
const rows=JSON.parse(input);
console.log(JSON.stringify(rows.map(x=>showdown('PLO5',x.board,x.hands).winners)));
'''


def pokerinfra(rows):
    p=subprocess.run(['node','--input-type=module','-e',JS],input=json.dumps(rows),
                     text=True,capture_output=True,timeout=60,check=True)
    if len(p.stdout)>1024*1024:
        raise ValueError('Oversized result')
    return json.loads(p.stdout)


def checked(rows, values):
    if type(values) is not list or len(values)!=len(rows):
        raise ValueError('External result coverage mismatch')
    for row, winners in zip(rows,values):
        if (type(winners) is not list or not winners or
                any(type(i) is not int or not 0<=i<len(row['hands']) for i in winners) or
                len(set(winners))!=len(winners)):
            raise ValueError('Invalid winner indices')
    return [sorted(w) for w in values]


def compare(rows, reference, candidate):
    start=time.perf_counter(); a=checked(rows,reference(rows)); t1=time.perf_counter()-start
    start=time.perf_counter(); b=checked(rows,candidate(rows)); t2=time.perf_counter()-start
    mismatches=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
    return {'variant':5,'cases':len(rows),'mismatches':mismatches,'reference_seconds':t1,
            'candidate_seconds':t2,'winner_agreement':not mismatches,
            'scope':'known_complete_showdowns_only','production_backend_changed':False,'gto_solution':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('backend',choices=('pokerkit','pokerinfra'));p.add_argument('--cases',type=int,default=256);p.add_argument('--seed',type=int,default=20261125)
    a=p.parse_args(argv);report=compare(list(cases(a.cases,a.seed)),native,{'pokerkit':pokerkit,'pokerinfra':pokerinfra}[a.backend]);print(json.dumps(report,indent=2));return 0 if report['winner_agreement'] else 1


if __name__=='__main__':raise SystemExit(main())
