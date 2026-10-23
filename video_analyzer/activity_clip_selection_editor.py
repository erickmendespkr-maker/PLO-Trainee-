"""Render a local-only human clip selection editor from an unapproved template.

The editor never authenticates video contents or authorizes equity/EV. Only
explicitly approved selections are exported; crop regions require confirmation.
The exported JSON is still validated by build_review_clip_plan before FFmpeg.
"""
import argparse
import base64
import hashlib
from html import escape
import json
import math
from pathlib import Path

from activity_review_clip_export import STATUS

_FIELDS = {'schema_version', 'analysis_status', 'source_queue_sha256',
           'source_draft_sha256', 'recording_sha256', 'regions', 'selections',
           'seconds_before', 'seconds_after', 'max_clips', 'regions_human_confirmed'}
_REGION_FIELDS = {'table_id', 'x', 'y', 'width', 'height'}
_SELECTION_FIELDS = {'table_id', 'hand_id', 'event_index', 'decision_timestamp',
                     'reviewer_approved', 'reviewer_priority', 'explanation'}


def validate_unapproved_template(template):
    """Reject malformed or preapproved input; preserve all SHA/identity fields."""
    if (not isinstance(template, dict) or set(template) != _FIELDS
            or type(template['schema_version']) is not int or template['schema_version'] != 1
            or template['analysis_status'] != STATUS
            or template['regions_human_confirmed'] is not False):
        raise ValueError('Expected unapproved clip selection template')
    for name in ('source_queue_sha256', 'source_draft_sha256', 'recording_sha256'):
        value = template[name]
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid SHA-256: ' + name)
    regions, selections = template['regions'], template['selections']
    if (not isinstance(regions, list) or not 1 <= len(regions) <= 4
            or not isinstance(selections, list) or not 1 <= len(selections) <= 100):
        raise ValueError('Invalid regions or decisions')
    ids = set()
    for row in regions:
        if (not isinstance(row, dict) or set(row) != _REGION_FIELDS
                or any(type(row[k]) is not int for k in _REGION_FIELDS)
                or not 1 <= row['table_id'] <= 4 or row['table_id'] in ids
                or min(row['x'], row['y']) < 0 or min(row['width'], row['height']) <= 0):
            raise ValueError('Invalid crop region')
        ids.add(row['table_id'])
    seen = set()
    for item in selections:
        if not isinstance(item, dict) or set(item) != _SELECTION_FIELDS:
            raise ValueError('Invalid decision')
        table, hand, event = item['table_id'], item['hand_id'], item['event_index']
        key = (table, hand, event)
        pts = item['decision_timestamp']
        if (type(table) is not int or table not in ids or type(event) is not int
                or not isinstance(hand, str) or not 0 < len(hand) <= 200
                or key in seen or type(pts) not in (float, int)
                or not math.isfinite(pts) or pts < 0
                or item['reviewer_approved'] is not False
                or item['reviewer_priority'] is not None or item['explanation'] != ''):
            raise ValueError('Expected unapproved unique decision')
        seen.add(key)
    for name, lower, upper in [('seconds_before', 0, 60), ('seconds_after', .01, 60)]:
        value = template[name]
        if type(value) not in (float, int) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError('Invalid clip interval')
    if type(template['max_clips']) is not int or not 1 <= template['max_clips'] <= 20:
        raise ValueError('Invalid max_clips')
    return template


