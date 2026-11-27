"""Offline intake for explicitly supported PokerStars-style PLO5 cash text exports.
Not a DriveHUD database reader; raw actions are evidence, not a validated ledger.
"""
import hashlib
import re
from pathlib import Path
from plo5_pre_gto_context import need,cards
from plo5_review_session import page,text

HEADER=re.compile(r'^PokerStars Hand #(\d+): (?:5 Card Omaha|Omaha 5 Cards) Pot Limit \(',re.I)
START=re.compile(r'^PokerStars Hand #',re.M)
DEALT=re.compile(r'^Dealt to (.+?) \[([^\[\]]+)\]$',re.M)


def intake(path):
    p=Path(path);need(p.is_file() and not p.is_symlink() and p.suffix.lower()=='.txt' and 0<p.stat().st_size<=16*1024**2,'Local TXT required (up to 16 MiB)')
    raw=p.read_bytes();s=raw.decode('utf-8-sig').replace('\r\n','\n');starts=[m.start() for m in START.finditer(s)]
    need(starts and not s[:starts[0]].strip() and len(starts)<=10000,'Unsupported history format or record budget')
    rows=[];rejected=[];seen=set()
    for start,end in zip(starts,starts[1:]+[len(s)]):
        hand=s[start:end].strip();head=hand.splitlines()[0];m=HEADER.match(head)
        if not m or 'Tournament' in head or '*** SUMMARY ***' not in hand:
            rejected.append(dict(header=head[:200],reason='UNSUPPORTED_OR_INCOMPLETE'));continue
        ident=m.group(1);found=DEALT.findall(hand)
        if len(found)!=1 or ident in seen:
            rejected.append(dict(header=head[:200],reason='MISSING_OR_DUPLICATE_HERO_OR_ID'));continue
        hero,holding=found[0]
        try:h=cards(holding.split())
        except ValueError:
            rejected.append(dict(header=head[:200],reason='INVALID_PLO5_HOLDING'));continue
        seen.add(ident);rows.append(dict(id=ident,hero=hero,holding=h,raw=hand,hand_verified=False,ev_authorized=False))
    return dict(status='TEXT_HISTORY_CANDIDATES_ONLY',source_sha256=hashlib.sha256(raw).hexdigest(),hands=rows,rejected=rejected,financial_result_verified=False,strategy_authorized=False)


def report(source,output):
    result=intake(source);out=Path(output);need(out.suffix.lower()=='.html' and not out.exists() and not out.is_symlink(),'New HTML required')
    body=[f'<p>Históricos candidatos: {len(result["hands"])} | Rejeitados: {len(result["rejected"])}. Ações e resultados ainda não reconciliados; EV indisponível.</p>']
    for h in result['hands']:
        body.append('<article><h2>Mão '+text(h['id'])+'</h2><p>'+text(h['hero'])+' — '+text(' '.join(h['holding']))+'</p><details><summary>Histórico original</summary><pre style="white-space:pre-wrap">'+text(h['raw'])+'</pre></details></article>')
    for r in result['rejected']:body.append('<p>Rejeitado: '+text(r['header'])+' — '+text(r['reason'])+'</p>')
    with out.open('x',encoding='utf-8') as f:f.write(page(body))
    return dict(hands=len(result['hands']),rejected=len(result['rejected']),report=str(out),strategy_authorized=False)
