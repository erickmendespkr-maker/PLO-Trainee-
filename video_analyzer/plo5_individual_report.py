"""Offline Portuguese report for one declared PLO5 decision; not a verified grade."""
import argparse
from fractions import Fraction
import hashlib
import json
from math import log, sqrt
from pathlib import Path

from plo5_leak_review import aggregate, digest, fraction, need, number, same
from plo5_ev_comparison import action_key
from plo5_equity_store import SOURCE, LICENSE, SHA256
from plo5_hand_structure import describe
from plo5_board_texture import texture
from plo5_postflop_draws import draws

CATEGORIES={'high_card':'carta alta','one_pair':'um par','two_pair':'dois pares',
            'three_of_a_kind':'trinca','straight':'sequência','flush':'flush',
            'full_house':'full house','four_of_a_kind':'quadra','straight_flush':'straight flush'}
CLASSIFICATIONS={
    'INFERIOR_IN_ALL_DECLARED_HYPOTHESES':'A ação tem EV inferior em todas as hipóteses declaradas, dentro dos limites calculados.',
    'BEST_OR_TIED_IN_ALL_DECLARED_HYPOTHESES':'A ação é melhor ou empatada com a melhor alternativa modelada em todas as hipóteses declaradas.',
    'SENSITIVE_OR_UNCERTAIN':'A comparação depende das hipóteses ou da incerteza amostral; não há conclusão robusta.',
    'PARTIAL_HYPOTHESES':'A comparação cobre apenas parte das hipóteses; não há conclusão global.',
    'NO_MATCH':'Não há referência ou alternativa compatível para avaliar a ação.',
    'INSUFFICIENT_DATA':'Dados insuficientes para comparar a ação.'}


def fmt(x, places=3):
    return f'{float(x):.{places}f}'.replace('.',',')


def pct(x): return fmt(100*x,2)+'%'


def action(a):
    kind,x=action_key(a)
    return kind.upper()+(f' (+{x} fichas acima do call)' if x else '')


def quoted(v):
    # Keep declared names/filenames on a single literal line in a text report.
    return json.dumps(v,ensure_ascii=True)


def equity_detail(e):
    if e is None: return None
    need(type(e) is dict and set(e)=={'method','equity_fraction','outcome_mass','mass_denominator','sampling_ci95','evaluated_states','seed'},'Invalid equity detail')
    m=e['outcome_mass'];d=e['mass_denominator'];n=e['evaluated_states']
    need(type(m) is dict and set(m)=={'win','tie','loss'} and all(type(x) is int and x>=0 for x in m.values()) and type(d) is int and d>0 and sum(m.values())==d and type(n) is int and n>0,'Invalid outcome counts')
    q=fraction(e['equity_fraction']);need(q==Fraction(2*m['win']+m['tie'],2*d),'Equity fraction mismatch')
    if e['method']=='exact_weighted_runouts':
        need(e['seed'] is None and n<=20000 and n<=d,'Invalid exact evidence');radius=0
    else:
        need(e['method']=='weighted_monte_carlo' and type(e['seed']) is int and 0<=e['seed']<2**32 and n==d and n<=100000,'Invalid simulation evidence');radius=sqrt(log(40)/(2*n))
    lo,hi=map(number,e['sampling_ci95']);need(same(lo,max(0,float(q)-radius)) and same(hi,min(1,float(q)+radius)),'Equity interval mismatch')
    return {'equity':float(q),'interval':[lo,hi],'method':e['method'],'evaluated_states':n}


def starting_reference(ref, structure):
    if ref is None or ref.get('status')=='NO_MATCH': return None
    h=structure['hand_class'];need(ref.get('status') in ('DESCRIPTOR_ONLY','AMBIGUOUS_DESCRIPTOR') and ref.get('source')==SOURCE and ref.get('license')==LICENSE and ref.get('csv_sha256')==SHA256 and ref.get('exact_suit_match') is False and ref.get('strategy_reference') is False and ref.get('gto') is False and ref.get('frequency') is None and ref.get('ev_bb') is None and (ref.get('hand'),ref.get('suits'))==(h['rank_descriptor'],h['suit_descriptor']),'Incompatible equity reference')
    rows=ref['rows'];need(type(rows) is list and 1<=len(rows)<=1000 and ref['matches']==len(rows) and ref['status']==('DESCRIPTOR_ONLY' if len(rows)==1 else 'AMBIGUOUS_DESCRIPTOR'),'Invalid descriptor rows')
    ranks=set(); lows=[]; highs=[]
    for row in rows:
        need(isinstance(row,(list,tuple)) and len(row)==4,'Invalid descriptor row')
        rank,lo,hi,combos=row;lo,hi=Fraction(lo),Fraction(hi)
        need(type(rank) is int and 1<=rank<=134459 and rank not in ranks and type(combos) is int and combos>0 and 0<=lo<=hi<=1,'Invalid descriptor values')
        ranks.add(rank);lows.append(lo);highs.append(hi)
    need(Fraction(ref['equity_lo'])==min(lows) and Fraction(ref['equity_hi'])==max(highs),'Descriptor bounds mismatch')
    return (float(min(lows)),float(max(highs)),len(rows))


