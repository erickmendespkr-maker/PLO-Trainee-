"""Offline review adapter for stored restricted preflop policies.
Requires an explicit model and matching root context. Never certifies GTO errors.
"""
import json
from plo5_pre_gto_context import identity,need,cards
from plo5_pre_gto_tree import replay,bounds
from plo5_pre_gto_store import lookup

def review_policy(db,model,context,history,hero,chosen,*,position,pot,stack,to_call):
    need(context["history"]==[],"Root model context required")
    state=replay(context["stacks"],context["sb"],context["bb"],history)
    b=bounds(state)
    need((position,pot,stack,to_call)==(state.actor,state.pot,b["stack"],b["to_call"]),"Observed decision mismatch")
    need(set(chosen)=={"action","amount"},"Invalid chosen action")
    cards(hero)
    result=dict(variant=5,status="UNSOLVED_CONTEXT",gto_solution=False,
                strategic_error_established=False,conditional_ev_loss_bb=None,
                chosen_frequency=None,chosen_ev_bb=None,actions=[])
    row=db.execute("SELECT context_key,metadata FROM pre_gto_models WHERE model=?",(model,)).fetchone()
    if row is None:return result
    need(row[0]==identity(context)["key"],"Model context mismatch")
    metadata=json.loads(row[1])
    result["model"]=model
    result["model_gap_bb"]=metadata.get("gap_bb")
    result["model_target_reached"]=metadata.get("target_reached")
    policy=lookup(db,model,history,hero)
    result["status"]=policy["status"]
    if policy["status"]!="RESTRICTED_POLICY":return result
    need(policy["position"]==position,"Actor mismatch")
    aa=policy["actions"];result["actions"]=aa
    match=[a for a in aa if (a["action"],a["amount"])==(chosen["action"],chosen["amount"])]
    if not match:
        result["status"]="UNMODELED_ACTION";return result
    a=match[0];result["chosen_frequency"]=a["frequency"];result["chosen_ev_bb"]=a["ev_bb"]
    if all(x["ev_bb"] is not None for x in aa):
        result["conditional_ev_loss_bb"]=max(x["ev_bb"] for x in aa)-a["ev_bb"]
    result["status"]="RESTRICTED_POLICY_MATCH"
    result["scope"]="Conditional on stored restricted game, ranges, sizing and continuation; not verified full PLO5 GTO"
    return result
