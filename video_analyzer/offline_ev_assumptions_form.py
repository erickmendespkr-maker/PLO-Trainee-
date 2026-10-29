"""Offline browser form for hypothetical PLO5/PLO6 EV sensitivity assumptions.

Usage:
    python offline_ev_assumptions_form.py create NEW_FORM.html
    python offline_ev_assumptions_form.py verify ASSUMPTIONS.json

Creates only a local HTML form and validates JSON; it does not infer ranges,
identify players/actions, compute equity, or access any poker service.
The resulting JSON is an input to offline_acknowledged_sensitivity_bundle.py.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from offline_plo_equity_monte_carlo import cards, read_json, require

CONFIG_FIELDS = {'schema_version', 'pot_now', 'call_cost', 'raise_extra',
                 'fold_probabilities', 'hypotheses'}
HYPOTHESIS_FIELDS = {'label', 'call_model', 'raise_called_model',
                     'call_iterations', 'raise_called_iterations', 'call_seed',
                     'raise_called_seed', 'fold_probability_assumed'}


def _number(x, name, minimum, maximum, *, integer=False):
    require(type(x) is (int if integer else float) or
            (not integer and type(x) is int), f'invalid {name} type')
    require(math.isfinite(x) and minimum <= x <= maximum, f'invalid {name}')
    return x


def _model(model):
    require(type(model) is dict and model.get('kind') in ('uniform', 'weighted_combos'),
            'invalid opponent range model')
    if model['kind'] == 'uniform':
        require(set(model) == {'kind'}, 'uniform range cannot have combos')
        return
    require(set(model) == {'kind', 'combos'} and type(model['combos']) is list and
            1 <= len(model['combos']) <= 1000, 'invalid weighted combos')
    seen = set()
    count = None
    for item in model['combos']:
        require(type(item) is dict and set(item) == {'cards', 'weight'},
                'invalid weighted combo fields')
        hand = cards(item['cards'])
        require(len(hand) in (5, 6), 'weighted combo must have five or six cards')
        count = count or len(hand)
        require(len(hand) == count, 'mixed PLO5/PLO6 weighted combos')
        key = tuple(sorted(hand))
        require(key not in seen, 'duplicate weighted combo')
        seen.add(key)
        _number(item['weight'], 'combo weight', 1e-300, 1e6)


def validate_assumptions(data):
    """Check the exported config schema, not its empirical correctness."""
    require(type(data) is dict and set(data) == CONFIG_FIELDS and
            type(data.get('schema_version')) is int and data['schema_version'] == 1,
            'invalid assumptions schema; cards and observed actions are forbidden')
    pot = _number(data['pot_now'], 'pot_now', 1e-6, 1e9)
    cost = _number(data['call_cost'], 'call_cost', 1e-6, 1e9)
    extra = _number(data['raise_extra'], 'raise_extra', 1e-6, 1e9)
    require(pot >= cost and pot + cost + 2 * extra <= 1e9, 'invalid pot geometry')
    ps = data['fold_probabilities']
    require(type(ps) is list and 2 <= len(ps) <= 21, 'require 2..21 fold probabilities')
    for p in ps:
        _number(p, 'fold probability', 0, 1)
    require(all(a < b for a, b in zip(ps, ps[1:])),
            'fold probabilities must be strictly increasing')
    hs = data['hypotheses']
    require(type(hs) is list and 1 <= len(hs) <= 5, 'require 1..5 range hypotheses')
    labels = set()
    for h in hs:
        require(type(h) is dict and set(h) == HYPOTHESIS_FIELDS,
                'invalid hypothesis fields')
        label = h['label']
        require(type(label) is str and 1 <= len(label) <= 64 and
                all(c.isprintable() and c not in '<>\\' for c in label) and
                label not in labels, 'invalid/duplicate hypothesis label')
        labels.add(label)
        _model(h['call_model'])
        _model(h['raise_called_model'])
        for field in ('call_iterations', 'raise_called_iterations'):
            _number(h[field], field, 2, 50000, integer=True)
        for field in ('call_seed', 'raise_called_seed'):
            _number(h[field], field, 0, 2**32-1, integer=True)
        _number(h['fold_probability_assumed'], 'baseline fold probability', 0, 1)
    return {'schema_version': 1, 'hypotheses': len(hs),
            'fold_probabilities': len(ps),
            'ranges_are_reviewer_assumptions': True,
            'action_observed_or_graded': False}


HTML = r'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'">
<title>PLO Trainee — hipóteses offline de EV</title>
<style>
:root{color-scheme:light}body{font:16px system-ui,sans-serif;background:#f4f6fa;color:#152336;margin:0;padding:20px}
main{max-width:950px;margin:auto;background:white;padding:24px;border-radius:14px}
h1{margin-top:0}fieldset{border:1px solid #ccd5df;border-radius:8px;margin:16px 0;padding:16px}
legend{font-weight:650}label{display:inline-flex;flex-direction:column;gap:4px;margin:7px 12px 7px 0}
input,select,textarea,button{font:inherit;padding:7px;border-radius:5px;border:1px solid #8999ab}
input[type=number]{width:130px}input[type=text]{min-width:190px}textarea{width:min(100%,720px);min-height:75px;box-sizing:border-box}
button{cursor:pointer;background:#f0f4fa}button[type=submit]{background:#164e86;color:white;border:0;padding:11px 18px}
.warning{padding:14px;background:#fff2d6;border-left:4px solid #a56d12}
.hypothesis{border:1px solid #ccd5df;padding:14px;margin:12px 0;border-radius:9px}
.range{padding:10px;background:#f7f9fc;border-radius:7px;margin:10px 0}
#message{min-height:1.4em}small{color:#485a6c}button:focus-visible,input:focus-visible{outline:3px solid #3389dd}
[hidden]{display:none!important}
</style></head><body><main>
<h1>Hipóteses matemáticas de EV — PLO5/PLO6</h1>
<p class="warning"><strong>Somente análise offline de gravações.</strong> Ranges, pote e probabilidades de fold são hipóteses fornecidas pelo revisor, não fatos extraídos do vídeo. A equity será calculada separadamente com cartas já confirmadas. O modelo é heads-up e terminal: sem rake, side pots, all-in ou apostas futuras. Não classifica jogadas.</p>
<form id="form" novalidate>
<fieldset><legend>Parâmetros hipotéticos do pote</legend>
<label>Pote atual (inclui aposta adversária)<input id="pot" type="number" min="0.000001" max="1000000000" step="any" value="100" required></label>
<label>Custo do call<input id="cost" type="number" min="0.000001" max="1000000000" step="any" value="20" required></label>
<label>Raise adicional acima do call<input id="extra" type="number" min="0.000001" max="1000000000" step="any" value="40" required></label>
<label>Grade de probabilidades de fold (0–1, em ordem)<input id="grid" type="text" value="0, 0.25, 0.5, 0.75, 1" style="min-width:270px" required></label>
</fieldset>
<fieldset><legend>Hipóteses de ranges (até cinco)</legend><div id="hypotheses"></div>
<button id="add" type="button">Adicionar hipótese</button></fieldset>
<p><label><input type="checkbox" id="ack" required> Declaro que os ranges e probabilidades são suposições minhas, não reconhecimento automático.</label></p>
<button id="export" type="submit">Exportar ASSUMPTIONS.json</button>
<p id="message" role="status" aria-live="polite"></p>
</form><p><small>O JSON exportado pode ser usado em <code>offline_acknowledged_sensitivity_bundle.py</code> com o relatório de cartas revisadas e o MP4. Não inclui cartas, identificação do jogador, ações observadas ou credenciais. Esta página não envia dados para a internet.</small></p>
</main>
<template id="hyp-template"><section class="hypothesis">
<label>Nome da hipótese<input class="name" type="text" maxlength="64" value="uniforme" required></label>
<button type="button" class="remove">Remover hipótese</button>
<div class="range"><label>Range se o adversário recebe call<select class="call-kind"><option value="uniform">Uniforme</option><option value="weighted_combos">Combinações ponderadas</option></select></label>
<label class="call-combos-wrap" hidden>Combinações (JSON: [{"cards":["As",...],"weight":1}])<textarea class="call-combos" spellcheck="false"></textarea></label>
<label>Simulações call<input class="call-iterations" type="number" value="500" min="2" max="50000" required></label>
<label>Semente call<input class="call-seed" type="number" value="42" min="0" max="4294967295" required></label></div>
<div class="range"><label>Range se o raise é pago<select class="raise-kind"><option value="uniform">Uniforme</option><option value="weighted_combos">Combinações ponderadas</option></select></label>
<label class="raise-combos-wrap" hidden>Combinações ponderadas (JSON)<textarea class="raise-combos" spellcheck="false"></textarea></label>
<label>Simulações raise pago<input class="raise-iterations" type="number" value="500" min="2" max="50000" required></label>
<label>Semente raise pago<input class="raise-seed" type="number" value="43" min="0" max="4294967295" required></label></div>
<label>Probabilidade-base de fold assumida (0–1)<input class="baseline" type="number" value="0.35" min="0" max="1" step="any" required></label>
</section></template>
<script>
'use strict';
const $=id=>document.getElementById(id), root=$('hypotheses');
const rank='23456789TJQKA',suits='cdhs';
function fail(s){throw Error(s)}
function num(value,name,lo,hi){let s=String(value).trim();if(!s)fail('Informe '+name);
 let n=Number(s);if(!Number.isFinite(n)||n<lo||n>hi)fail('Valor inválido: '+name);return n;}
function integer(value,name,lo,hi){let s=String(value).trim();if(!/^\d+$/.test(s))fail('Inteiro inválido: '+name);
 let n=Number(s);if(!Number.isSafeInteger(n)||n<lo||n>hi)fail('Inteiro fora do limite: '+name);return n;}
function combos(value){let a;try{a=JSON.parse(value)}catch{fail('JSON inválido de combinações ponderadas')}
 if(!Array.isArray(a)||a.length<1||a.length>1000)fail('Range deve ter 1 a 1000 combinações');
 let seen=new Set(),length=null;
 for(const x of a){if(!x||typeof x!=='object'||Array.isArray(x)||Object.keys(x).sort().join(',')!=='cards,weight')fail('Combinação deve conter cards e weight');
 if(!Array.isArray(x.cards)||![5,6].includes(x.cards.length)||new Set(x.cards).size!==x.cards.length)fail('Combinação PLO5/PLO6 inválida');
 if(length===null)length=x.cards.length;if(x.cards.length!==length)fail('Não misture PLO5/PLO6 no mesmo range');
 for(const c of x.cards){if(typeof c!=='string'||c.length!==2||!rank.includes(c[0])||!suits.includes(c[1]))fail('Carta inválida no range')}
 const key=[...x.cards].sort().join(',');if(seen.has(key))fail('Combinação repetida');seen.add(key);
 if(typeof x.weight!=='number'||!Number.isFinite(x.weight)||x.weight<=0||x.weight>1e6)fail('Peso inválido');}
 return a;}
function model(node,prefix){let kind=node.querySelector('.'+prefix+'-kind').value;
 if(kind==='uniform')return {kind:'uniform'};
 if(kind!=='weighted_combos')fail('Tipo de range inválido');
 return {kind:'weighted_combos',combos:combos(node.querySelector('.'+prefix+'-combos').value)};}
function addHyp(){if(root.children.length>=5)fail('Limite de cinco hipóteses');
 let n=$('hyp-template').content.firstElementChild.cloneNode(true);if(root.children.length)n.querySelector('.name').value='hipótese '+(root.children.length+1);
 n.querySelector('.remove').onclick=()=>{if(root.children.length>1)n.remove();else $('message').textContent='Mantenha pelo menos uma hipótese.'};
 for(const prefix of ['call','raise']){const kind=n.querySelector('.'+prefix+'-kind'),wrap=n.querySelector('.'+prefix+'-combos-wrap');
 kind.onchange=()=>wrap.hidden=kind.value!=='weighted_combos';}
 root.append(n);return n;}
function collect(){if(!$('ack').checked)fail('Confirme que os ranges são hipóteses.');
 let pot=num($('pot').value,'pote',0.000001,1e9),cost=num($('cost').value,'call',0.000001,1e9),extra=num($('extra').value,'raise adicional',0.000001,1e9);
 if(pot<cost||pot+cost+2*extra>1e9)fail('Geometria de pote inválida');
 let grid=$('grid').value.split(',').map(x=>num(x,'probabilidade da grade',0,1));
 if(grid.length<2||grid.length>21||grid.some((v,i)=>i&&v<=grid[i-1]))fail('Informe 2–21 probabilidades em ordem crescente, sem repetição');
 let labels=new Set(),hs=[];
 for(const n of root.children){let label=n.querySelector('.name').value.trim();
 if(!label||label.length>64||/[<>\\]/.test(label)||[...label].some(c=>/\p{C}/u.test(c))||labels.has(label))fail('Nome de hipótese inválido ou repetido');labels.add(label);
 const q=sel=>n.querySelector('.'+sel).value;
 hs.push({label,call_model:model(n,'call'),raise_called_model:model(n,'raise'),
 call_iterations:integer(q('call-iterations'),'iterações call',2,50000),
 raise_called_iterations:integer(q('raise-iterations'),'iterações raise',2,50000),
 call_seed:integer(q('call-seed'),'semente call',0,4294967295),
 raise_called_seed:integer(q('raise-seed'),'semente raise',0,4294967295),
 fold_probability_assumed:num(q('baseline'),'probabilidade-base de fold',0,1)});}
 if(hs.length<1||hs.length>5)fail('Informe 1–5 hipóteses');
 return {schema_version:1,pot_now:pot,call_cost:cost,raise_extra:extra,fold_probabilities:grid,hypotheses:hs};}
$('add').onclick=()=>{try{addHyp();$('message').textContent=''}catch(e){$('message').textContent=e.message}};
$('form').onsubmit=ev=>{ev.preventDefault();try{const obj=collect();const blob=new Blob([JSON.stringify(obj,null,2)+'\n'],{type:'application/json'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='ASSUMPTIONS.json';document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);$('message').textContent='JSON exportado. Valide-o antes de executar Monte Carlo.';
 }catch(e){$('message').textContent=e.message;}};
addHyp();
</script></body></html>
'''


def render():
    return HTML


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('create').add_argument('new_html')
    sub.add_parser('verify').add_argument('assumptions_json')
    args = parser.parse_args(argv)
    if args.command == 'create':
        out = Path(args.new_html)
        require(out.suffix == '.html' and out.parent.is_dir() and
                not out.parent.is_symlink() and not out.exists() and
                not out.is_symlink(), 'HTML output must be a new local file')
        with out.open('x', encoding='utf-8') as f:
            f.write(render())
        print(json.dumps({'html_created': str(out), 'offline_only': True}))
    else:
        print(json.dumps(validate_assumptions(read_json(args.assumptions_json))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