def build(bundle):
    """Reuse block 32 validation; render one report and optional separate ledger."""
    summary=aggregate(bundle)
    need(len(bundle['expected_decisions'])==len(bundle['reports'])==1,'Exactly one declared decision/report required')
    r=bundle['reports'][0]; row=summary['decisions'][0]; c=r['context']; model=r['conditional_model']
    classification=row['classification']; chosen=action(r['chosen_action_declared'])
    lines=['PLO TRAINEE — RELATÓRIO TÉCNICO INDIVIDUAL PLO5',
           'Análise offline de uma decisão declarada; não constitui avaliação GTO ou verificação de vídeo.', '',
           '1. Evidências e contexto declarado',
           f"Job: {r['job_id']} | Segmento: {quoted(r['draft_id'])}",
           f"Quadro de contexto: {quoted(r['context_file'])} | PTS {fmt(r['context_pts'])} s",
           f"Quadro de ação: {quoted(r['action_file'])} | PTS {fmt(r['action_pts'])} s",
           f"Street: {c['street']} | Posição: {c['position']} | Jogadores declarados: {c['players']}",
           f"Hero: {' '.join(c['hero'])} | Board: {' '.join(c['board']) or 'pré-flop'}",
           f"Pote: {c['pot']} BB | Call: {c['to_call']} BB | Stack restante do Hero: {c['stack']} BB",
           f"Ação declarada: {chosen}. Sizing agressivo em fichas incrementais acima do call.",
           'Os quadros e a ação são referências declaradas, não prova de autenticidade.', '',
           '2. Fundamentos matemáticos']
    metrics_allowed=r.get('context_is_reviewed_declaration_not_verified') is True and r['status']!='INSUFFICIENT_DATA'
    if metrics_allowed:
        p,call=Fraction(c['pot']),Fraction(c['to_call'])
        if call: lines.append(f'Pot odds sem rake: {pct(float(call/(p+call)))} (equity de equilíbrio terminal; não considera apostas futuras).')
        if c['street']=='preflop':
            structure=describe(c['hero']);lines.extend(structure['interpretation_pt'])
            ref=starting_reference(r.get('starting_equity'),structure)
            if ref:
                lo,hi,n=ref;lines.append(f'Referência agregada submetida SolvePoker: {pct(lo)} a {pct(hi)}, {n} registro(s), contra um adversário aleatório; não há correspondência exata de naipes nem frequência GTO.')
                lines.append('Fonte: '+SOURCE+' | Licença declarada: '+LICENSE+' | SHA-256 CSV: '+SHA256)
        else:
            t=texture(c['board'],c['hero']);d=draws(c['hero'],c['board']); hero=t['hero']
            lines.append(f"Mão atual: {CATEGORIES[hero['made_hand']['category']]}. Nuts absolutos atuais do board: {CATEGORIES[t['board_nut_category']]}. " + ('Hero não pode ser superado no board atual (considerando blockers).' if hero['cannot_be_beaten_now'] else 'Existem pares privados adversários capazes de superar o Hero no board atual.'))
            lines.append(f"Textura: ranks {t['rank_partition']}, naipes {t['suit_partition']}; pares adversários que superam o Hero: {hero['opponent_pairs_beating_hero']}. Pares não equivalem a holdings completas.")
            if d['next_card_denominator']:
                for k,name in [('straight','sequência'),('flush','flush'),('full_house','full house'),('quads','quadra')]:
                    target=d['targets'][k]
                    if not target['already_possible']:
                        lines.append(f"Conclusão de {name}: {target['next_completion']['count']}/{d['next_card_denominator']} na próxima carta; até o river {pct(target['by_river_completion']['probability'])}.")
                lines.append('Outs de conclusão não são necessariamente outs vencedores; probabilidades condicionadas somente às cartas do Hero e board.')
    else: lines.append('Contexto insuficiente ou sem declaração de compatibilidade; fundamentos descritivos não apresentados como análise da jogada.')
    lines.extend(['','3. Comparação das alternativas','Frequências GTO: indisponíveis. Nenhuma referência estratégica autorizada foi verificada.'])
    scenarios=[]
    if model is not None:
        for name,s in sorted(model['scenarios'].items()):
            lines.append('Hipótese '+quoted(name)+' — SHA-256 '+s['scenario_sha256'])
            for alt in s['alternatives']:
                eq=equity_detail(alt.get('showdown_equity'))
                text=f"  {action(alt['action'])}: EV condicional {fmt(alt['ev_bb'])} BB; intervalo [{fmt(alt['sampling_interval_bb'][0])}, {fmt(alt['sampling_interval_bb'][1])}] BB."
                if eq:
                    text+=f" Equity de showdown {'quando pago' if alt['action']['action'] in ('bet','raise') else 'terminal'}: {pct(eq['equity'])} [{pct(eq['interval'][0])}, {pct(eq['interval'][1])}], {eq['evaluated_states']} estados/amostras."
                lines.append(text)
            if s['loss_bounds_bb'] is not None:
                lines.append(f"  Diferença para a melhor alternativa modelada: {fmt(s['conditional_ev_loss_bb'])} BB; limites [{fmt(s['loss_bounds_bb'][0])}, {fmt(s['loss_bounds_bb'][1])}] BB.")
            else: lines.append('  Diferença indisponível: ação/sizing ausente ou sem alternativa comparável.')
            scenarios.append({'name':name,'scenario_sha256':s['scenario_sha256'],'status':s['status'],'alternatives':s['alternatives'],'conditional_ev_loss_bb':s['conditional_ev_loss_bb'],'loss_bounds_bb':s['loss_bounds_bb']})
        lines.append(f"Cobertura: {row['comparable_hypotheses']}/{row['hypotheses']} hipóteses; espaço de ações incompleto.")
        lines.append('Limite inferior de cobertura amostral conjunta sob as hipóteses: '+pct(model['sampling_interval_joint_coverage_lower_bound'])+'. Não inclui incerteza dos ranges ou respostas.')
        lines.append('EV incremental em BB, baseline fold=0; modelo terminal heads-up sem apostas futuras. Não é EV de uma árvore real.')
    else: lines.append('Sem modelo compatível: EV, equity contra range e diferença de EV indisponíveis.')
    lines.extend(['','4. Interpretação e confiança',CLASSIFICATIONS[classification],
                  'Confiança: consistência matemática condicional; autenticidade da ação e do vídeo não verificada. Nenhum erro ou acerto estratégico real comprovado.',
                  'Para aprofundar: confirmar cartas, ordem, sizing, stack efetivo, rake e range adversário; obter referência estratégica autorizada compatível.','', '5. Resultado financeiro e variância'])
    f=bundle['financial_report'];net=None
    if f is not None:
        item=next((x for x in f['reviews'] if x['draft_id']==r['draft_id']),None)
        if item and item['status']=='conditional_reconciled':net=item['conditional_net_bb']
    lines.append('Resultado financeiro condicional do segmento: '+(net+' BB (ledger declarado; não verificado).' if net is not None else 'indisponível.'))
    lines.append('Não é EV loss. Atribuição à variância: indisponível; resultado isolado não demonstra sorte ou erro.')
    sources={k:r[k] for k in ('job_id','source_sha256','manifest_sha256','draft_sha256','draft_id','context_file','action_file','context_pts','action_pts')}
    sources['decision_report_sha256']=digest(r);sources['financial_report_sha256']=digest(f) if f is not None else None
    lines.extend(['','6. Rastreabilidade',*[f'{k}: {quoted(v)}' for k,v in sources.items()]])
    return {'variant':5,'status':'INDIVIDUAL_CONDITIONAL_REPORT','classification':classification,'language':'pt-BR',
            'sources':sources,'bundle_sha256':summary['bundle_sha256'],'scenarios':scenarios,'text':'\n'.join(lines)+'\n',
            'conditional_segment_net_bb':net,'frequency':None,'ev_loss_bb':None,'variance_attribution':None,
            'gto_solution':False,'video_verified':False,'strategic_error_established':False,'report_authenticity_verified':False,'automatic_clip_selection_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle');p.add_argument('output');a=p.parse_args(argv)
    source=Path(a.bundle);out=Path(a.output)
    need(source.is_file() and not source.is_symlink() and 0<source.stat().st_size<=32*1024*1024,'Unsafe input')
    need(out.suffix in ('.json','.txt') and not out.exists() and not out.is_symlink(),'New JSON or TXT output required')
    def unique(items):
        obj={}
        for k,v in items:need(k not in obj,'Duplicate JSON key');obj[k]=v
        return obj
    raw=source.read_bytes();need(len(raw)<=32*1024*1024,'Oversized input')
    r=build(json.loads(raw,object_pairs_hook=unique));r['input_sha256']=hashlib.sha256(raw).hexdigest()
    with out.open('x',encoding='utf-8') as f:
        if out.suffix=='.txt':f.write(r['text']+'input_sha256: '+r['input_sha256']+'\n')
        else:json.dump(r,f,ensure_ascii=False,indent=2,allow_nan=False)
    return 0


if __name__=='__main__':raise SystemExit(main())
