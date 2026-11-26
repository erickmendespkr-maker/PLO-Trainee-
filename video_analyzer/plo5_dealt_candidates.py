"""Offline visual evidence of opponent card backs and explicit vacant-seat markers."""
import base64
import cv2
import numpy as np
from plo5_mixed_money import STARTS, detect

SEATS=('top','upper_right','lower_right','lower_left','upper_left')
BACK_CENTERS={'pppoker': [(213, 118), (314, 230), (314, 429), (64, 429), (64, 230)], 'suprema': [(222, 62), (306, 169), (306, 390), (74, 390), (74, 169)]}
EMPTY_CENTERS={'pppoker': [(189, 118), (337, 230), (337, 429), (41, 429), (41, 230)], 'suprema': [(189, 95), (333, 202), (333, 423), (42, 423), (42, 202)]}
BACK_GLYPHS={'pppoker': ['kIFZ1ntvV8GGcXtze4lug4dsa9Jzcr19dW92hm94eIiUdmO1b2LWcn+NcXxuf3lxiWWKimhvtHKBh2+BhmyAe4pzzmds0WqGfXJtf4R8iHOQatZuXNR5dHJ/gYZveXt6hFfWZoOecoGChm9ugHuAbo5dx2HUc4V8dnJ/fX9vfXt8ZqBV0Gp/fXJ/gW94f3p6fKR1oot/cYBygoZ4dH91fHrWYtV1gW+BgHJ8eI17eXhtyVPEb32CdXhvgnmAcnaK', 'Wth7bYKXgl/VZXpzgHaGfFrWbXLQa29r2G6AdIh4cYFl13du2Ht7i517jXRxfXmBZtBtaNJnadVrcnR7eo55eV3Sf1jRgVrMhn+AeHx1gn1hz3FosnOrl4Bzdnp/gHGBYdhkmX1a0Gh1fYCAcX+AgFzUZtRrZ7t0e4BzfXZ9bm9czVrRXdR6eIp7dX15cYGDV85hyl3WeXp7dXKNfX19cVbJXLV4q4B4bY+DfHOCgHVcw22D1HFsjXl9dnSDbnxv', 'ZNRwdtNub3W7c4OCeHhzhGbWaGrUbm7OfYJ1fW6Cg39e13Jl2HJkz3V7hnKAbHZzZ9V2Xr19baeHc4hvgIR5fF/SaHiYZ9Vsg3J/hnGBcotc1GHAe17RcXyEdYZzgHRzXM9e0GCNlnN5hnF8gHR4clnKYdJkz3d+h3F2eIF4i3FaylzLYMuBdHZ2eIhvf3x2UMZdoq6FcXmCi3F4goN5dmzDiHnPdoOCc3d2fXZ1gHqIus5YvG2DhmyCiHKCeoZz'], 'suprema': ['l6Ke7VkzpKJf7TZmop3uS0GfoZ1lMTJhpKPxZTJmpYfdOWSDXOuNZ5ijYe1HK19lYelGNmBk7Do1Z0Cv6jllaWfq6+oqMWRD8S9hPOvqnTs06+ujZDk96+xj6jpmOu3tbFQ77eo5ZzW76zk4VursrDSj62Q4fe6AO2o16UdkZFHqOmM5NGfu6+3rM2dL6mY1Y1zqTmdf6mVuY2Q0OehDKOw4ZGDmZzeYjes9XqPnT0GSn2dm69/t7jRgoOk5M5+H5zydmeuBaqCiZDt/6us4Nmie5zw/j+o5OmZ15zlka51kOTHUP3MzXWTsLkhh7KpRZuuIP2RkY2dkKDZxbz9CYOxXoKrpYWRm6GNjhkpkY2RLPDg7', 'ZmVhX+03c6Kg7Fc2pJ2f7Z5keGVgLjxRpJ+S7TNupKDpTjWco5TwO2Wknl9jVzWgn5ftNmSdiexXT2Oi3o84Zp+maDsqOWWhXu03ZWY67HtjZVDrVTVoo2Hs7C05ZGnM7DdpPNzuNT875Os2Yztq6ezt62BkOdntZDntyOlfNum952U7b+3pNl/sPzbn3+o0YzmPzzZjOOtKQzk77Ozq7Sw8ZDYz6zloZO1oOWNl6VBIZV5PazLK7FU1ZUPrNmad6lc1eZDnM2CBZmaj6zTsajVlleklZKHnnF2g3oc8o5+jZDbr7e1jOJuW7DWHpOk5Y6Lqn0ifn59kNursPOlAoHzrPGNh5jZjYes6X2VmZ2Q4Lztu', 'oJ9z7TRhomTpSWBkpOpmM2ain2A5Jzlln1rvOmJnNepqZWlZ6z0wY3Fm6+0oLGNg0ewyXDbS7Ek7PNnqO2M5d+ns7us6YDXR6WA57b/qYDvq5N5jOOvr7Dtp6jk/6tHpOmE64Gg4ZzjoQE4zOuPr6+5oOmU2Nes5ZGbtYzllWeVpXGZmMewsTunuO2FP6jxim+lEQ56J6Thlo2Zkve4y6u42YZHrOoWe6aNooOtSOp2io2M07OzpMTafkes4iJvqSWGC555lnqSfZzrs6ThvOKNa7ThkWew7ZmDpNmNlZ2FgOCw7b288ZF3mNVmE6aKe1tmlpotAKDlDOjhuckpjkeljP9yiOzroZjtBY21ZOCtROjk6']}
EMPTY_GLYPHS={'pppoker': 'JSomJycoKCgoJycnJycnJycoJyUlJyonJyYmJiYnJycnJycnJygnJSQgR0Q6IyMjIycnJycnJycnKCclIUukY0sjLB4tJCojLSB1SiYqJyghRK1YKKyQyJW6TbaHcZKAsSWxJh9JnVYnvR+4IKNXhg+jdUFXdJghHkeYXESvI70mnVSnX55/eCPSOScfLlFVSD8TOhcyQpdQIzFVE6coJygrJyolJiYnJiYyUSEmJSGDVComKiooJicqKCgoJiQfICQmKCMiKCg=', 'suprema': 'PTwnKCcrKCwsKC0rLCknKysuKysmKysrKSkoKUE9OywnKCcrJygnLCgpJycpKSwoKCcoKyYmJyYpJzg7QFYnKCcrWSgzUSklJ1ZXV1VYJVYoKClJU1MpLCw7QPgnKCcr1inv+ScmJyUmJmK9JfolJ9bOJZ72JSU5M52JJCTEZCbonSUnIiYlIu0lJvwmbmwiJCIy8iY5MSb9IiT6JW9tLu0lISUl9SsiIv8ixScmJSIk+yM9LB/lOWyLIPshIP8nHyHJOSEiIP0fyyUgIiId/CE8MSY+u+QwRcdsbm90IXqYHyIgIvsgeWceICAh8iE1Mx8g++0iqz0fICH5SN4gHiAgIv8fIeaHH2vuJBwsLR8egkUfnSEfHiGMfJ6gnp+fIZ0hHyByn44hHyAnJyQeHSAdICQfHR0bHx4fHR4eGx8fHSAgHh0eICojJiohIR0fIB8fJCIgHR8fHR4eHx0hIB4aHR8dHi0j'}

