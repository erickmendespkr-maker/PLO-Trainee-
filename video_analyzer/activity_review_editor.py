"""Offline editable OCR decision worksheet with fail-closed draft validation.

An HTML edit or human checkbox is NOT video authentication or permission for EV.
Only a separately audited evidence gate can authorize mathematical scenarios.
"""
import argparse
import copy
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re

from activity_review_packet import build_review_packet
from activity_review_draft_binding import check_draft_binding

FIELDS = ('hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount')
CARD = re.compile(r'[2-9TJQKA][shdc]\Z')

# Script does not use eval, fetch, network resources, innerHTML or remote assets.
SCRIPT = r'''"use strict";
const initial = __INITIAL__;
const fields = ["hero_cards", "board", "observed_action", "pot_before_action", "call_amount"];
const labels = {hero_cards:"Cartas privadas (5 ou 6, separadas por vírgula)",board:"Board (0, 3, 4 ou 5 cartas)",observed_action:"Ação (fold/call/raise)",pot_before_action:"Pote antes da ação",call_amount:"Valor para pagar"};
const root = document.getElementById("editor");
const status = document.getElementById("status");
function input(type, value, label, parent) {
  const wrap = document.createElement("label");
  wrap.textContent = label + " ";
  const element = document.createElement("input");
  element.type = type;
  if (type === "number") { element.step = "any"; element.min = "0"; }
  if (type === "checkbox") element.checked = Boolean(value);
  else element.value = value == null ? "" : String(value);
  wrap.appendChild(element);
  parent.appendChild(wrap);
  return element;
}
const controls = [];
for (const entry of initial.entries) {
  const section = document.createElement("section");
  const heading = document.createElement("h2");
  heading.textContent = "Mesa " + entry.table_id + " · Mão " + entry.hand_id + " · Evento " + entry.event_index + " · PTS " + entry.decision_timestamp + "s";
  section.appendChild(heading);
  const group = {};
  for (const field of fields) {
    const row = document.createElement("div"); row.className = "row";
    const cardField = field === "hero_cards" || field === "board";
    const numberField = field === "pot_before_action" || field === "call_amount";
    const current = entry.reviewed_fields[field];
    const value = input(numberField ? "number" : "text", cardField && Array.isArray(current.value) ? current.value.join(", ") : current.value, labels[field], row);
    const confidence = input("number", current.confidence, "Confiança (0–1)", row);
    confidence.max = "1";
    const timestamp = input("number", current.source_timestamp, "PTS da evidência (s)", row);
    const source = input("text", current.source, "Origem verificada manualmente", row);
    const confirmed = input("checkbox", current.human_confirmed, "Eu conferi este campo no vídeo", row);
    group[field] = {value, confidence, timestamp, source, confirmed, cardField, numberField};
    section.appendChild(row);
  }
  const notes = document.createElement("textarea"); notes.placeholder = "Observações da revisão (sem dados sensíveis)";
  notes.value = entry.reviewer_notes;
  section.appendChild(notes); root.appendChild(section);
  controls.push({group, notes});
}
function nullableNumber(node) { const value = node.value.trim(); return value === "" ? null : Number(value); }
function exportDraft() {
  const result = structuredClone(initial);
  result.analysis_status = "manual_review_draft_unverified_no_ev";
  result.ready_for_equity_or_ev = false;
  result.source_visual_content_verified = false;
  for (let i = 0; i < controls.length; i++) {
    const controlsForEntry = controls[i];
    const entry = result.entries[i];
    entry.human_confirmed = false;
    entry.ready_for_ev = false;
    entry.reviewer_notes = controlsForEntry.notes.value;
    for (const field of fields) {
      const form = controlsForEntry.group[field];
      const raw = form.value.value.trim();
      let value = raw === "" ? null : raw;
      if (value !== null && form.cardField) value = raw.split(",").map(x => x.trim());
      if (value !== null && form.numberField) value = Number(raw);
      entry.reviewed_fields[field] = {
        value, confidence: nullableNumber(form.confidence),
        source_timestamp: nullableNumber(form.timestamp),
        source: form.source.value.trim() || null,
        human_confirmed: form.confirmed.checked
      };
    }
  }
  return result;
}
document.getElementById("download").addEventListener("click", () => {
  try {
    const draft = exportDraft();
    for (const entry of draft.entries) for (const field of fields) {
      const record = entry.reviewed_fields[field];
      if (record.human_confirmed && (record.value === null || record.confidence === null || record.source_timestamp === null || !record.source))
        throw Error("Mesa " + entry.table_id + ": confirmação incompleta de " + field);
    }
    const blob = new Blob([JSON.stringify(draft, null, 2) + "\n"], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url;
    a.download = "plo-review-" + initial.source_queue_sha256.slice(0, 12) + ".json";
    a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = "Rascunho exportado. Execute a validação Python antes de utilizá-lo. Equity/EV continuam bloqueados.";
  } catch (err) { status.textContent = "Erro: " + String(err.message); }
});'''


def _safe_js_json(value):
    """Encode JSON as JS literal without creating an HTML script closing tag."""
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return (raw.replace('<', r'\u003c').replace('>', r'\u003e')
            .replace('&', r'\u0026').replace('\u2028', r'\u2028')
            .replace('\u2029', r'\u2029'))


