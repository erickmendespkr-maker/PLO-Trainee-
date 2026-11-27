"""Versioned sizing and rake rules for the restricted preflop solver.
Rake is a declared model, not a claim about a poker room's actual rules.
"""
from plo5_pre_gto_context import need, integer
from plo5_pre_gto_tree import bounds, actions

VERSION="pre-gto-rules-v1"

def rake_config(bps=0,cap=0,on_fold=False):
    integer(bps);integer(cap)
    need(bps<=10000 and type(on_fold) is bool,"Invalid rake settings")
    return dict(bps=bps,cap=cap,on_fold=on_fold)

def rake_amount(contested,config,fold_terminal=False):
    integer(contested)
    return 0 if fold_terminal and not config["on_fold"] else min(config["cap"],contested*config["bps"]//10000)

def sized_actions(state,absolute=(),pot_bps=()):
    """Fraction of pot after calling, added to call; round down to chip.
    Minimum and maximum remain included; illegal intermediate sizes omitted.
    """
    b=bounds(state)
    need(type(pot_bps) in (tuple,list) and len(pot_bps)<=32,"Invalid sizing list")
    c=b["to_call"]
    amounts=list(absolute)
    for f in pot_bps:
        integer(f,1);need(f<=10000,"Pot limit exceeded")
        amounts.append(c+(b["pot"]+c)*f//10000)
    return actions(state,amounts)

def selftest():
    from plo5_pre_gto_tree import start
    s=start({"SB":200,"BB":200},1,2)
    assert sized_actions(s,pot_bps=(5000,7500,10000))==(("fold",0),("call",1),("raise",3),("raise",4),("raise",5))
    c=rake_config(500,3)
    assert rake_amount(100,c)==3 and rake_amount(100,c,True)==0
    assert rake_amount(20,rake_config(500,3,True),True)==1
    print("Sizing and rake checks passed")

if __name__=="__main__":selftest()
