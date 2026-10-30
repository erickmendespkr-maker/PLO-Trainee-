"""Generate an offline per-hand/per-street review worksheet from OCR reconstruction.

Usage: python offline_hand_street_review.py RECONSTRUCTION.json NEW_REVIEW.html NEW_WORKSHEET.json

This is an *unverified human review draft*, never a math-ready input. No video,
network, gambling service, or Monte Carlo is accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

SHA = re.compile(r'[0-9a-f]{64}\Z')
ID = re.compile(r'[A-Za-z0-9_-]{1,40}\Z')
CARD = re.compile(r'[23456789TJQKA][cdhs]\Z')
MAX_BYTES = 4_000_000
MAX_HANDS = 100


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_BYTES,
            'invalid or oversized reconstruction')
    return json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def validate(report):
    require(type(report) is dict and report.get('schema_version') == 1 and
            report.get('status') == 'offline_ocr_hand_reconstruction_unverified_not_math_ready' and
            type(report.get('source_ledger_sha256')) is str and SHA.fullmatch(report['source_ledger_sha256']) and
            type(report.get('source_video_sha256_claim')) is str and SHA.fullmatch(report['source_video_sha256_claim']) and
            type(report.get('hand_count')) is int and
            type(report.get('hands')) is list and
            1 <= len(report['hands']) <= MAX_HANDS and
            report['hand_count'] == len(report['hands']) and
            type(report.get('eligible_for_equity')) is int and report['eligible_for_equity'] == 0 and
            report.get('equity_or_ev_calculated') is False and
            report.get('human_review_required') is True and
            report.get('original_video_cards_not_independently_verified') is True,
            'unsupported or unsafe reconstruction')
    seen = set()
    tables = set()
    for hand in report['hands']:
        require(type(hand) is dict and
                type(hand.get('hand_id')) is str and ID.fullmatch(hand['hand_id']) and
                hand['hand_id'] not in seen and
                type(hand.get('table_id')) is str and ID.fullmatch(hand['table_id']) and
                hand.get('math_ready') is False and hand.get('eligible_for_equity') is False and
                hand.get('variant_candidate_unverified') in (None, 'PLO5', 'PLO6') and
                type(hand.get('review_flags')) is list and
                len(hand['review_flags']) <= 100 and
                all(type(f) is str and len(f) <= 80 for f in hand['review_flags']) and
                type(hand.get('card_candidates_unverified')) is dict and
                set(hand['card_candidates_unverified']) == {'hero_card', 'board_card'} and
                type(hand.get('other_selected_candidates_unverified')) is dict and
                set(hand['other_selected_candidates_unverified']) == {'variant', 'action', 'pot', 'stack'},
                'invalid reconstruction hand')
        seen.add(hand['hand_id'])
        tables.add(hand['table_id'])
        for field, max_slots in (('hero_card', 6), ('board_card', 5)):
            slots = hand['card_candidates_unverified'][field]
            require(type(slots) is dict and len(slots) <= max_slots, 'invalid card slots')
            for slot, candidates in slots.items():
                require(type(slot) is str and slot in {str(i) for i in range(max_slots)} and
                        type(candidates) is list and 1 <= len(candidates) <= 52 and
                        all(type(c) is str and CARD.fullmatch(c) for c in candidates) and
                        len(set(candidates)) == len(candidates), 'invalid card candidate')
        for field, values in hand['other_selected_candidates_unverified'].items():
            require(type(values) is list and len(values) <= 6000, 'invalid non-card observations')
            for value in values:
                require(type(value) is dict and set(value) == {'value', 'pts_seconds'} and
                        type(value['value']) is str and 1 <= len(value['value']) <= 80 and
                        all(32 <= ord(c) < 127 for c in value['value']) and
                        type(value['pts_seconds']) in (int, float) and
                        0 <= value['pts_seconds'] <= 14400, 'invalid non-card observation')
    require(len(tables) <= 4, 'more than four tables')


def worksheet(report, source_sha):
    validate(report)
    require(type(source_sha) is str and SHA.fullmatch(source_sha), 'invalid source hash')
    hands = []
    for hand in report['hands']:
        variant = hand['variant_candidate_unverified']
        fields = []
        for field, count in (('hero_card', 6), ('board_card', 5)):
            for slot in range(count):
                if field == 'hero_card' and variant == 'PLO5' and slot == 5:
                    continue
                street = ('preflop' if field == 'hero_card' else
                          'flop' if slot < 3 else 'turn' if slot == 3 else 'river')
                fields.append({'field': field, 'slot': slot, 'street': street,
                               'ocr_candidates_unverified': hand['card_candidates_unverified'][field].get(str(slot), []),
                               'review_status': 'unreviewed', 'reviewer_value': None})
        for field in ('action', 'pot', 'stack'):
            values = hand['other_selected_candidates_unverified'][field]
            fields.append({'field': field, 'slot': None, 'street': 'unknown',
                           'ocr_candidates_unverified': sorted(set(v['value'] for v in values)),
                           'review_status': 'unreviewed', 'reviewer_value': None})
        fields.append({'field': 'variant', 'slot': None, 'street': 'unknown',
                       'ocr_candidates_unverified': [variant] if variant else [],
                       'review_status': 'unreviewed', 'reviewer_value': None})
        hands.append({'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                      'review_flags': sorted(set(hand['review_flags'])), 'fields': fields,
                      'math_ready': False, 'eligible_for_equity': False})
    return {'schema_version': 1, 'status': 'offline_hand_street_review_worksheet_not_math_ready',
            'source_reconstruction_sha256': source_sha,
            'source_ledger_sha256': report['source_ledger_sha256'],
            'source_video_sha256_claim': report['source_video_sha256_claim'],
            'hands': hands, 'hand_count': len(hands), 'eligible_for_equity': 0,
            'equity_or_ev_calculated': False, 'human_review_not_authenticated': True,
            'reviewer_claims_not_verified_against_video': True,
            'warning': 'This worksheet is for offline human inspection. No card, action, pot, stack, or variant is independently verified. Never use this draft directly for equity/EV.'}


STYLE = '''body{font:15px system-ui,sans-serif;max-width:1100px;margin:auto;padding:22px;background:#f8fafc;color:#15263b}
header{border-bottom:2px solid #334155;margin-bottom:20px}article{background:white;border:1px solid #cbd5e1;border-radius:12px;margin:14px 0;padding:16px}
section{margin:12px 0}h3{margin:8px 0}.field{display:grid;grid-template-columns:110px 110px minmax(130px,1fr) 145px minmax(120px,1fr);gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid #e2e8f0}
input,select,button{font:inherit;padding:7px;max-width:100%;box-sizing:border-box}button{cursor:pointer;background:#164e63;color:white;border:0;border-radius:6px}
small{color:#475569}.warning{background:#fff7ed;border-left:4px solid #c2410c;padding:10px} @media(max-width:650px){.field{grid-template-columns:1fr 1fr}.field>*{min-width:0}}'''

SCRIPT = r'''"use strict";
const packet = JSON.parse(document.getElementById("packet").textContent);
const root = document.getElementById("hands");
function el(tag, text, parent, className) {
  const n = document.createElement(tag); if(text !== null) n.textContent = text;
  if(className) n.className = className; parent.appendChild(n); return n;
}
for (const hand of packet.hands) {
  const article = el("article", null, root);
  el("h2", hand.hand_id + " · " + hand.table_id, article);
  el("small", "Pendências: " + (hand.review_flags.join(", ") || "nenhuma sinalizada"), article);
  for (const street of ["preflop","flop","turn","river","unknown"]) {
    const fields = hand.fields.filter(f => f.street === street);
    if(!fields.length) continue;
    const sec = el("section",null,article); el("h3",street === "unknown" ? "Sem street comprovada" : street,sec);
    for(const field of fields) {
      const row = el("div",null,sec,"field");
      el("strong",field.field + (field.slot === null ? "" : " #" + field.slot),row);
      el("small",field.street,row);
      el("small",field.ocr_candidates_unverified.join(" / ") || "sem candidato OCR",row);
      const sel = el("select",null,row);
      for(const [value,label] of [["unreviewed","Não revisado"],["confirmed_by_reviewer","Declaração manual"],["rejected","Rejeitado"],["unknown","Não visível"]]) {
        const opt = document.createElement("option"); opt.value=value; opt.textContent=label; sel.appendChild(opt);
      }
      const input = el("input",null,row); input.maxLength=80; input.placeholder="Valor declarado";
      sel.addEventListener("change",()=>{field.review_status=sel.value;if(sel.value!=="confirmed_by_reviewer"){input.value="";field.reviewer_value=null;}});
      input.addEventListener("input",()=>{field.reviewer_value=input.value || null;});
    }
  }
}
document.getElementById("export").addEventListener("click",()=>{
  const output = structuredClone(packet);
  for(const hand of output.hands) for(const field of hand.fields){
    if(field.review_status!=="confirmed_by_reviewer") field.reviewer_value=null;
  }
  const file = new Blob([JSON.stringify(output,null,2)+"\n"],{type:"application/json"});
  const url = URL.createObjectURL(file); const a=document.createElement("a");
  a.href=url; a.download="hand_street_review_draft.json"; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});'''


def render(packet):
    # Escape < so an untrusted candidate cannot terminate the JSON script element.
    embedded = json.dumps(packet, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PLO Trainee — revisão de mãos</title><style>' + STYLE + '</style></head><body>'
            '<header><h1>Revisão offline de mãos e streets</h1></header>'
            '<p class="warning"><b>Sem validação matemática.</b> Sugestões OCR não são fatos. '
            'Mesmo após preencher os campos, este rascunho não autoriza equity/EV.</p>'
            '<button id="export" type="button">Exportar rascunho JSON</button>'
            '<div id="hands"></div><script id="packet" type="application/json">' + embedded +
            '</script><script>' + SCRIPT + '</script></body></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reconstruction_json')
    parser.add_argument('new_review_html')
    parser.add_argument('new_worksheet_json')
    args = parser.parse_args(argv)
    source = Path(args.reconstruction_json)
    html_path, json_path = Path(args.new_review_html), Path(args.new_worksheet_json)
    require(html_path.suffix == '.html' and json_path.suffix == '.json' and
            html_path.resolve() != json_path.resolve() and
            all(p.parent.is_dir() and not p.parent.is_symlink() and not p.exists() and
                not p.is_symlink() and p.resolve() != source.resolve() for p in (html_path, json_path)),
            'outputs must be new, distinct files')
    before = digest(source)
    packet = worksheet(read(source), before)
    page = render(packet)
    require(digest(source) == before, 'source changed during generation')
    # Generate both in memory before writing; never overwrite existing files.
    with json_path.open('x', encoding='utf-8') as stream:
        json.dump(packet, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    try:
        with html_path.open('x', encoding='utf-8') as stream:
            stream.write(page)
    except Exception:
        json_path.unlink()
        raise
    print(json.dumps({'hands': packet['hand_count'], 'html': str(html_path),
                      'worksheet': str(json_path), 'eligible_for_equity': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
