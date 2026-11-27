"""Offline association of opponent label candidates and displayed stakes, not action sizes."""
import argparse,hashlib,io,json
from decimal import Decimal,InvalidOperation
from pathlib import Path
from PIL import Image
from plo5_opponent_labels import run as read_labels,need,SEATS
from plo5_blind_evidence import Reader
from plo5_mixed_money import STARTS


def positive(v):
    if type(v) is not str:return False
    try:d=Decimal(v)
    except InvalidOperation:return False
    return d.is_finite() and d>0


def associate(labels,a,b):
    need(a['table_id']==b['table_id'] and a['platform']==b['platform'],'Stake context mismatch')
    def index(obs):
        rows=obs['stakes'];m={r['seat']:r for r in rows}
        need(len(m)==len(rows) and set(m)<=set(SEATS)|{'hero_bottom'},'Invalid stake roster');return m
    x,y=index(a),index(b);out=[]
    for q in labels:
        s=q['seat'];u=x.get(s,{}).get('value_bb');v=y.get(s,{}).get('value_bb')
        same=positive(u) and u==v
        out.append({**q,'after_stake_bb':u,'peer_stake_bb':v,'displayed_stake_bb_candidate':u if same else None,
                    'association_status':'SAME_SEAT_CO_VISIBLE_CANDIDATE' if same and q['label_candidate'] is not None else 'INCONCLUSIVE',
                    'action_amount_bb':None,'action_verified':False,'amount_verified':False})
    return out


def run(root,bank):
    root=Path(root);p=root/'manifest.json';raw=p.read_bytes();m=json.loads(raw)
    labels=read_labels(root,bank);need(labels['manifest_sha256']==hashlib.sha256(raw).hexdigest(),'Manifest mismatch')
    events={e['event_id']:e for e in m['events']};reader=Reader();rows=[]
    for row in labels['rows']:
        i,t,k=row['event_id'],row['table_id'],row['platform'];e=events[i]
        def stake(key):
            entry=e[key];name=f'prints/{i:04}_{key}.png';need(entry['file']==name,'Unexpected print path');q=root/name
            need(q.is_file() and not q.is_symlink() and not q.parent.is_symlink() and q.stat().st_size<=8*2**20,'Unsafe print');data=q.read_bytes();need(hashlib.sha256(data).hexdigest()==entry['sha256'],'Print hash mismatch')
            with Image.open(io.BytesIO(data)) as im:
                need(im.size==(372,696),'Invalid crop');full=Image.new('RGB',(1504,696));full.paste(im.convert('RGB'),(STARTS[t-1],0))
            obs=reader.scan(full,t);need(obs['platform']==k and obs['table_id']==t,'Stake context mismatch');return obs
        a,b=stake('after'),stake('peer');rows.append({**row,'opponents':associate(row['opponents'],a,b)})
    need(p.read_bytes()==raw and hashlib.sha256(Path(bank).read_bytes()).hexdigest()==labels['bank_sha256'],'Input changed')
    return {**labels,'status':'CO_VISIBLE_LABEL_STAKE_CANDIDATES_ONLY','rows':rows,'stake_cache':reader.cache.stats(),'amounts_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('bank');p.add_argument('output');a=p.parse_args(argv);r=run(a.report,a.bank)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
