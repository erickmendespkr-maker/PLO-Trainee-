"""Offline Suprema PLO5 card-slot and suit candidates for 1504x696 recordings.
No rank recognition or verified card/hand claims in this profile.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
from PIL import Image
from plo5_mixed_money import STARTS, detect
from plo5_fourcolor_cards import ink, signature

HERO_X=(225,242,258,275,292)
BOARD_X=(67,117,167,217,267)


def regions(image,table,field,i):
    if image.size!=(1504,696) or type(table) is not int or not 1<=table<=4 or field not in ('hero','board') or type(i) is not int or not 0<=i<5:
        raise ValueError('Unsupported Suprema card geometry')
    x=STARTS[table-1]+(HERO_X if field=='hero' else BOARD_X)[i]
    y=546 if field=='hero' else 253
    if field=='hero':
        return image.crop((x+2,y+2,x+16,y+17)),image.crop((x+2,y+18,x+15,y+29))
    return image.crop((x+2,y+2,x+22,y+23)),image.crop((x+2,y+23,x+15,y+34))


def felt(im):
    pixels=list(im.convert('RGB').getdata())
    return sum(b>=g+10 and g>=r+5 and 30<=b<=145 for r,g,b in pixels)/len(pixels)


def feature(image,table,field,i):
    rank,suit=regions(image,table,field,i)
    a,mask,bg=ink(rank);b,_,bs=ink(suit)
    empty=field=='board' and felt(rank)>.85 and felt(suit)>.85
    return a,b,signature(mask,rank.size),bg,bs,empty


def classify(image,table,field,i):
    a,b,sig,bg,bs,empty=feature(image,table,field,i)
    out={'rank':None,'card':None,'suit':None,'status':'uncertain','rank_color':a,'symbol_color':b}
    if empty:out['status']='felt_empty_candidate'
    elif a is not None and a==b and sig is not None and bg>.25 and bs>.30:
        out.update(suit=b,status='suit_candidate_unverified')
    return out


def observe(image,table):
    platform=detect(image,table)
    out={'table_id':table,'variant':5,'platform':platform,'hero_slots':[],'board_slots':[],'hero_cards':None,'board_cards':None,'cards_verified':False}
    if platform!='suprema':return out
    for f in ('hero','board'):
        out[f+'_slots']=[classify(image,table,f,i) for i in range(5)]
    return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('frame');a=p.parse_args(argv)
    raw=Path(a.frame).read_bytes()
    with Image.open(io.BytesIO(raw)) as im:
        rgb=im.convert('RGB');tables=[observe(rgb,i) for i in range(1,5)]
    print(json.dumps({'status':'SUPREMA_SUIT_CANDIDATES_ONLY','variant':5,'frame_sha256':hashlib.sha256(raw).hexdigest(),'tables':tables,'cards_verified':False},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
