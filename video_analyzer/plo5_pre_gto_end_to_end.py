"""End-to-end offline preflop smoke test with real cards and synthetic betting context.
No video evidence and no full-game GTO certification.
"""
import json
from contextlib import closing
from plo5_pre_gto_tree import VERSION
from plo5_pre_gto_generate import generate
from plo5_pre_gto_store import connect
from plo5_pre_gto_review import review_policy

def run():
    hero=["As","Kd","Qh","Jc","Ts"]
    opponent=["2s","3d","4h","5c","6s"]
    context=dict(variant=5,stacks={"SB":2,"BB":2},sb=1,bb=2,
        rake_bps=0,rake_cap=0,rake_on_fold=False,history=[],
        ranges={"SB":[dict(cards=hero,weight=1)],"BB":[dict(cards=opponent,weight=1)]},
        tree_version=VERSION,continuation_version="showdown_only_v1")
    with closing(connect(":memory:")) as db:
        g=generate(db,context,trials=100,iterations=500)
        def review(hand,action,amount,pot=3):
            return review_policy(db,g["model"],context,[],hand,dict(action=action,amount=amount),
                                 position="SB",pot=pot,stack=1,to_call=1)
        a=review(hero,"call",1)
        assert a["status"]=="RESTRICTED_POLICY_MATCH"
        assert a["chosen_ev_bb"] is not None
        assert abs(sum(x["frequency"] for x in a["actions"])-1)<1e-8
        assert a["conditional_ev_loss_bb"]>=0
        assert not a["gto_solution"] and not a["strategic_error_established"]
        assert review(opponent,"call",1)["status"]=="UNSOLVED_HOLDING"
        assert review(hero,"raise",5)["status"]=="UNMODELED_ACTION"
        try:review(hero,"call",1,pot=4)
        except ValueError:pass
        else:raise AssertionError("Mismatched pot accepted")
        return dict(model=g["model"],scope=g["scope"],gap_bb=g["nash_gap_bb"],review=a,
                    video_verified=False,gto_solution=False)
if __name__=="__main__":print(json.dumps(run(),allow_nan=False))
