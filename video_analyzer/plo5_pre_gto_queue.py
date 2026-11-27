"""Persistent single-worker queue for restricted offline HU model generation.
Interrupted jobs are retried from the beginning, not from CFR iteration state.
"""
import json
import sqlite3
import time
import uuid
from plo5_pre_gto_context import identity,need
from plo5_pre_gto_store import dump,digest

def setup(db):
    db.execute("""CREATE TABLE IF NOT EXISTS pre_gto_jobs(
        id TEXT PRIMARY KEY, context TEXT NOT NULL, options TEXT NOT NULL,
        priority INTEGER NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        lease TEXT, expires REAL, model TEXT, error TEXT)""")
    db.commit()

def enqueue(db,context,options,priority=0):
    ident=identity(context)
    allowed={"trials","seed","iterations","target","pair_limit","node_limit","max_work","sizings","check_every"}
    need(type(options) is dict and set(options)<=allowed,"Invalid queue options")
    need(type(priority) is int and -1000<=priority<=1000,"Invalid priority")
    key=digest(dict(context=ident["key"],options=options,queue_version=1))
    with db:
        db.execute("INSERT OR IGNORE INTO pre_gto_jobs(id,context,options,priority,status) VALUES(?,?,?,?,'pending')",
                   (key,dump(context),dump(options),priority))
    return key

def claim(db,lease_seconds=3600):
    need(type(lease_seconds) is int and 1<=lease_seconds<=86400,"Invalid lease")
    now=time.time();token=uuid.uuid4().hex
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("UPDATE pre_gto_jobs SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'pending' END,lease=NULL,expires=NULL,error='expired lease' WHERE status='running' AND expires<=?",(now,))
        row=db.execute("SELECT id,context,options FROM pre_gto_jobs WHERE status='pending' ORDER BY priority DESC,id LIMIT 1").fetchone()
        if row:
            db.execute("UPDATE pre_gto_jobs SET status='running',attempts=attempts+1,lease=?,expires=?,error=NULL WHERE id=?",(token,now+lease_seconds,row[0]))
        db.commit()
    except BaseException:
        db.rollback();raise
    return None if row is None else (row[0],json.loads(row[1]),json.loads(row[2]),token)

def finish(db,key,token,*,model=None,error=None):
    need((model is None)!=(error is None),"Provide exactly one outcome")
    with db:
        if model is not None:
            need(db.execute("SELECT 1 FROM pre_gto_models WHERE model=?",(model,)).fetchone() is not None,"Unknown model")
        cur=db.execute("UPDATE pre_gto_jobs SET status=?,model=?,error=?,lease=NULL,expires=NULL WHERE id=? AND status='running' AND lease=?",
                       ("completed" if model else "failed",model,error,key,token))
        need(cur.rowcount==1,"Lost job lease")

def run_one(db):
    from plo5_pre_gto_generate import generate
    job=claim(db)
    if job is None:return None
    key,context,options,token=job
    try:
        result=generate(db,context,**options)
    except Exception as e:
        finish(db,key,token,error=str(e)[:1000]);raise
    finish(db,key,token,model=result["model"])
    return result

def status(db):
    return dict(db.execute("SELECT status,COUNT(*) FROM pre_gto_jobs GROUP BY status"))

def selftest():
    db=sqlite3.connect(":memory:")
    setup(db)
    with db:
        db.execute("INSERT INTO pre_gto_jobs(id,context,options,priority,status) VALUES('a','{}','{}',0,'pending'),('b','{}','{}',10,'pending')")
    j=claim(db,1);assert j[0]=='b'
    with db:db.execute("UPDATE pre_gto_jobs SET expires=0 WHERE id='b'")
    k=claim(db);assert k[0]=='b' and k[3]!=j[3]
    finish(db,k[0],k[3],error="fixture")
    assert status(db)=={"failed":1,"pending":1}
    db.close()
if __name__=="__main__":selftest()