SCRIPT = r'''"use strict";
const initial = __INITIAL__;
const regions = document.getElementById("regions");
const decisions = document.getElementById("decisions");
const status = document.getElementById("status");
function control(type, value, label, parent) {
  const wrap = document.createElement("label");
  wrap.textContent = label + " ";
  const node = document.createElement("input");
  node.type = type;
  if (type === "checkbox") node.checked = value === true;
  else node.value = value == null ? "" : String(value);
  if (type === "number") node.step = "any";
  wrap.appendChild(node); parent.appendChild(wrap);
  return node;
}
const cropControls = [];
for (const region of initial.regions) {
  const section = document.createElement("section");
  const heading = document.createElement("h2"); heading.textContent = "Mesa " + region.table_id;
  section.appendChild(heading);
  const nodes = {};
  for (const field of ["x", "y", "width", "height"]) nodes[field] = control("number", region[field], field, section);
  regions.appendChild(section);
  cropControls.push(nodes);
}
const confirmRegions = control("checkbox", false, "Conferi manualmente todas as regiões na gravação", regions);
const selectionControls = [];
for (const item of initial.selections) {
  const section = document.createElement("section");
  const heading = document.createElement("h2");
  heading.textContent = "Mesa " + item.table_id + " · Mão " + item.hand_id + " · Evento " + item.event_index + " · PTS " + item.decision_timestamp + "s";
  section.appendChild(heading);
  const approved = control("checkbox", false, "Incluir este corte (revisado manualmente)", section);
  const priority = control("number", "", "Prioridade subjetiva (0 a 1)", section);
  priority.min = "0"; priority.max = "1";
  const explanation = document.createElement("textarea");
  explanation.placeholder = "Explicação humana, sem alegar erro matemático não demonstrado";
  section.appendChild(explanation);
  decisions.appendChild(section);
  selectionControls.push({approved, priority, explanation});
}
const before = control("number", initial.seconds_before, "Segundos antes", document.getElementById("settings"));
const after = control("number", initial.seconds_after, "Segundos depois", document.getElementById("settings"));
const limit = control("number", initial.max_clips, "Máximo de clipes (1–20)", document.getElementById("settings"));
function finiteNumber(node, min, max, integer) {
  if (node.value.trim() === "") throw Error("Valor numérico obrigatório");
  const value = Number(node.value);
  if (!Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value)))
    throw Error("Valor numérico fora dos limites");
  return value;
}
function exportSelection() {
  if (!confirmRegions.checked) throw Error("Confirme manualmente as regiões das mesas");
  const output = structuredClone(initial);
  output.regions_human_confirmed = true;
  for (let i = 0; i < output.regions.length; i++) {
    for (const field of ["x", "y", "width", "height"])
      output.regions[i][field] = finiteNumber(cropControls[i][field], 0, 100000, true);
    if (!output.regions[i].width || !output.regions[i].height) throw Error("Região vazia");
  }
  output.seconds_before = finiteNumber(before, 0, 60, false);
  output.seconds_after = finiteNumber(after, .01, 60, false);
  output.max_clips = finiteNumber(limit, 1, 20, true);
  output.selections = output.selections.filter((item, index) => {
    const controls = selectionControls[index];
    if (!controls.approved.checked) return false;
    item.reviewer_approved = true;
    item.reviewer_priority = finiteNumber(controls.priority, 0, 1, false);
    item.explanation = controls.explanation.value.trim();
    if (!item.explanation || item.explanation.length > 500) throw Error("Explicação humana obrigatória (até 500 caracteres)");
    return true;
  });
  if (!output.selections.length) throw Error("Selecione ao menos uma decisão");
  return output;
}
document.getElementById("download").addEventListener("click", () => {
  try {
    const data = exportSelection();
    const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], {type:"application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = "plo-clips-" + initial.source_queue_sha256.slice(0, 12) + ".json";
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = "Seleção exportada. A validação Python/FFmpeg ainda é obrigatória; nenhum EV foi calculado.";
  } catch (err) { status.textContent = "Erro: " + String(err.message); }
});'''


def render_clip_selection_editor(template):
    validate_unapproved_template(template)
    literal = json.dumps(template, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    literal = (literal.replace('<', r'\u003c').replace('>', r'\u003e')
               .replace('&', r'\u0026').replace('\u2028', r'\u2028').replace('\u2029', r'\u2029'))
    script = SCRIPT.replace('__INITIAL__', literal)
    digest = base64.b64encode(hashlib.sha256(script.encode('utf-8')).digest()).decode('ascii')
    policy = ("default-src 'none'; script-src 'sha256-" + digest + "'; "
              "style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; "
              "object-src 'none'; base-uri 'none'; form-action 'none'")
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="' + escape(policy, quote=True) + '">'
            '<title>PLO Trainee — seleção offline de cortes</title><style>'
            'body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:1rem}'
            'section{border:1px solid #888;padding:1rem;margin:1rem 0}'
            'label{display:inline-flex;flex-direction:column;margin:.4rem;min-width:160px}'
            'input{padding:.3rem}textarea{display:block;width:95%;min-height:3rem}'
            'button{padding:.8rem;cursor:pointer}</style></head><body>'
            '<h1>Seleção de cortes — PLO5/PLO6 offline</h1>'
            '<p>Confira o vídeo original. Regiões são sugestões, não detecção validada. '
            'Prioridades são subjetivas. Nenhuma seleção comprova erro, equity ou EV. '
            'O JSON exportado deve passar pela validação Python antes do FFmpeg.</p>'
            '<p>Gravação SHA-256: ' + template['recording_sha256'] + '</p>'
            '<h2>Regiões das mesas</h2><div id="regions"></div>'
            '<h2>Decisões disponíveis</h2><div id="decisions"></div>'
            '<h2>Intervalos</h2><div id="settings"></div>'
            '<p><button id="download" type="button">Exportar seleção JSON</button></p>'
            '<p id="status" role="status"></p><script>' + script + '</script></body></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('selection_template_json')
    parser.add_argument('output_html')
    args = parser.parse_args(argv)
    source, output = Path(args.selection_template_json), Path(args.output_html)
    if output.exists() or output.is_symlink() or source.resolve() == output.resolve():
        raise ValueError('Output must be new and distinct from input')
    template = json.loads(source.read_text(encoding='utf-8'))
    html = render_clip_selection_editor(template)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(html)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
