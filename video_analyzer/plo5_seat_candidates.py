"""Offline dealer marker candidates and conditional seat order for 1504x696 PLO5."""
import cv2
import numpy as np
from plo5_mixed_money import STARTS, detect

SEATS=('top','upper_right','lower_right','hero_bottom','lower_left','upper_left')
CENTERS={'pppoker':((235,132),(292,244),(292,443),(145,548),(86,443),(86,244)),
         'suprema':((224,95),(304,203),(304,423),(143,527),(75,423),(75,203))}
# Small grayscale dealer glyphs, not avatars, taken from two calibration frames.
GLYPHS={
'pppoker':'5f5f7986aaecf2f1eccd8b80615f6a8998d7ebeee6e7e9eae9b3877f86c1e4f1ee827b7997b5edf2d48f88e3e4e3d92e2b2a212441e6ebb68ee2e0e5b03455d9c13526bee4b88ee2dfe5992d86eee7542f9ee7b88ee2dfed6332bce9e95a35cae5b58ee2dff05031c9eeac474be6dfb391ddd8d54441606a4936bbe0dfb888dfe0c03a403f3b61bee1deecac7592c9e0d6d8dbd9e8eaddd5af9c446597b3eaedf1f4f1efbd9e7365473f517cabc0dee0d7baa760443d554e42456d90b6c1ad8851414855',
'suprema':'252a2de0b69cddf9ebb59ff04e24213df196fbfefbfbfffcfbcbce7120f4a8fffbfffdfcfafffafdecdcad82fcff481916171b1ebbfdfcc2f3e4ffff502120281f2021c1fcfbb6fefcff532027f9ff3e2432fcfb7cffffff512025fdff8e2019fffa72fefffc522428ffff8b2019fefea7ffffff53202bfdff79211ff9fff4f2fdff4e2027c1ad242266fafcbd95fcff51201f261e1f3af9feda24f7d0ffa3979a9c9aeffffcfaad2157e6ccfffffcfffdfffff799a0261f36fc70edfefcfffc76ee751f'}


def observe(image,table,cards=None):
    platform=detect(image,table)
    out={'table_id':table,'platform':platform,'dealer_seat_candidate':None,'hero_seat_candidate':None,'scores':[],'positions_verified':False,'hero_identity_verified':False,'dealt_seats':None,'hero_position':None}
    if platform not in CENTERS:return out
    a=np.asarray(image.convert('L'));glyph=np.frombuffer(bytes.fromhex(GLYPHS[platform]),np.uint8).reshape(14,14)
    for seat,(x,y) in zip(SEATS,CENTERS[platform]):
        x+=STARTS[table-1];roi=a[y-17:y+18,x-17:x+18]
        m=cv2.matchTemplate(roi,glyph,cv2.TM_CCOEFF_NORMED);_,v,_,loc=cv2.minMaxLoc(m)
        out['scores'].append({'seat':seat,'score':float(v),'center':[x-17+loc[0]+7-STARTS[table-1],y-17+loc[1]+7]})
    scores=sorted(out['scores'],key=lambda q:q['score'],reverse=True)
    if scores[0]['score']>=.75 and scores[0]['score']-scores[1]['score']>=.20:out['dealer_seat_candidate']=scores[0]['seat']
    if cards is not None and cards.get('table_id')==table and cards.get('platform')==platform and cards.get('variant')==5:
        from plo5_card_review import valid
        h=cards.get('hero_cards')
        if valid(h,(5,)):out['hero_seat_candidate']='hero_bottom'
    return out


def conditional_positions(dealer,dealt,*,standard_blinds=False):
    """Positions only for explicitly supplied dealt seats, standard blinds, live button."""
    if standard_blinds is not True or type(dealt) is not list or any(s not in SEATS for s in dealt) or len(set(dealt))!=len(dealt) or dealer not in dealt or not 2<=len(dealt)<=6:return None
    start=SEATS.index(dealer);order=[SEATS[(start+i)%6] for i in range(6) if SEATS[(start+i)%6] in dealt]
    labels={2:('BTN/SB','BB'),3:('BTN','SB','BB'),4:('BTN','SB','BB','CO'),5:('BTN','SB','BB','UTG','CO'),6:('BTN','SB','BB','UTG','HJ','CO')}[len(order)]
    return dict(zip(order,labels))
