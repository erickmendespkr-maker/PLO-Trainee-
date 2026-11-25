"""PLO5 offline study reports from submitted models; no solver reruns or verified leaks."""
from collections import Counter, defaultdict
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import argparse
import math

from plo5_leak_review import aggregate, digest, fraction, model_result, need, number, same
from plo5_individual_report import CLASSIFICATIONS, CATEGORIES, action, equity_detail, fmt, pct, starting_reference
from plo5_ev_comparison import action_key, summarize
from plo5_hand_structure import describe
from plo5_evaluator import evaluate
from plo5_board_texture import texture
from plo5_postflop_draws import draws
from plo5_session_export import load, write
from offline_video_ingest_probe import sha256
from strategic_normalize import normalize_scenario

FLAGS=('gto_solution','video_verified','strategic_error_established','automatic_clip_selection_authorized')


def bounds(point, interval):
    need(type(interval) is list and len(interval)==2,'Invalid interval')
    lo,hi=map(number,interval);need(lo<=hi and lo<=number(point)+1e-10 and point<=hi+1e-10,'Point outside interval');return lo,hi


def classify(intervals):
    if not intervals:return 'NO_MATCH'
    return ('INFERIOR_IN_ALL_DECLARED_HYPOTHESES' if all(x[0]>1e-10 for x in intervals) else
            'BEST_OR_TIED_IN_ALL_DECLARED_HYPOTHESES' if all(x[1]==0 for x in intervals) else 'SENSITIVE_OR_UNCERTAIN')


