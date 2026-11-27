"""Offline SQLite store for restricted PLO5 solver artifacts.
Content-addressed model identity includes actual report and declared context.
Physical hands use a 52-bit mask; class signature is an index, not a substitute
for a physical policy. No interpolation or GTO certification.
"""
import hashlib
import json
import sqlite3
import struct
from math import isfinite
from plo5_pre_gto_context import identity, cards, need
from plo5_pre_gto_response import export
from plo5_pre_gto_opening import canonical
from plo5_pre_gto_equity import DECK

VERSION="pre-gto-store-v1"
CARD_ID={c:i for i,c in enumerate(DECK)}

def dump(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False)

def digest(x):
    return hashlib.sha256(dump(x).encode()).hexdigest()

def mask(hand):
    return sum(1<<CARD_ID[c] for c in cards(hand))

def connect(path):
    db=sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS pre_gto_models(
        model TEXT PRIMARY KEY, context_key TEXT NOT NULL, metadata TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS pre_gto_nodes(
        model TEXT NOT NULL REFERENCES pre_gto_models(model), node INTEGER NOT NULL,
        history TEXT NOT NULL, position TEXT NOT NULL, actions TEXT NOT NULL,
        PRIMARY KEY(model,node), UNIQUE(model,history));
    CREATE TABLE IF NOT EXISTS pre_gto_policies(
        model TEXT NOT NULL, node INTEGER NOT NULL, holding INTEGER NOT NULL,
        class_key TEXT NOT NULL, frequencies BLOB NOT NULL, ev BLOB,
        PRIMARY KEY(model,node,holding),
        FOREIGN KEY(model,node) REFERENCES pre_gto_nodes(model,node));
    CREATE INDEX IF NOT EXISTS pre_gto_class ON pre_gto_policies(model,node,class_key);
    """)
    return db

def pack(values):
    return struct.pack("<"+"d"*len(values),*values)

def unpack(blob,n):
    need(len(blob)==8*n,"Corrupt numeric vector")
    return list(struct.unpack("<"+"d"*n,blob))

def save(db,context,report,*,hu_holdings=None,source_manifest):
    ident=identity(context)
    need(not context["history"],"Root context required for full-tree import")
    need(type(source_manifest) is dict and source_manifest,"Explicit source manifest required")
    # Replay legal tree and preserve physical policy; report is not certified.
    data=export(report,context["stacks"],context["sb"],context["bb"],hu_holdings=hu_holdings)
    declared_rake=dict(bps=context["rake_bps"],cap=context["rake_cap"],on_fold=context["rake_on_fold"])
    need(report.get("rake",dict(bps=0,cap=0,on_fold=False))==declared_rake,"Rake mismatch")
    metadata=dict(schema=VERSION,context_key=ident["key"],source_manifest=source_manifest,
                  report_sha256=digest(report),hu_mapping_sha256=digest(hu_holdings),
                  solver_version=report.get("version"),gap_bb=data["source_gap_bb"],
                  target_reached=data["source_target_reached"],gto_solution=False)
    model=digest(metadata)
    by_hand={}
    for row in report["policy"]:
        h=row["holding"]
        if type(h) is int:h=hu_holdings[row["position"]][h]
        by_hand[row["node"],mask(h)]=row
    with db:
        old=db.execute("SELECT metadata FROM pre_gto_models WHERE model=?",(model,)).fetchone()
        if old is not None:
            need(old[0]==dump(metadata),"Model identity collision")
            return model
        db.execute("INSERT INTO pre_gto_models VALUES(?,?,?)",(model,ident["key"],dump(metadata)))
        for node in data["decisions"]:
            n=node["node"];p=node["position"];aa=node["actions"]
            db.execute("INSERT INTO pre_gto_nodes VALUES(?,?,?,?,?)",
                       (model,n,dump(node["history"]),p,dump(aa)))
            for row in node["physical_policies"]:
                h=mask(row["cards"])
                raw=by_hand[n,h]["actions"]
                vals=[a.get("ev_bb") for a in raw]
                need(all(v is None or type(v) in (int,float) and isfinite(v) for v in vals),"Invalid EV")
                # NaN sentinel in binary only; decoded as missing, never zero.
                ev=pack([float("nan") if v is None else v for v in vals]) if any(v is not None for v in vals) else None
                db.execute("INSERT INTO pre_gto_policies VALUES(?,?,?,?,?,?)",
                           (model,n,h,canonical(row["cards"]),pack(row["frequency"]),ev))
    return model

def lookup(db,model,history,hand):
    row=db.execute("SELECT node,position,actions FROM pre_gto_nodes WHERE model=? AND history=?",
                   (model,dump(history))).fetchone()
    if row is None:return dict(status="UNSOLVED_CONTEXT",gto_solution=False)
    n,p,raw=row;aa=json.loads(raw)
    found=db.execute("SELECT frequencies,ev FROM pre_gto_policies WHERE model=? AND node=? AND holding=?",
                     (model,n,mask(hand))).fetchone()
    if found is None:return dict(status="UNSOLVED_HOLDING",position=p,gto_solution=False)
    f=unpack(found[0],len(aa))
    need(all(isfinite(v) and 0<=v<=1 for v in f) and abs(sum(f)-1)<1e-8,"Corrupt frequencies")
    ev=unpack(found[1],len(aa)) if found[1] is not None else [None]*len(aa)
    return dict(status="RESTRICTED_POLICY",position=p,gto_solution=False,
                actions=[dict(a,frequency=x,ev_bb=y if y is not None and isfinite(y) else None) for a,x,y in zip(aa,f,ev)])

def selftest():
    h=["As","Kd","Qh","Jc","Ts"]
    assert mask(h)==mask(h[::-1])
    assert unpack(pack([.25,.75]),2)==[.25,.75]
    db=connect(":memory:")
    assert lookup(db,"absent",[],h)["status"]=="UNSOLVED_CONTEXT"
    db.close()
    print("Store primitive checks passed")

if __name__=="__main__":selftest()
