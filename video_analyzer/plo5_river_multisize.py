"""Offline PLO5 HU river: check/showdown or choose one of several legal bets.

CFR+ with independently evaluated best-response bounds. No raises, no rake,
no inferred ranges, no full-game GTO. Reuses existing weighted legal deals.
"""
import math
from plo5_river_solver import prepare


def policy(r):
    total = sum(r)
    return [z / total for z in r] if total else [1 / len(r)] * len(r)


def optimize(pairs, na, nv, ratios, iterations=10000, target=.01):
    k = len(ratios)
    if not 1 <= k <= 8 or not 1 <= iterations <= 50000:
        raise ValueError("Invalid action or iteration budget")
    if iterations * len(pairs) * k > 4000000:
        raise ValueError("Pair-action budget exceeded")
    if not math.isfinite(target) or not 0 <= target <= 1:
        raise ValueError("Invalid gap target")
    ra = [[0.] * (k+1) for _ in range(na)]
    rv = [[[0., 0.] for _ in ratios] for _ in range(nv)]
    sa = [[0.] * (k+1) for _ in range(na)]
    sv = [[[0., 0.] for _ in ratios] for _ in range(nv)]
    deals = [(i,j,w,q,[q*(1+2*b)-b for b in ratios])
             for i,j,w,q,_ in pairs]

    def utilities(x,y):
        a = [[0.] * (k+1) for _ in range(na)]
        v = [[[0.,0.] for _ in ratios] for _ in range(nv)]
        for i,j,w,q,called in deals:
            a[i][0] += w*q
            for s,c in enumerate(called):
                f,call = y[j][s]
                a[i][s+1] += w*(f+call*c)
                reach = w*x[i][s+1]
                v[j][s][0] += reach
                v[j][s][1] += reach*c
        return a,v

    def update(r,s,p,u,t,sign):
        avg = sum(x*y for x,y in zip(p,u))
        for z in range(len(r)):
            r[z] = max(0.,r[z]+sign*(u[z]-avg))
            s[z] += t*p[z]

    def certificate(x,y):
        a,v = utilities(x,y)
        value = sum(sum(p*u for p,u in zip(xi,ai)) for xi,ai in zip(x,a))
        upper = sum(max(ai) for ai in a)
        lower = sum(x[i][0]*a[i][0] for i in range(na))
        lower += sum(min(row) for player in v for row in player)
        if not lower-1e-9 <= value <= upper+1e-9:
            raise ArithmeticError("Invalid best-response bounds")
        return value,lower,upper,max(0.,upper-lower),a

    for t in range(1,iterations+1):
        x = [policy(r) for r in ra]
        y = [[policy(r) for r in player] for player in rv]
        a,v = utilities(x,y)
        for i in range(na):
            update(ra[i],sa[i],x[i],a[i],t,1)
        for j in range(nv):
            for s in range(k):
                update(rv[j][s],sv[j][s],y[j][s],v[j][s],t,-1)
        if t % 50 == 0 or t == iterations:
            ax = [policy(s) for s in sa]
            ay = [[policy(s) for s in player] for player in sv]
            value,lower,upper,gap,ev = certificate(ax,ay)
            if gap <= target:
                break
    return dict(iterations=t,value=value,lower=lower,upper=upper,gap=gap,
                target_reached=gap<=target,hero_policy=ax,opponent_policy=ay,
                weighted_action_values=ev)


def solve(game, bet_sizes, *, iterations=10000, target=.01):
    if (type(bet_sizes) not in (list,tuple) or not 1<=len(bet_sizes)<=8
            or any(type(b) is not int or b<=0 for b in bet_sizes)
            or len(set(bet_sizes))!=len(bet_sizes)):
        raise ValueError("Expected unique positive chip bet sizes")
    if type(iterations) is not int:
        raise ValueError("Integer iterations required")
    sizes = sorted(bet_sizes)
    a,v,pairs,_,mass,p,bb = prepare(dict(game,bet_chips=max(sizes)),iterations)
    result = optimize(pairs,len(a),len(v),[b/p for b in sizes],iterations,target)
    marg = [0.] * len(a)
    for i,j,w,q,c in pairs:
        marg[i] += w
    rows = []
    for i,(cards,weight) in enumerate(a):
        if not marg[i]:
            continue
        rows.append(dict(cards=list(cards),actions=[
            dict(action="check" if s==0 else "bet",extra_chips=b,
                 frequency=result["hero_policy"][i][s],
                 ev_bb=result["weighted_action_values"][i][s]*p/bb/marg[i])
            for s,b in enumerate([0]+sizes)]))
    return dict(**result,hero_strategy=rows,bet_sizes=sizes,
                opponent_holdings=[list(h) for h,w in v],
                legal_joint_weight=mass,legal_joint_deals=len(pairs),
                nash_gap_bb=result["gap"]*p/bb,variant=5,
                scope="HU river; check forces showdown; multiple bet sizes; fold/call; zero rake",
                gto_solution=False,production_strategy_authorized=False,
                range_assumptions_verified=False,video_verified=False)


def selftest():
    # A guaranteed winner cannot improve over check if villain always folds.
    for q,expected in [(1.,1.),(0.,0.),(.5,.5)]:
        r=optimize([(0,0,1.,q,q)],1,1,[.5,1.],2000,.01)
        assert r["gap"] <= .01
        assert abs(r["value"]-expected) <= .01
        assert abs(sum(r["hero_policy"][0])-1)<1e-12
    # Private information: equally likely nuts and air against one bluff catcher.
    r=optimize([(0,0,.5,1.,1.),(1,0,.5,0.,0.)],2,1,[.5,1.],10000,.01)
    assert r["gap"]<=.01
    assert r["lower"]<=r["value"]+1e-9<=r["upper"]+2e-9
    print("Restricted multi-size CFR+ analytical checks passed")


if __name__ == "__main__":
    selftest()
