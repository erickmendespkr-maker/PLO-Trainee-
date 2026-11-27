"""Generate reproducible restricted HU preflop policies from explicit ranges.
Offline only. No full-game GTO claim. Output model identity and coverage.
"""
import argparse,json
from contextlib import closing,nullcontext
from pathlib import Path
from plo5_pre_gto_context import normalize,need
from plo5_pre_gto_tree import VERSION as TREE_VERSION
from plo5_pre_gto_hu import prepare,solve,VERSION as SOLVER_VERSION
from plo5_pre_gto_opening import export
from plo5_pre_gto_store import connect,save,digest
from plo5_pre_gto_native import NativeEquity

def generate(db,context,*,trials=1000,seed=42,iterations=500,target=.01,
             pair_limit=256,node_limit=2000,max_work=20000000,sizings=(),
             native=None,threads=2,check_every=50):
    c=normalize(context)
    need(set(c["stacks"])=={"SB","BB"} and not c["history"],"HU root required")
    need(c["rake_bps"]==c["rake_cap"]==0 and not c["rake_on_fold"],"Zero rake only")
    need(c["tree_version"]==TREE_VERSION and c["continuation_version"]=="showdown_only_v1","Model version mismatch")
    rows,pairs=prepare([c["ranges"][p] for p in ("SB","BB")],trials=trials,seed=seed,
                       pair_limit=pair_limit,native=native,threads=threads,reuse_symmetry=True)
    mapping={p:[list(h) for h,w in r] for p,r in zip(("SB","BB"),rows)}
    report=solve(c["stacks"],c["sb"],c["bb"],pairs,iterations=iterations,target=target,
                 node_limit=node_limit,max_work=max_work,sizings=sizings,check_every=check_every)
    manifest=dict(solver=SOLVER_VERSION,equity_backend="native" if native else "python",
                  trials_per_pair=trials,seed=seed,joint_symmetry=True,pairs_sha256=digest(pairs),
                  legal_pairs=len(pairs),sizings=list(sizings),target_bb=target)
    openings=export(report,hu_holdings=mapping)
    model=save(db,context,report,hu_holdings=mapping,source_manifest=manifest)
    return dict(variant=5,model=model,manifest=manifest,opening=openings,
                nash_gap_bb=report["nash_gap_bb"],target_reached=report["target_reached"],
                iterations=report["iterations"],scope=report["scope"],gto_solution=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("context");p.add_argument("database");p.add_argument("--native")
    p.add_argument("--trials",type=int,default=1000);p.add_argument("--iterations",type=int,default=500)
    p.add_argument("--seed",type=int,default=42)
    a=p.parse_args()
    c=json.loads(Path(a.context).read_text(encoding="utf-8"))
    with closing(connect(a.database)) as db:
        with (NativeEquity(a.native) if a.native else nullcontext(None)) as native:
            result=generate(db,c,trials=a.trials,iterations=a.iterations,seed=a.seed,native=native)
    print(json.dumps(result,allow_nan=False))
if __name__=="__main__":main()
