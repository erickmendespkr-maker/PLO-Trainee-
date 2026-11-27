"""Local, user-defined rake profiles; never assume a room's actual rules."""
import sqlite3
from contextlib import closing
from decimal import Decimal, InvalidOperation
from plo5_pre_gto_context import need, integer


def _scaled(text, scale, limit):
    need(type(text) is str and 0 < len(text) <= 32, 'Valor inválido')
    try:
        d=Decimal(text.strip().replace(',', '.'))
        need(d.is_finite() and 0 <= d <= limit and abs(d.as_tuple().exponent) <= 12, 'Valor fora do limite')
        # Ratio conversion avoids decimal-context rounding.
        n,den=d.as_integer_ratio()
        need(n*scale % den == 0, 'Valor não representável na unidade de fichas')
        return n*scale//den
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError('Valor inválido') from exc


def profile(platform, club, limit, percent, cap_bb, on_fold):
    labels=[platform,club,limit]
    need(all(type(x) is str and 0 < len(x.strip()) <= 100 for x in labels), 'Informe plataforma, clube e limite')
    need(type(on_fold) is bool, 'Regra de fold inválida')
    bps=_scaled(percent,100,100)
    # Store exact decimal BB text; conversion to chips depends on the context.
    _scaled(cap_bb,10**6,10**6)
    return dict(platform=platform.strip(),club=club.strip(),limit=limit.strip(),rake_bps=bps,
                cap_bb=cap_bb.strip().replace(',','.'),rake_on_fold=on_fold)


def apply(context, p):
    from plo5_post_gto_context import normalize
    c=normalize(context)
    bps=integer(p['rake_bps']); need(bps<=10000, 'Rake inválido')
    cap=_scaled(p['cap_bb'],c['bb'],10**6); integer(cap)
    need(type(p['rake_on_fold']) is bool,'Regra de fold inválida')
    return dict(context,rake_bps=bps,rake_cap=cap), p['rake_on_fold']


def _open(path):
    con=sqlite3.connect(path,timeout=10)
    con.execute('CREATE TABLE IF NOT EXISTS rake_profiles (platform TEXT, club TEXT, stake TEXT, bps INTEGER, cap_bb TEXT, on_fold INTEGER, PRIMARY KEY(platform,club,stake))')
    return con


def save(path,p):
    p=profile(p['platform'],p['club'],p['limit'],str(Decimal(p['rake_bps'])/100),p['cap_bb'],p['rake_on_fold'])
    with closing(_open(path)) as con, con:
        con.execute('INSERT OR REPLACE INTO rake_profiles VALUES (?,?,?,?,?,?)',(p['platform'],p['club'],p['limit'],p['rake_bps'],p['cap_bb'],int(p['rake_on_fold'])))


def load(path):
    with closing(_open(path)) as con:
        return [dict(platform=a,club=b,limit=c,rake_bps=d,cap_bb=e,rake_on_fold=bool(f)) for a,b,c,d,e,f in con.execute('SELECT * FROM rake_profiles ORDER BY platform,club,stake')]
