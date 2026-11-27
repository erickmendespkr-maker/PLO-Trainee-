"""Run pre-GTO unit and integration checks from repository root."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import plo5_pre_gto_context as context
import plo5_pre_gto_tree as tree
import plo5_pre_gto_equity as equity
import plo5_pre_gto_hu as hu
import plo5_pre_gto_multiway as multi
import plo5_pre_gto_opening as opening
import plo5_pre_gto_response as response
import plo5_pre_gto_rules as rules
import plo5_pre_gto_store as store

def main():
    for m in (context,tree,equity,hu,multi,opening,response,rules,store):
        m.selftest()
    h=["As","Kd","Qh","Jc","Ts"]
    v=["2s","3d","4h","5c","6s"]
    mapping={"SB":[h],"BB":[v]}
    stacks={"SB":2,"BB":2}
    report=hu.solve(stacks,1,2,[(0,0,1,.75)],iterations=100)
    c=dict(variant=5,stacks=stacks,sb=1,bb=2,rake_bps=0,rake_cap=0,
           rake_on_fold=False,history=[],ranges={p:[dict(cards=hs[0],weight=1)] for p,hs in mapping.items()},
           tree_version=tree.VERSION,continuation_version="test-showdown")
    db=store.connect(":memory:")
    try:
        key=store.save(db,c,report,hu_holdings=mapping,source_manifest={"fixture":"synthetic equity .75"})
        assert key==store.save(db,c,report,hu_holdings=mapping,source_manifest={"fixture":"synthetic equity .75"})
        result=store.lookup(db,key,[],h)
        assert result["status"]=="RESTRICTED_POLICY"
        assert abs(next(a["ev_bb"] for a in result["actions"] if a["action"]=="call")-1)<1e-9
        assert store.lookup(db,key,[],v)["status"]=="UNSOLVED_HOLDING"
    finally:db.close()
    print("PASS restricted preflop integration")
if __name__=="__main__":main()
