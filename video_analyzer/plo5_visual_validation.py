"""Compare offline PPPoker PLO5 readings with explicit, hash-bound visual annotations."""
import argparse, hashlib, io, json
from pathlib import Path
from PIL import Image
from fractions import Fraction
from plo5_fourcolor_cards import load_bank, observe as cards
from plo5_mixed_money import detect, read
from plo5_hero_actions import observe as actions
from plo5_payout_display import Reader as PayoutReader
from plo5_blind_evidence import Reader as StakeReader

FIELDS={'hero_cards','board_cards','stack','pot','hero_label','hero_stake','payout_top'}

def need(ok,msg):
    if not ok:raise ValueError(msg)

def digest(data):return hashlib.sha256(data).hexdigest()

def compare(expected,actual):
    if expected==actual:return 'correct'
    if actual is None:return 'abstained'
    if expected is None:return 'false_positive'
    return 'wrong'

def run(root,annotations,bank_path):
    root=Path(root);p=root/'manifest.json';raw=p.read_bytes();m=json.loads(raw)
    ap=Path(annotations);araw=ap.read_bytes();a=json.loads(araw)
    need(a['variant']==5 and a['platform']=='pppoker' and a['source_sha256']==m['source_sha256'] and a['manifest_sha256']==digest(raw),'Annotation binding mismatch')
    t=a['table_id'];need(type(t) is int and 1<=t<=4,'Invalid table')
    bank_hash=digest(Path(bank_path).read_bytes());bank=load_bank(bank_path);pr=PayoutReader();sr=StakeReader()
    frames={f['file']:f for f in m['frames']};need(len(frames)==len(m['frames']),'Duplicate manifest frames');out=[];seen=set();prev=None
    for label in a['anchors']:
        name=label['file'];need(name in frames and name not in seen and Path(name).name==name,'Invalid anchor');seen.add(name);f=frames[name]
        pts=Fraction(f['pts']);need(label['pts']==f['pts'] and label['sha256']==f['sha256'] and (prev is None or pts>prev),'Anchor mismatch');prev=pts
        expected=label['expected'];need(type(expected) is dict and bool(expected) and set(expected)<=FIELDS,'Invalid fields')
        q=root/name;need(q.is_file() and not q.is_symlink() and q.stat().st_size<=8*2**20,'Invalid print');data=q.read_bytes();need(digest(data)==f['sha256'],'Print changed')
        with Image.open(io.BytesIO(data)) as im:im=im.convert('RGB')
        need(im.size==(1504,696),'Invalid geometry');actual={k:None for k in expected}
        if detect(im,t)=='pppoker':
            if set(expected)&{'hero_cards','board_cards'}:
                c=cards(im,t,bank)
                for k in set(expected)&{'hero_cards','board_cards'}:actual[k]=c[k]
            for k in set(expected)&{'stack','pot'}:actual[k]=read(im,t,'pppoker',k)['value_bb']
            if 'hero_label' in expected:actual['hero_label']=actions(im,t)['hero_action_candidate']
            if 'hero_stake' in expected:actual['hero_stake']=next((v['value_bb'] for v in sr.scan(im,t)['stakes'] if v['seat']=='hero_bottom'),None)
            if 'payout_top' in expected:actual['payout_top']=next((v['displayed_plus_bb'] for v in pr.scan(im,t) if v['seat']=='top'),None)
        out.append({'file':name,'pts':f['pts'],'expected':expected,'actual':actual,'results':{k:compare(v,actual[k]) for k,v in expected.items()}})
    need(p.read_bytes()==raw and ap.read_bytes()==araw and digest(Path(bank_path).read_bytes())==bank_hash,'Input changed')
    totals={}
    for row in out:
        for field,status in row['results'].items():
            c=totals.setdefault(field,dict.fromkeys(('correct','abstained','false_positive','wrong'),0));c[status]+=1
    return {'variant':5,'status':'VISUAL_ANNOTATION_COMPARISON_ONLY','source_sha256':m['source_sha256'],'annotation_sha256':digest(araw),'bank_sha256':bank_hash,'table_id':t,'anchors':out,'totals':totals,'independent_validation':False,'hands_reconstructed':False,'financial_result_verified':False}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('annotations');p.add_argument('bank');p.add_argument('output');a=p.parse_args(argv);r=run(a.report,a.annotations,a.bank)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