BACK_SIZE={'pppoker':(12,16),'suprema':(12,23)}
EMPTY_SIZE={'pppoker':(10,20),'suprema':(12,30)}
BACK_MIN=.55
EMPTY_MIN=.85


def template(encoded,shape):
    return np.frombuffer(base64.b64decode(encoded),np.uint8).reshape(shape)


def score(a,g,x,y,dx,dy):
    roi=a[y-dy:y+dy+1,x-dx:x+dx+1]
    return float(cv2.minMaxLoc(cv2.matchTemplate(roi,g,cv2.TM_CCOEFF_NORMED))[1])


def classify(back,empty):
    if back>=BACK_MIN and empty>=EMPTY_MIN:return 'conflicting_visual_evidence'
    if back>=BACK_MIN:return 'card_backs_visible_candidate'
    if empty>=EMPTY_MIN:return 'explicit_empty_marker_candidate'
    return 'unknown'


def observe(image,table):
    if image.size!=(1504,696) or type(table) is not int or not 1<=table<=4:
        raise ValueError('Unsupported table geometry')
    platform=detect(image,table)
    out={'table_id':table,'platform':platform,'opponents':[],'dealt_roster_verified':False}
    if platform not in BACK_CENTERS:return out
    a=np.asarray(image.convert('L'));offset=STARTS[table-1]
    for i,seat in enumerate(SEATS):
        x,y=BACK_CENTERS[platform][i];u,v=EMPTY_CENTERS[platform][i]
        b=score(a,template(BACK_GLYPHS[platform][0 if i==0 else 1 if i<3 else 2],BACK_SIZE[platform]),x+offset,y,25,15)
        e=score(a,template(EMPTY_GLYPHS[platform],EMPTY_SIZE[platform]),u+offset,v,23,18)
        out['opponents'].append({'seat':seat,'status':classify(b,e),'back_score':b,'empty_score':e,'dealt_verified':False})
    return out
