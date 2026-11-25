"""Open a dedicated local cache, never migrate an unrelated SQLite file."""
from contextlib import closing
from pathlib import Path
import sqlite3
from plo5_restricted_cache import connect


def open_cache(path, *, protected=()):
    p=Path(path)
    if p.is_symlink() or not p.parent.is_dir() or any(p.resolve()==Path(x).resolve() for x in protected):
        raise ValueError('Unsafe solver cache path')
    if p.exists():
        if not p.is_file():raise ValueError('Regular solver cache required')
        with closing(sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            expected=[('restricted_solutions','table')]
            objects=db.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            columns=db.execute('PRAGMA table_info(restricted_solutions)').fetchall()
            if objects!=expected or [(r[1],r[2],r[5]) for r in columns]!=[('key','TEXT',1),('input','TEXT',0),('policy','TEXT',0)]:
                raise ValueError('Existing SQLite is not a dedicated solver cache')
    return connect(p)
