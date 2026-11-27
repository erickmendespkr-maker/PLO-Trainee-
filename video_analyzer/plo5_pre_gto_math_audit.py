"""Analytic oracle tests for restricted HU solver; synthetic equity inputs."""
from plo5_pre_gto_hu import solve

def run():
    cases=0
    for i in range(21):
        q=i/20
        r=solve({"SB":2,"BB":2},1,2,[(0,0,1,q)],iterations=500)
        root=r["policy"][0]["actions"]
        a={x["action"]:x for x in root}
        expected=max(-.5,2*q-1)
        assert abs(a["fold"]["ev_bb"])<1e-10
        assert abs(a["call"]["ev_bb"]-(2*q-.5))<1e-10
        assert r["best_response_lower_bb"]-1e-10<=expected<=r["best_response_upper_bb"]+1e-10
        assert abs(r["value_sb_bb"]-expected)<.01
        assert r["nash_gap_bb"]<.01
        cases+=1
    # Private SB holding matters. BB is all-in: no opponent action.
    r=solve({"SB":2,"BB":2},1,2,[(0,0,1,.1),(1,0,3,.8)],iterations=500)
    expected=(-.5+3*.6)/4
    assert abs(r["value_sb_bb"]-expected)<.01
    for row in r["policy"]:
        a={x["action"]:x for x in row["actions"]}
        assert a["call"]["frequency"]<.01 if row["holding"]==0 else a["call"]["frequency"]>.99
    cases+=1
    print("PASS",cases,"analytic HU fixtures")
    return cases

if __name__=="__main__":run()