def extension(item,base):
    need(type(item) is dict and set(item)=={'review','extension','report'},'Invalid integration entry')
    review,e,r=(item[k] for k in ('review','extension','report'))
    need(type(e) is dict and set(e)=={'variant','review_digest','kind','scenario','seat_map'} and type(e['variant']) is int and e['variant']==5 and e['review_digest']==digest(review),'Extension identity mismatch')
    need(r['review_digest']==digest(review) and r['extension_digest']==digest(e) and r['base_decision']==base and r['variant']==5 and r['model_kind']==e['kind'],'Integration identity mismatch')
    need(all(r.get(k) is False for k in FLAGS) and all(k in r and r[k] is None for k in ('frequency','ev_loss_bb','financial_result_bb')),'Unsupported verified result')
    need(type(review['variant']) is int and review['variant']==5 and all(review[k]==base[k] for k in ('job_id','draft_sha256','draft_id','context_file','action_file')) and normalize_scenario(5,review['context'])==base['context'] and review['chosen_action']==base['chosen_action_declared'],'Review context mismatch')
    kind=e['kind'];s=e['scenario'];m=r['extension_result'];c=base['context'];chosen=action_key(base['chosen_action_declared']);lines=[];loss=[]
    need(kind in ('none','preflop','stackoff','multiway','river'),'Unknown model family')
    if kind=='none':
        need(m is None and s is None and not e['seat_map'],'Unexpected base extension');return None
    need(not review['hypotheses'] and base['conditional_model'] is None,'Mixed model families')
    if base['status']=='INSUFFICIENT_DATA':
        need(m is None and r['model_status']=='INSUFFICIENT_DATA','Insufficient evidence cannot be scored');return {'family':kind,'classification':'INSUFFICIENT_DATA','loss_bounds_bb':None,'lines':['Dados insuficientes para executar o modelo adicional.']}
    need(type(m) is dict and type(s) is dict and type(m['variant']) is int and type(s['variant']) is int and m['variant']==s['variant']==5 and m.get('gto_solution') is False and m.get('video_verified') is False,'Invalid conditional extension')
    bb=s.get('bb',s.get('bb_chips'));need(type(bb) is int and bb>0 and Fraction(bb)==Fraction(review['context']['bb_size']),'Big blind mismatch')
    def match(v,k):need(type(v) is int and Fraction(v,bb)==Fraction(c[k]),'Extension monetary mismatch')
    need(review['context']['amount_unit']=='chips','Explicit chip unit required')
    if kind!='river':
        cap=s.get('rake_cap',s.get('rake_cap_chips'));match(cap,'rake_cap');need(type(s['rake_bps']) is int and Fraction(s['rake_bps'],100)==Fraction(c['rake_percent']),'Rake mismatch')
    if kind in ('preflop','stackoff'):
        need(c['street']=='preflop' and s['position']==m['position']==c['position'] and sorted(s['hero'])==c['hero'] and len(s['stacks'])==c['players'],'Preflop context mismatch')
        match(m['pot_chips'],'pot');match(m['to_call_chips'],'to_call');match(m['remaining_stacks_chips'][c['position']],'stack')
        need((s['chosen']['action'],s['chosen']['amount']-m['to_call_chips'] if chosen[0]=='raise' else 0)==chosen,'Preflop sizing mismatch')
        if kind=='preflop':
            need(m['history_sha256']==digest(s),'Replay hash mismatch')
            lines.append('Contexto pré-flop declarado: '+str(m['spot'])+'; classe da ação: '+str(m['chosen_class'])+'.')
            lines.append('Stack efetivo inicial por adversário (BB): '+str(m['effective_initial_stack_bb'])+'.')
            comparison=m['conditional_model']
            if comparison is not None:
                checked=model_result(comparison,chosen);loss=[checked['loss_bounds_bb']] if checked['loss_bounds_bb'] is not None else []
                for name,h in sorted(comparison['scenarios'].items()):
                    lines.append('Hipótese '+str(name)+': '+', '.join(action(a['action'])+' '+fmt(a['ev_bb'])+' BB' for a in h['alternatives']))
                return {'family':kind,'classification':checked['classification'],'loss_bounds_bb':checked['loss_bounds_bb'],'lines':lines}
        else:
            need(m['scenario_sha256']==digest(s),'Stack-off hash mismatch')
            keys=set()
            for x in m['actions']:
                k=action_key({'action':x['action'],'extra_chips':x['extra_chips']});need(k not in keys and same(float(fraction(x['ev_fraction_bb'])),x['ev_bb']),'Invalid stack-off alternative');keys.add(k);bounds(x['ev_bb'],x['sampling_interval_bb'])
            checked=summarize({'actions':m['actions'],'scenario_sha256':m['scenario_sha256']},chosen);need(checked==m['comparison'],'Stack-off comparison mismatch')
            for a in checked['alternatives']:
                equity_detail(a.get('showdown_equity'));lines.append(action(a['action'])+': EV terminal '+fmt(a['ev_bb'])+' BB; intervalo '+str(a['sampling_interval_bb'])+'.')
            if checked['loss_bounds_bb'] is not None:loss=[checked['loss_bounds_bb']]
            lines.append('Stack-off HU: fold/call terminal, sem futuras apostas; range e respostas declarados.')
    elif kind=='multiway':
        need(c['players']>=3 and c['street']!='preflop' and chosen[0] in ('fold','call') and sorted(s['hero'])==c['hero'] and sorted(s['board'][:3])+s['board'][3:]==c['board'],'Multiway context mismatch')
        match(s['pot_chips'],'pot');match(s['call_chips'],'to_call');match(s['hero_stack_chips'],'stack')
        eq=m['equity_model'];n=c['players'];mass=eq['share_mass'];den=eq['mass_denominator'];need(eq['players']==n and type(mass) is list and len(mass)==n+1 and all(type(v) is int and v>=0 for v in mass) and type(den) is int and den>0 and sum(mass)==den,'Invalid share mass')
        q=sum((Fraction(mass[j],den*j) for j in range(1,n+1)),Fraction());need(q==fraction(eq['equity_fraction']) and same(float(q),eq['equity']),'Equity share mismatch')
        need(eq['method'] in ('exact','monte_carlo') and eq['evaluated_states']>0 and (eq['method']=='exact' or eq['evaluated_states']==den),'Invalid equity method')
        pool=s['pot_chips']+s['call_chips'];fee=lambda p:min(s['rake_cap_chips'],p*s['rake_bps']//10000);net=pool-fee(pool)
        need(set(m['scenarios'])==set(s['scenarios']),'Multiway hypothesis mismatch')
        lines.append('Equity de divisão do pote: '+pct(float(q))+'; '+str(n)+' jogadores, pote comum elegível declarado.')
        for name,x in sorted(m['scenarios'].items()):
            payments=s['scenarios'][name];limit=0 if c['street']=='river' else min([s['hero_stack_chips']-s['call_chips']]+s['opponent_stacks_chips']);need(payments==x['future_payment_by_share_bucket_chips'] and len(payments)==n+1 and all(type(v) is int and 0<=v<=limit for v in payments),'Future payments mismatch')
            pay=[(Fraction(net+n*v-(fee(pool+n*v)-fee(pool)),j) if j else Fraction())-s['call_chips']-v for j,v in enumerate(payments)]
            ev=sum((Fraction(w,den)*p for w,p in zip(mass,pay)),Fraction())/bb
            need(ev==fraction(x['ev_call_fraction_bb']) and same(float(ev),x['ev_call_bb']),'Multiway EV mismatch')
            lo,hi=bounds(float(ev),x['sampling_ci95_bb']);radius=0 if eq['method']=='exact' else float(max(pay)-min(pay))*math.sqrt(math.log(40)/(2*den))/bb
            need(same(lo,min(float(ev),max(float(min(pay)/bb),float(ev)-radius))) and same(hi,max(float(ev),min(float(max(pay)/bb),float(ev)+radius))),'Multiway interval mismatch')
            deltas=[(Fraction(n*v-(fee(pool+n*v)-fee(pool)),j) if j else Fraction())-v for j,v in enumerate(payments)]
            gain=sum((Fraction(w,den)*max(0,d) for w,d in zip(mass,deltas)),Fraction())/bb;reverse=sum((Fraction(w,den)*max(0,-d) for w,d in zip(mass,deltas)),Fraction())/bb
            need(same(float(gain),x['expected_implied_gain_bb']) and same(float(reverse),x['expected_reverse_implied_loss_bb']),'Implied payment mismatch')
            loss.append([max(0,lo),max(0,hi)] if chosen[0]=='fold' else [max(0,-hi),max(0,-lo)])
            lines.append('Hipótese '+str(name)+': call '+fmt(ev)+' BB, fold 0 BB; ganho implícito '+fmt(x['expected_implied_gain_bb'])+' BB, perda implícita reversa '+fmt(x['expected_reverse_implied_loss_bb'])+' BB.')
        lines.append('Pagamentos futuros iguais e condicionados ao resultado; não é uma árvore de apostas.')
    else:
        need(c['street']=='river' and c['players']==2 and c['to_call']=='0' and c['rake_percent']=='0' and sorted(s['board'][:3])+s['board'][3:]==c['board'] and m['game']==s and m['game_sha256']==digest(s),'River game mismatch')
        match(s['pot_chips'],'pot');match(s['hero_stack_chips'],'stack');need(chosen[0]=='check' or chosen==('bet',s['bet_chips']),'River sizing mismatch')
        rows=[x for x in m['hero_strategy'] if sorted(x['cards'])==c['hero']];need(len(rows)==1 and rows[0]==r['chosen_conditional_model'],'Hero strategy mismatch')
        actions=rows[0]['actions'];need(len(actions)==2 and [x['action'] for x in actions]==['check','bet'] and actions[1]['extra_chips']==s['bet_chips'] and all(0<=number(x['frequency'])<=1 for x in actions) and same(sum(x['frequency'] for x in actions),1),'Invalid restricted frequencies')
        lo,hi=bounds(m['hero_value_bb'],[m['best_response_lower_bb'],m['best_response_upper_bb']]);gap=number(m['nash_gap_bb']);need(same(gap,hi-lo) and same(m['gap_fraction_of_pot'],gap*bb/s['pot_chips']),'River gap mismatch')
        lines.extend([x['action'].upper()+': frequência do jogo restrito '+pct(x['frequency'])+'; EV '+fmt(x['ev_bb'])+' BB.' for x in actions]);lines.append('Gap global de melhores respostas: '+fmt(gap)+' BB. Não é erro individual nem frequência GTO da mão real.')
        return {'family':kind,'classification':'RESTRICTED_GAME_ONLY','loss_bounds_bb':None,'lines':lines}
    return {'family':kind,'classification':classify(loss),'loss_bounds_bb':[min(x[0] for x in loss),max(x[1] for x in loss)] if loss else None,'lines':lines}


def build(payload,mode='quick'):
    need(type(payload) is dict and set(payload)=={'bundle','integrations'} and mode in ('quick','deep'),'Invalid report request')
    b=payload['bundle'];summary=aggregate(b);reports={r['action_file']:r for r in b['reports']};integrations=payload['integrations'];need(type(integrations) is list and len(integrations)<=len(reports),'Invalid integration roster')
    extra={};ext_hashes={}
    for item in integrations:
        f=item['report']['base_decision']['action_file'];need(f in reports and f not in extra,'Duplicate or unrostered extension');extra[f]=extension(item,reports[f]);ext_hashes[f]=digest(item)
    @lru_cache(maxsize=32)
    def cards(h,board):
        if not board:return describe(list(h)),None
        if mode=='quick':return evaluate(h,board),None
        return texture(board,h),draws(h,board)
    money={x['draft_id']:x['conditional_net_bb'] for x in b['financial_report']['reviews'] if x['status']=='conditional_reconciled'} if b['financial_report'] is not None else {}
    decisions=[];groups=defaultdict(list)
    for row in summary['decisions']:
        f=row['action_file'];r=reports.get(f);ex=extra.get(f);family=ex['family'] if ex else 'base_hu_terminal';classification=ex['classification'] if ex else row['classification'];loss=ex['loss_bounds_bb'] if ex else row['loss_bounds_bb'];lines=['PLO5 — estudo de decisão declarada']
        if r:
            c=r['context'];lines.extend([f"Posição {c['position']} | {c['street']} | {c['players']} jogadores declarados",f"Hero {' '.join(c['hero'])} | Board {' '.join(c['board']) or 'pré-flop'}",f"Pote {c['pot']} BB; call {c['to_call']} BB; stack restante {c['stack']} BB",'Ação declarada: '+action(r['chosen_action_declared'])])
            if r.get('context_is_reviewed_declaration_not_verified') is True and r['status']!='INSUFFICIENT_DATA':
                p,call=Fraction(c['pot']),Fraction(c['to_call']);lines.append('Stack restante Hero/pote: '+fmt(Fraction(c['stack'])/p)+' (não é SPR efetivo inicial).')
                if call:lines.append('Pot odds sem rake: '+pct(float(call/(p+call)))+'.')
                a,d=cards(tuple(c['hero']),tuple(c['board']))
                if not c['board']:
                    lines.extend(a['interpretation_pt']);ref=starting_reference(r.get('starting_equity'),a)
                    if ref:lines.append('Equity agregada SolvePoker contra aleatório: '+pct(ref[0])+' a '+pct(ref[1])+'; não é estratégia.')
                else:
                    made=a['hero']['made_hand'] if d else a;lines.append('Mão atual: '+CATEGORIES[made['category']]+'.')
                    if d:
                        lines.append('Nuts do board: '+CATEGORIES[a['board_nut_category']]+'. Pares adversários superiores após blockers: '+str(a['hero']['opponent_pairs_beating_hero'])+'.')
                        for k,t in d['targets'].items():
                            if d['next_card_denominator'] and not t['already_possible']:lines.append(k+': '+str(t['next_completion']['count'])+'/'+str(d['next_card_denominator'])+' cartas de conclusão; não necessariamente vencedoras.')
                    else:lines.append('Modo rápido: textura detalhada, nuts e draws não recalculados; disponíveis no modo aprofundado.')
            if ex:lines.extend(ex['lines'])
            elif r['conditional_model']:
                for name,h in sorted(r['conditional_model']['scenarios'].items()):
                    lines.append('Hipótese '+str(name)+':')
                    for a in h['alternatives']:
                        eq=equity_detail(a.get('showdown_equity'));lines.append(action(a['action'])+': EV '+fmt(a['ev_bb'])+' BB; intervalo '+str(a['sampling_interval_bb'])+('. Equity '+pct(eq['equity']) if eq else ''))
        lines.append(CLASSIFICATIONS.get(classification,'Sem relatório disponível.' if classification=='MISSING_REPORT' else 'Jogo restrito: resultado apenas para a árvore declarada.'))
        if loss is not None:lines.append('Diferença condicional para alternativa modelada: '+fmt(loss[0])+' a '+fmt(loss[1])+' BB. Não somar entre decisões.')
        lines.append('Resultado financeiro do segmento (não verificado): '+(money[row['draft_id']]+' BB' if row['draft_id'] in money else 'indisponível')+'. EV loss real, variância e frequência GTO: indisponíveis.')
        item={**row,'model_family':family,'classification':classification,'base_classification':row['classification'],'loss_bounds_bb':loss,'text':'\n'.join(lines)+'\n','integration_sha256':ext_hashes.get(f)}
        if f in extra:item['integration_present']=True
        if ex:
            for k in ('comparable_hypotheses','hypotheses','stochastic_intervals'):item[k]=None
        decisions.append(item);groups[(family,row['players_dealt'],row['position'],row['street'],row['action'],row['hero_remaining_stack_bucket_bb'])].append(item)
    patterns=[]
    for key,items in sorted(groups.items(),key=lambda x:str(x[0])):
        inferior=[x for x in items if x['classification']=='INFERIOR_IN_ALL_DECLARED_HYPOTHESES' and x['loss_bounds_bb'] is not None];comparable=sum(x['loss_bounds_bb'] is not None for x in items);distinct=len({x['draft_id'] for x in inferior})
        patterns.append(dict(zip(('model_family','players','position','street','action','stack_bucket'),key),declared_decisions=len(items),comparable_decisions=comparable,conditional_inferior_decisions=len(inferior),distinct_inferior_segments=distinct,repeated_conditional_pattern=distinct>=2,study_action_files=[x['action_file'] for x in sorted(inferior,key=lambda x:(-x['loss_bounds_bb'][0],x['action_file']))],coverage_fraction=comparable/len(items)))
    info=cards.cache_info();return {'variant':5,'status':'CONDITIONAL_STUDY_REPORT','mode':mode,'input_digest':digest(payload),'declared_decisions':len(decisions),'classification_counts':dict(Counter(x['classification'] for x in decisions)),'reports_received':len(reports),'comparable_decisions':sum(x['loss_bounds_bb'] is not None for x in decisions),'patterns':patterns,'decisions':decisions,'financial':summary['financial'],'base_summary':summary['overall'],'card_cache':{'hits':info.hits,'misses':info.misses,'maxsize':info.maxsize},'solver_reruns':0,'denominator_scope':'declared_roster_only','recurrence_scope':'distinct_declared_segments_with_same_family_and_group_not_identical_ranges_or_verified_hands','report_authenticity_verified':False,'ev_loss_bb':None,'variance_attribution':None,**{k:False for k in FLAGS}}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('output');p.add_argument('--mode',choices=('quick','deep'),default='quick');a=p.parse_args(argv);out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required');payload,h=load(a.input);r=build(payload,a.mode);need(sha256(a.input)==h,'Input changed');r['input_sha256']=h;write(out,r);return 0

if __name__=='__main__':raise SystemExit(main())
