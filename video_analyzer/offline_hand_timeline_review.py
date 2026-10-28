"""Create a fully offline review report from Cycle 174 hand drafts.

Usage: python offline_hand_timeline_review.py HAND_DRAFTS_JSON NEW_OUTPUT_DIR

The HTML viewer accepts an optional local recording via file picker; it never uploads
anything. Hand boundaries and OCR remain unverified; no equity or EV is computed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_JSON = 8 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
CARD = re.compile(r"[2-9TJQKA][cdhs]\Z")
AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?\Z")
FIELDS = {"hero_cards", "board", "pot", "bet", "stack", "action"}
ACTIONS = {"fold", "check", "call", "bet", "raise", "all-in"}
STREET = {0: "preflop_or_unknown", 3: "flop", 4: "turn", 5: "river"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
            "Unsafe JSON input")
    return json.loads(p.read_text("utf-8"), object_pairs_hook=unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 86400


def sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def validate_field(field, value, variant):
    require(type(value) is str and 0 < len(value) <= 128 and value == value.strip(),
            "Invalid reviewed value")
    if field in {"pot", "bet", "stack"}:
        require(AMOUNT.fullmatch(value) is not None, "Invalid amount")
    elif field == "action":
        require(value in ACTIONS, "Invalid action")
    else:
        cards = value.split(" ")
        require(all(CARD.fullmatch(c) for c in cards) and len(cards) == len(set(cards)),
                "Invalid cards")
        if field == "hero_cards":
            require(len(cards) == (5 if variant == "PLO5" else 6), "Invalid hero count")
        else:
            require(1 <= len(cards) <= 5, "Invalid board count")


def timeline(doc):
    require(type(doc) is dict and type(doc.get("schema_version")) is int
            and doc["schema_version"] == 1
            and doc.get("analysis_status") == "offline_reviewed_hand_drafts_only"
            and doc.get("hands_reconstructed") is False
            and doc.get("ready_for_equity_or_ev") is False
            and all(sha(doc.get(k)) for k in (
                "source_reviewed_report_sha256", "source_boundaries_sha256",
                "source_roi_ocr_report_sha256"))
            and type(doc.get("hands")) is list and 1 <= len(doc["hands"]) <= 200,
            "Invalid draft provenance")
    seen_hands, seen_proposals, output, by_table = set(), set(), [], {i: [] for i in range(1, 5)}
    for hand in doc["hands"]:
        require(type(hand) is dict and type(hand.get("hand_id")) is str
                and IDENT.fullmatch(hand["hand_id"]) is not None
                and hand["hand_id"] not in seen_hands
                and type(hand.get("table_id")) is int and 1 <= hand["table_id"] <= 4
                and hand.get("variant") in ("PLO5", "PLO6")
                and number(hand.get("start_seconds")) and number(hand.get("end_seconds"))
                and hand["start_seconds"] < hand["end_seconds"]
                and hand.get("boundary_origin") == "manual_unverified"
                and type(hand.get("boundary_note")) is str
                and 0 < len(hand["boundary_note"].strip()) <= 500
                and hand.get("status") == "draft_requires_human_reconstruction"
                and hand.get("ready_for_equity_or_ev") is False
                and type(hand.get("reviewed_fields")) is dict
                and set(hand["reviewed_fields"]).issubset(FIELDS)
                and type(hand.get("observation_indices")) is list
                and type(hand.get("unresolved_indices")) is list
                and type(hand.get("missing_fields")) is list
                and type(hand.get("consistency_warnings")) is list,
                "Invalid draft hand")
        seen_hands.add(hand["hand_id"])
        by_table[hand["table_id"]].append(hand)
        observed = hand["observation_indices"]
        unresolved = hand["unresolved_indices"]
        require(len(observed) <= 2000 and len(set(observed)) == len(observed)
                and all(type(i) is int and i >= 0 for i in observed)
                and len(set(unresolved)) == len(unresolved)
                and all(type(i) is int and i in observed for i in unresolved)
                and not (set(observed) & seen_proposals), "Duplicate observation identity")
        seen_proposals.update(observed)
        require(len(set(hand["missing_fields"])) == len(hand["missing_fields"])
                and all(f in FIELDS for f in hand["missing_fields"])
                and len(hand["consistency_warnings"]) <= 100
                and all(type(w) is str and len(w) <= 128 for w in hand["consistency_warnings"]),
                "Invalid draft warnings")
        events, used = [], set(unresolved)
        for field, entries in hand["reviewed_fields"].items():
            require(type(entries) is list and 1 <= len(entries) <= 2000,
                    "Invalid field entries")
            for entry in entries:
                require(type(entry) is dict
                        and type(entry.get("proposal_index")) is int
                        and entry["proposal_index"] in observed
                        and entry["proposal_index"] not in used
                        and number(entry.get("timestamp_seconds"))
                        and hand["start_seconds"] <= entry["timestamp_seconds"] < hand["end_seconds"]
                        and entry.get("review") in ("confirmed", "corrected"),
                        "Invalid reviewed observation")
                validate_field(field, entry.get("value"), hand["variant"])
                used.add(entry["proposal_index"])
                events.append({"proposal_index": entry["proposal_index"],
                               "timestamp_seconds": entry["timestamp_seconds"],
                               "field": field, "value": entry["value"],
                               "review": entry["review"]})
        require(used == set(observed), "Observation indices not accounted for")
        require(set(hand["missing_fields"]) == {f for f in ("hero_cards", "board", "pot", "action")
                                                 if f not in hand["reviewed_fields"]},
                "Missing fields mismatch")
        events.sort(key=lambda e: (e["timestamp_seconds"], e["proposal_index"]))
        warnings = set(hand["consistency_warnings"])
        board_events = [e for e in events if e["field"] == "board"]
        previous = None
        for event in board_events:
            cards = event["value"].split()
            if len(cards) in (1, 2):
                warnings.add("incomplete_board_snapshot")
            if previous is not None:
                if len(cards) < len(previous):
                    warnings.add("board_regressed_in_time")
                elif cards[:len(previous)] != previous:
                    warnings.add("board_changed_nonprefix")
                if len(cards) - len(previous) > 1:
                    warnings.add("missing_intermediate_board_snapshot")
            previous = cards
        hero_events = [e for e in events if e["field"] == "hero_cards"]
        if len({frozenset(e["value"].split()) for e in hero_events}) > 1:
            warnings.add("hero_cards_changed_in_interval")
        if hero_events and board_events:
            hero = set(hero_events[0]["value"].split())
            if any(hero.intersection(e["value"].split()) for e in board_events):
                warnings.add("hero_board_card_collision")
        if not events:
            warnings.add("no_resolved_observations")
        if unresolved:
            warnings.add("unresolved_ocr_observations")
        output.append({
            "hand_id": hand["hand_id"], "table_id": hand["table_id"],
            "variant": hand["variant"], "start_seconds": hand["start_seconds"],
            "end_seconds": hand["end_seconds"], "boundary_origin": "manual_unverified",
            "boundary_note": hand["boundary_note"], "events": events,
            "unresolved_indices": sorted(unresolved),
            "missing_fields": hand["missing_fields"],
            "warnings": sorted(warnings),
            "observed_streets": sorted({STREET[len(e["value"].split())]
                                        for e in board_events if len(e["value"].split()) in STREET}),
            "status": "review_required", "ready_for_equity_or_ev": False,
        })
    for hands in by_table.values():
        hands.sort(key=lambda h: h["start_seconds"])
        for first, second in zip(hands, hands[1:]):
            require(first["end_seconds"] <= second["start_seconds"],
                    "Overlapping manual hand boundaries")
    output.sort(key=lambda h: (h["table_id"], h["start_seconds"], h["hand_id"]))
    return output


# The interface never reads arbitrary local paths: the user selects a video file locally.
# It does not send data to a server, and exported annotations do not overwrite evidence.
STYLE = """body{font:15px system-ui,sans-serif;margin:0;background:#101724;color:#e9eef5}
header{padding:18px 22px;background:#1c2b40}main{max-width:1200px;margin:auto;padding:20px}
section{background:#1a2638;border:1px solid #34445c;border-radius:10px;padding:15px;margin:12px 0}
label{display:block;margin:8px 0}input,select,textarea,button{font:inherit;padding:7px;border-radius:6px}
input,select,textarea{background:#101724;color:#fff;border:1px solid #67778b}
input[type=number]{width:90px}textarea{width:min(100%,650px);box-sizing:border-box}
button{cursor:pointer;background:#b9d7ff;color:#102038;border:0;margin:4px}
video{width:min(100%,850px);max-height:400px;background:#000}
small,.muted{color:#b8c5d4}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #40516b;padding:6px;text-align:left}
.warn{color:#ffce81}.status{font-weight:700} .toolbar{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
"""
SCRIPT = r"""
'use strict';
const DATA = __DATA__;
const root=document.getElementById('hands');
const player=document.getElementById('video');
const edits=new Map();let objectUrl=null;
function element(tag, text, parent, cls){const el=document.createElement(tag);if(text!==null)el.textContent=text;
 if(cls)el.className=cls;if(parent)parent.appendChild(el);return el;}
function jump(time){if(!player.src){document.getElementById('message').textContent='Selecione um video local antes de navegar.';return;}
 player.currentTime=Math.max(0,Number(time));player.play().catch(()=>{});}
function fmt(v){return Number(v).toFixed(2)+' s';}
for(const hand of DATA.hands){
 const section=element('section',null,root);
 element('h2','Mesa '+hand.table_id+' · '+hand.hand_id+' · '+hand.variant,section);
 element('p','Limites manuais, não verificados. Evidência insuficiente para equity/EV.',section,'warn');
 const toolbar=element('div',null,section,'toolbar');
 element('button','Ir ao início '+fmt(hand.start_seconds),toolbar).onclick=()=>jump(hand.start_seconds);
 element('button','Ir ao fim '+fmt(hand.end_seconds),toolbar).onclick=()=>jump(hand.end_seconds);
 element('span','Observações confirmadas/corrigidas: '+hand.events.length,toolbar);
 const warns=[...hand.warnings,...hand.missing_fields.map(f=>'Campo ausente: '+f)];
 element('p',warns.length?'Atenção: '+warns.join(' · '):'Sem alertas estruturais; revisão ainda obrigatória.',section,'warn');
 const table=element('table',null,section),thead=element('thead',null,table),head=element('tr',null,thead);
 for(const v of ['PTS','Campo','Valor revisado','Estado'])element('th',v,head);
 const body=element('tbody',null,table);
 for(const event of hand.events){const tr=element('tr',null,body);
 const td=element('td',null,tr);element('button',fmt(event.timestamp_seconds),td).onclick=()=>jump(event.timestamp_seconds);
 element('td',event.field,tr);element('td',event.value,tr);element('td',event.review,tr);}
 const fields=element('div',null,section,'toolbar');
 const startLabel=element('label','Início (s) ',fields),start=element('input',null,startLabel);start.type='number';start.min=0;start.step='0.01';start.value=hand.start_seconds;
 const endLabel=element('label','Fim (s) ',fields),end=element('input',null,endLabel);end.type='number';end.min=0;end.step='0.01';end.value=hand.end_seconds;
 const stateLabel=element('label','Revisão ',fields),state=element('select',null,stateLabel);
 for(const [value,name] of [['pending','Pendente'],['confirmed','Confirmar limites'],['corrected','Corrigir limites'],['inconclusive','Inconclusivo']]){
 const o=element('option',name,state);o.value=value;}
 const noteLabel=element('label','Justificativa/observações ',section),note=element('textarea',null,noteLabel);
 note.rows=2;note.maxLength=500;note.placeholder='Explique correções e incertezas';
 edits.set(hand.hand_id,{hand,start,end,state,note});
}
document.getElementById('file').addEventListener('change',e=>{
 if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=null;player.removeAttribute('src');
 const f=e.target.files?.[0];if(f){objectUrl=URL.createObjectURL(f);player.src=objectUrl;player.load();}
});
document.getElementById('export').addEventListener('click',()=>{
 const out=[];const byTable=new Map();
 for(const {hand,start,end,state,note} of edits.values()){
 const a=Number(start.value),b=Number(end.value),s=state.value,n=note.value.trim();
 if(!Number.isFinite(a)||!Number.isFinite(b)||a<0||b<=a||b>86400||
    (s==='corrected'&&!n)||n.length>500){alert('Revise os limites e a justificativa: '+hand.hand_id);return;}
 if(s!=='corrected'&&(a!==hand.start_seconds||b!==hand.end_seconds)){
   alert('Limites alterados precisam do estado Corrigir: '+hand.hand_id);return;}
 if(s==='corrected'&&(a===hand.start_seconds&&b===hand.end_seconds)){
   alert('Use Corrigir somente quando houver alteração: '+hand.hand_id);return;}
 if(!byTable.has(hand.table_id))byTable.set(hand.table_id,[]);
 byTable.get(hand.table_id).push([a,b,hand.hand_id]);
 out.push({hand_id:hand.hand_id,table_id:hand.table_id,review_status:s,
   start_seconds:a,end_seconds:b,note:n});
 }
 for(const list of byTable.values()){
 list.sort((a,b)=>a[0]-b[0]);for(let i=1;i<list.length;i++)if(list[i-1][1]>list[i][0]){
 alert('Intervalos sobrepostos na mesma mesa: '+list[i-1][2]+' e '+list[i][2]);return;}
 }
 const payload={schema_version:1,source_hand_drafts_sha256:DATA.source_hand_drafts_sha256,
   review_kind:'manual_boundaries_only',ready_for_equity_or_ev:false,annotations:out};
 const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)+'\n'],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download='hand_boundary_annotations.json';a.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.getElementById('message').textContent='Anotações exportadas localmente. Nenhuma análise de EV foi autorizada.';
});
"""


def render_html(report):
    safe = json.dumps(report, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    script = SCRIPT.replace("__DATA__", safe)
    return ("<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
            "script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src blob:;\">"
            "<title>PLO Trainee — revisão offline de mãos</title><style>" + STYLE +
            "</style></head><body><header><h1>PLO Trainee · Revisão offline</h1>"
            "<p>Somente gravações. Não é assistência ao vivo. OCR e limites ainda não são fatos confirmados.</p>"
            "</header><main><section><label>Vídeo local (opcional) <input id=file type=file accept='video/mp4,video/webm'></label>"
            "<video id=video controls preload=metadata></video><p id=message class=muted>"
            "O arquivo permanece no seu navegador, sem upload.</p>"
            "<button id=export>Exportar anotações JSON</button></section>"
            "<div id=hands></div></main><script>" + script + "</script></body></html>\n")


def build(drafts_path, output_dir):
    drafts_path, output_dir = Path(drafts_path), Path(output_dir)
    require(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
            and not output_dir.exists() and not output_dir.is_symlink()
            and IDENT.fullmatch(output_dir.name) is not None, "Unsafe output directory")
    original_sha = digest(drafts_path)
    hands = timeline(read_json(drafts_path))
    report = {
        "schema_version": 1, "analysis_status": "offline_manual_timeline_review_only",
        "source_hand_drafts_sha256": original_sha, "hands_reconstructed": False,
        "ready_for_equity_or_ev": False, "hands": hands,
        "warning": "OCR and manual hand boundaries are unverified; do not infer equity/EV."}
    with tempfile.TemporaryDirectory(prefix=".plo_timeline_", dir=output_dir.parent) as temp:
        stage = Path(temp)
        (stage / "hand_timeline_review.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", "utf-8")
        (stage / "hand_timeline_review.html").write_text(render_html(report), "utf-8")
        require(digest(drafts_path) == original_sha, "Input changed during processing")
        require(not output_dir.exists(), "Output appeared during processing")
        os.rename(stage, output_dir)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hand_drafts_json")
    parser.add_argument("new_output_dir")
    args = parser.parse_args(argv)
    result = build(args.hand_drafts_json, args.new_output_dir)
    print(json.dumps({"hands": len(result["hands"]), "review_required": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