def render_editor(queue):
    packet = build_review_packet(queue)
    template = packet['template']
    script = SCRIPT.replace('__INITIAL__', _safe_js_json(template))
    import base64
    digest = base64.b64encode(hashlib.sha256(script.encode('utf-8')).digest()).decode('ascii')
    policy = ("default-src 'none'; script-src 'sha256-" + digest + "'; "
              "style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; "
              "object-src 'none'; base-uri 'none'; form-action 'none'")
    html = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="' + escape(policy, quote=True) + '">'
            '<title>PLO Trainee — editor offline</title><style>'
            'body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:1rem}'
            'section{border:1px solid #888;padding:1rem;margin:1rem 0}'
            '.row{display:flex;flex-wrap:wrap;gap:1rem;margin:1rem 0;border-bottom:1px solid #ddd;padding-bottom:.7rem}'
            'label{display:flex;flex-direction:column;min-width:160px;flex:1}input{padding:.3rem}'
            'textarea{width:95%;min-height:3rem}button{padding:.8rem;cursor:pointer}'
            '</style></head><body><h1>Revisão manual PLO5/PLO6 — offline</h1>'
            '<p>Confira a gravação original antes de marcar cada campo. OCR é indício, '
            'não confirmação. Este editor não valida vídeo, não transmite dados e NÃO '
            'LIBERA EQUITY/EV. Salve o JSON e valide-o pelo comando Python.</p>'
            '<p>Fila vinculada ao SHA-256: ' + template['source_queue_sha256'] + '</p>'
            '<div id="editor"></div><button id="download" type="button">Exportar rascunho JSON</button>'
            '<p id="status" role="status"></p><script>' + script + '</script></body></html>')
    return html


def _number(value, *, probability=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Expected finite nonnegative number')
    if probability and value > 1:
        raise ValueError('Confidence exceeds one')
    return value


def validate_draft(queue, draft):
    """Validate structure, typed annotations, and queue binding; never approve EV."""
    template = build_review_packet(queue)['template']
    check_draft_binding(template, draft)
    for original, entry in zip(template['entries'], draft['entries']):
        notes = entry['reviewer_notes']
        if not isinstance(notes, str) or len(notes) > 2000:
            raise ValueError('Invalid notes')
        fields = entry['reviewed_fields']
        if not isinstance(fields, dict) or set(fields) != set(FIELDS):
            raise ValueError('Invalid reviewed field map')
        cards = []
        for field in FIELDS:
            record = fields[field]
            if not isinstance(record, dict) or set(record) != set(original['reviewed_fields'][field]):
                raise ValueError('Invalid field record')
            value, confidence, timestamp, source, confirmed = (record[k] for k in
                ('value', 'confidence', 'source_timestamp', 'source', 'human_confirmed'))
            if type(confirmed) is not bool:
                raise ValueError('Invalid human confirmation')
            if value is not None:
                if field in ('hero_cards', 'board'):
                    valid_lengths = (5, 6) if field == 'hero_cards' else (0, 3, 4, 5)
                    if not isinstance(value, list) or len(value) not in valid_lengths or any(
                        not isinstance(card, str) or not CARD.fullmatch(card) for card in value):
                        raise ValueError('Invalid cards')
                    cards.extend(value)
                elif field == 'observed_action':
                    if value not in ('fold', 'call', 'raise') or type(value) is not str:
                        raise ValueError('Invalid action')
                else:
                    _number(value)
            if confidence is not None:
                _number(confidence, probability=True)
            if timestamp is not None:
                _number(timestamp)
                limit = entry['decision_timestamp']
                if timestamp > limit or (field in ('hero_cards', 'board', 'pot_before_action') and timestamp >= limit):
                    raise ValueError('Future or simultaneous source timestamp')
            if source is not None and (not isinstance(source, str) or not source.strip() or len(source) > 256):
                raise ValueError('Invalid source description')
            if confirmed and (value is None or confidence is None or timestamp is None or source is None):
                raise ValueError('Confirmed field lacks manual evidence description')
        if len(set(cards)) != len(cards):
            raise ValueError('Duplicate cards')
    return copy.deepcopy(draft)


def _write_new(path, content):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as f:
        f.write(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    render = sub.add_parser('render')
    render.add_argument('queue_json'); render.add_argument('output_html')
    validate = sub.add_parser('validate')
    validate.add_argument('queue_json'); validate.add_argument('draft_json'); validate.add_argument('output_json')
    args = parser.parse_args(argv)
    queue_path = Path(args.queue_json)
    queue = json.loads(queue_path.read_text(encoding='utf-8'))
    if args.command == 'render':
        if queue_path.resolve() == Path(args.output_html).resolve():
            raise ValueError('Output would overwrite input')
        _write_new(args.output_html, render_editor(queue))
    else:
        if len({queue_path.resolve(), Path(args.draft_json).resolve(), Path(args.output_json).resolve()}) != 3:
            raise ValueError('Output would overwrite input')
        draft = json.loads(Path(args.draft_json).read_text(encoding='utf-8'))
        verified = validate_draft(queue, draft)
        _write_new(args.output_json, json.dumps(verified, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
