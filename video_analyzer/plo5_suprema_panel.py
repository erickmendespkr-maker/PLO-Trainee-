"""Offline fixed-layout Suprema panel candidates; not account identity proof."""
from statistics import median
from plo5_mixed_money import STARTS
from plo5_pre_gto_context import need


def panel(image,table):
    need(image.size==(1504,696) and image.mode=='RGB' and type(table) is int and 1<=table<=4,'Invalid panel geometry')
    x=STARTS[table-1]
    def white(p):return min(p)>185 and max(p)-min(p)<25
    # Four positive border segments; do not equate an absent marker with vacancy.
    scores=[sum(white(p) for p in image.crop((x+a,b,x+c,d)).getdata()) for a,b,c,d in ((155,584,223,585),(155,611,223,612),(155,585,156,612),(222,585,223,612))]
    seated=scores[0]>=48 and scores[1]>=60 and scores[2]>=23 and scores[3]>=23
    colors=[tuple(median(v[i] for v in image.crop((x+a,650,x+a+8,656)).getdata()) for i in range(3)) for a in (17,142,264)]
    (r,g,b),(r2,g2,b2),(r3,g3,b3)=colors
    turn=seated and r>=g+70 and r>=b+70 and g2>=r2+60 and g2>=b2+20 and r3>=g3+30 and g3>=b3+70
    return dict(seated_panel_candidate=seated,hero_turn_candidate=bool(turn),border_counts=scores,profile='suprema-1504x696-panel-v1',identity_verified=False,actor_verified=False)
