"""Original CFR/CFR+ kernel for the existing restricted HU PLO5 river model.
No full-tree GTO, no inferred ranges. Payoffs are expressed in pot units.
"""
import math


def policies(regrets):
    result=[]
    for a,b in regrets:
        a,b=max(a,0.),max(b,0.)
        result.append(b/(a+b) if a+b else .5)
    return result


def utilities(pairs,x,y,na,nv):
    a=[[0.,0.] for _ in range(na)];v=[[0.,0.] for _ in range(nv)]
    for i,j,w,c,q in pairs:
        a[i][0]+=w*c;a[i][1]+=w*(1-y[j]+y[j]*q)
        v[j][0]+=w*x[i];v[j][1]+=w*x[i]*q
    return a,v


def certificate(pairs,x,y,na,nv):
    a,v=utilities(pairs,x,y,na,nv)
    value=sum((1-x[i])*c+x[i]*b for i,(c,b) in enumerate(a))
    upper=sum(max(c,b) for c,b in a)
    lower=sum((1-x[i])*c for i,(c,b) in enumerate(a))+sum(min(f,c) for f,c in v)
    if not all(math.isfinite(z) for z in (value,upper,lower)) or not lower-1e-10<=value<=upper+1e-10:
        raise ValueError('Invalid best-response bounds')
    return {'value':value,'lower':lower,'upper':upper,'gap':max(0.,upper-lower)}


def optimize(pairs,na,nv,*,iterations=10000,algorithm='cfr_plus',target=.01,check_every=50):
    if (type(na) is not int or type(nv) is not int or not 1<=na<=128 or not 1<=nv<=128
            or type(iterations) is not int or not 1<=iterations<=50000
            or type(check_every) is not int or not 1<=check_every<=1000
            or type(target) not in (float,int) or not math.isfinite(target) or not 0<=target<=1
            or algorithm not in ('vanilla','cfr_plus')):
        raise ValueError('Invalid solver configuration')
    if type(pairs) not in (tuple,list) or not 1<=len(pairs)<=4096 or iterations*len(pairs)>4000000:
        raise ValueError('Invalid pairing budget')
    seen=set()
    for i,j,w,c,q in pairs:
        if (type(i) is not int or type(j) is not int or not 0<=i<na or not 0<=j<nv or (i,j) in seen
                or any(type(z) not in (int,float) or not math.isfinite(z) for z in (w,c,q))
                or w<=0 or c not in (0,.5,1) or not -1<=q<=2):
            raise ValueError('Invalid weighted pair')
        seen.add((i,j))
    if not math.isclose(sum(p[2] for p in pairs),1.,rel_tol=0,abs_tol=1e-10):
        raise ValueError('Pair weights must sum to one')
    ra=[[0.,0.] for _ in range(na)];rv=[[0.,0.] for _ in range(nv)]
    sa=[0.]*na;sv=[0.]*nv;total=0
    for t in range(1,iterations+1):
        x,y=policies(ra),policies(rv);a,v=utilities(pairs,x,y,na,nv)
        weight=t if algorithm=='cfr_plus' else 1;total+=weight
        for i,(c,b) in enumerate(a):
            u=(1-x[i])*c+x[i]*b
            ra[i][0]+=c-u;ra[i][1]+=b-u;sa[i]+=weight*x[i]
            if algorithm=='cfr_plus':ra[i]=[max(z,0.) for z in ra[i]]
        for j,(f,c) in enumerate(v):
            u=(1-y[j])*f+y[j]*c
            rv[j][0]+=u-f;rv[j][1]+=u-c;sv[j]+=weight*y[j]
            if algorithm=='cfr_plus':rv[j]=[max(z,0.) for z in rv[j]]
        if t%check_every==0 or t==iterations:
            ax=[z/total for z in sa];ay=[z/total for z in sv]
            cert=certificate(pairs,ax,ay,na,nv)
            if cert['gap']<=target or t==iterations:break
    return {'algorithm':algorithm,'iterations':t,'target_gap_fraction_of_pot':target,
            'target_reached':cert['gap']<=target,'hero_bet_probabilities':ax,'opponent_call_probabilities':ay,
            **cert,'gto_solution':False,'scope':'restricted_river_game_only'}


def solve_prepared(game,*,iterations=10000,algorithm='cfr_plus',target=.01,check_every=50):
    """Adapter to the existing PLO5 prepare() validator; does not modify its solver."""
    from plo5_river_solver import prepare
    a,v,pairs,input_mass,mass,p,bb=prepare(game,iterations)
    result=optimize(pairs,len(a),len(v),iterations=iterations,algorithm=algorithm,target=target,check_every=check_every)
    return {**result,'variant':5,'hero_holdings':[list(h) for h,w in a],
            'opponent_holdings':[list(h) for h,w in v],'legal_joint_deals':len(pairs),
            'input_joint_weight':input_mass,'legal_joint_weight':mass,
            'nash_gap_bb':result['gap']*p/bb,'video_verified':False,
            'production_strategy_authorized':False,'strategic_error_established':False}
