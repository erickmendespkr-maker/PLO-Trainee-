"""Resumable preparation of the canonical PLO5 catalog, not independent GTO solves."""
import sqlite3
import subprocess
from pathlib import Path
from itertools import permutations

TOTAL=134459
MASS=2598960
VERSION="canonical-index-v1-preflop"

def connect(path):
    db=sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS pre_gto_catalog_meta(version TEXT PRIMARY KEY,next_id INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS pre_gto_catalog(id INTEGER PRIMARY KEY,mask INTEGER UNIQUE NOT NULL,multiplicity INTEGER NOT NULL);
    """)
    with db:
        db.execute("INSERT OR IGNORE INTO pre_gto_catalog_meta VALUES(?,0)",(VERSION,))
    return db

def validate(line,expected):
    parts=list(map(int,line.split()))
    if len(parts)!=7:raise ValueError("Invalid catalog row")
    i,m,*h=parts
    if i!=expected or len(set(h))!=5 or any(not 0<=c<52 for c in h):
        raise ValueError("Invalid catalog identity")
    orbit={sum(1<<(4*(c//4)+p[c%4]) for c in h) for p in permutations(range(4))}
    if m!=len(orbit):raise ValueError("Invalid multiplicity")
    columns=sorted(tuple(int(4*r+s in h) for r in range(13)) for s in range(4))
    if any(int(4*r+s in h)!=columns[s][r] for r in range(13) for s in range(4)):
        raise ValueError("Noncanonical holding")
    return i,sum(1<<c for c in h),m

def progress(db):
    cursor=db.execute("SELECT next_id FROM pre_gto_catalog_meta WHERE version=?",(VERSION,)).fetchone()[0]
    count,mass,lo,hi=db.execute("SELECT COUNT(*),COALESCE(SUM(multiplicity),0),MIN(id),MAX(id) FROM pre_gto_catalog").fetchone()
    if count!=cursor or not 0<=cursor<=TOTAL or (count and (lo!=0 or hi!=count-1)):
        raise ValueError("Checkpoint/catalog mismatch")
    if cursor==TOTAL and mass!=MASS:raise ValueError("Physical mass mismatch")
    return dict(prepared_classes=count,remaining_classes=TOTAL-count,physical_mass=mass,
                catalog_complete=count==TOTAL,gto_solved_classes=None,gto_solution=False)

def advance(db,executable,*,batch_size=1024,timeout=120):
    if type(batch_size) is not int or not 1<=batch_size<=8192:raise ValueError("Invalid batch size")
    state=progress(db);start=state["prepared_classes"];count=min(batch_size,TOTAL-start)
    if not count:return state
    p=Path(executable).resolve(strict=True)
    r=subprocess.run([str(p),str(start),str(count)],capture_output=True,text=True,check=True,timeout=timeout)
    lines=r.stdout.splitlines()
    if len(lines)!=count:raise ValueError("Incomplete catalog batch")
    rows=[validate(line,start+i) for i,line in enumerate(lines)]
    db.execute("BEGIN IMMEDIATE")
    try:
        if progress(db)["prepared_classes"]!=start:raise ValueError("Concurrent checkpoint update")
        db.executemany("INSERT INTO pre_gto_catalog VALUES(?,?,?)",rows)
        db.execute("UPDATE pre_gto_catalog_meta SET next_id=? WHERE version=?",(start+count,VERSION))
        state=progress(db)
        db.commit()
    except BaseException:
        db.rollback();raise
    return state

def main():
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("database");p.add_argument("executable");p.add_argument("--batch-size",type=int,default=1024)
    p.add_argument("--batches",type=int,default=1)
    a=p.parse_args()
    if not 1<=a.batches<=1000:p.error("Invalid batch count")
    db=connect(a.database)
    try:
        for _ in range(a.batches):
            state=advance(db,a.executable,batch_size=a.batch_size)
            if state["catalog_complete"]:break
        print(json.dumps(state))
    finally:db.close()
if __name__=="__main__":main()
