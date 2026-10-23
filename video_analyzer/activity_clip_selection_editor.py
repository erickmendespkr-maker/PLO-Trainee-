"""Render a local-only human clip selection editor from an unapproved template.

The editor never authenticates video contents or authorizes equity/EV. Only
explicitly approved selections are exported; crop regions require confirmation.
The exported JSON is still validated by build_review_clip_plan before FFmpeg.
"""
import argparse
import base64
import binascii
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
_PREVIEW_FIELDS = {'recording_sha256', 'source_width', 'source_height',
                   'requested_timestamp_seconds', 'jpeg_sha256', 'jpeg_b64',
                   'frame_timing'}


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
const timelineFrames = __TIMELINE__;
let currentFrame = 0;
const reviewedFrames = new Set();
const regions = document.getElementById("regions");
const decisions = document.getElementById("decisions");
const status = document.getElementById("status");
const preview = document.getElementById("preview-frame");
const overlays = document.getElementById("region-overlay");
const sourceWidth = Number(document.body.dataset.frameWidth || 0);
const sourceHeight = Number(document.body.dataset.frameHeight || 0);
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
function updateOverlay() {
  if (!preview || !overlays) return;
  overlays.replaceChildren();
  for (let i = 0; i < initial.regions.length; i++) {
    const nodes = cropControls[i];
    const x = Number(nodes.x.value), y = Number(nodes.y.value);
    const w = Number(nodes.width.value), h = Number(nodes.height.value);
    const valid = [x,y,w,h].every(Number.isFinite) && x >= 0 && y >= 0 &&
      w > 0 && h > 0 && x + w <= sourceWidth && y + h <= sourceHeight;
    const box = document.createElement("div");
    box.className = "region-box" + (valid ? "" : " invalid");
    box.style.left = (Math.max(0, x) / sourceWidth * 100) + "%";
    box.style.top = (Math.max(0, y) / sourceHeight * 100) + "%";
    box.style.width = (Math.max(0, w) / sourceWidth * 100) + "%";
    box.style.height = (Math.max(0, h) / sourceHeight * 100) + "%";
    box.textContent = "Mesa " + initial.regions[i].table_id;
    overlays.appendChild(box);
  }
}
for (const nodes of cropControls) for (const field of ["x", "y", "width", "height"])
  nodes[field].addEventListener("input", () => {
    confirmRegions.checked = false;
    reviewedFrames.clear();
    const check = document.getElementById("frame-reviewed");
    if (check) check.checked = false;
    updateOverlay();
    displayFrame();
  });
updateOverlay();
const confirmRegions = control("checkbox", false, "Conferi manualmente todas as regiões na gravação", regions);
const frameLabel = document.getElementById("frame-label");
const frameReview = document.getElementById("frame-reviewed");
function displayFrame() {
  if (!timelineFrames.length) return;
  const item = timelineFrames[currentFrame];
  preview.src = "data:" + "image/jpeg;base64," + item.jpeg_b64;
  frameLabel.textContent = "Quadro " + (currentFrame + 1) + "/" + timelineFrames.length +
    " · busca aproximada " + item.requested_timestamp_seconds.toFixed(3) + "s · SHA-256 " + item.jpeg_sha256;
  frameReview.checked = reviewedFrames.has(currentFrame);
  document.getElementById("frame-progress").textContent =
    reviewedFrames.size + "/" + timelineFrames.length + " quadros conferidos";
}
if (timelineFrames.length) {
  frameReview.addEventListener("change", () => {
    if (frameReview.checked) reviewedFrames.add(currentFrame);
    else reviewedFrames.delete(currentFrame);
    confirmRegions.checked = false;
    displayFrame();
  });
  document.getElementById("frame-prev").addEventListener("click", () => {
    currentFrame = (currentFrame - 1 + timelineFrames.length) % timelineFrames.length;
    displayFrame();
  });
  document.getElementById("frame-next").addEventListener("click", () => {
    currentFrame = (currentFrame + 1) % timelineFrames.length;
    displayFrame();
  });
  displayFrame();
}

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
  if (timelineFrames.length && reviewedFrames.size !== timelineFrames.length)
    throw Error("Confira manualmente todos os quadros da gravação");
  if (!confirmRegions.checked) throw Error("Confirme manualmente as regiões das mesas");
  const output = structuredClone(initial);
  output.regions_human_confirmed = true;
  for (let i = 0; i < output.regions.length; i++) {
    for (const field of ["x", "y", "width", "height"])
      output.regions[i][field] = finiteNumber(cropControls[i][field], 0, 100000, true);
    if (!output.regions[i].width || !output.regions[i].height) throw Error("Região vazia");
  }
  if (preview) {
    for (const region of output.regions)
      if (region.x + region.width > sourceWidth || region.y + region.height > sourceHeight)
        throw Error("Região ultrapassa a imagem original");
    for (let i = 0; i < output.regions.length; i++)
      for (let j = i + 1; j < output.regions.length; j++) {
        const a = output.regions[i], b = output.regions[j];
        if (a.x < b.x + b.width && b.x < a.x + a.width &&
            a.y < b.y + b.height && b.y < a.y + a.height)
          throw Error("Regiões das mesas não podem se sobrepor");
      }
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


def _validate_preview(preview, template):
    if not isinstance(preview, dict) or set(preview) != _PREVIEW_FIELDS:
        raise ValueError('Invalid preview schema')
    if preview['recording_sha256'] != template['recording_sha256']:
        raise ValueError('Preview recording SHA-256 mismatch')
    if (type(preview['source_width']) is not int or type(preview['source_height']) is not int
            or not 1 <= preview['source_width'] <= 8192
            or not 1 <= preview['source_height'] <= 8192):
        raise ValueError('Invalid preview dimensions')
    ts = preview['requested_timestamp_seconds']
    if type(ts) not in (float, int) or not math.isfinite(ts) or ts < 0:
        raise ValueError('Invalid preview timestamp')
    if preview['frame_timing'] != 'approximate_ffmpeg_fast_seek_not_decision_evidence':
        raise ValueError('Invalid preview provenance')
    raw = preview['jpeg_b64']
    if not isinstance(raw, str) or len(raw) > 4 * 2 * 1024 * 1024 // 3 + 8:
        raise ValueError('Oversized or invalid preview')
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('Invalid preview encoding') from exc
    if (not 100 < len(decoded) <= 2 * 1024 * 1024
            or not decoded.startswith(b'\xff\xd8') or not decoded.endswith(b'\xff\xd9')
            or hashlib.sha256(decoded).hexdigest() != preview['jpeg_sha256']):
        raise ValueError('Preview JPEG or SHA-256 mismatch')


def render_clip_selection_editor(template, *, preview=None, preview_timeline=None):
    validate_unapproved_template(template)
    if preview is not None and preview_timeline is not None:
        raise ValueError('Use a single preview OR a preview timeline')
    if preview_timeline is not None:
        if (not isinstance(preview_timeline, dict)
                or set(preview_timeline) != {'schema_version', 'recording_sha256', 'frames'}
                or type(preview_timeline['schema_version']) is not int
                or preview_timeline['schema_version'] != 1
                or preview_timeline['recording_sha256'] != template['recording_sha256']
                or not isinstance(preview_timeline['frames'], list)
                or not 2 <= len(preview_timeline['frames']) <= 5):
            raise ValueError('Invalid preview timeline schema')
        previous = -1.0
        total = 0
        dims = None
        for frame in preview_timeline['frames']:
            _validate_preview(frame, template)
            if frame['requested_timestamp_seconds'] <= previous:
                raise ValueError('Timeline timestamps must be increasing')
            previous = frame['requested_timestamp_seconds']
            if dims is None:
                dims = (frame['source_width'], frame['source_height'])
            if dims != (frame['source_width'], frame['source_height']):
                raise ValueError('Timeline dimensions must be identical')
            total += len(frame['jpeg_b64']) * 3 // 4
            if total > 6 * 1024 * 1024:
                raise ValueError('Oversized preview timeline')
        preview = preview_timeline['frames'][0]
    elif preview is not None:
        _validate_preview(preview, template)
    literal = json.dumps(template, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    literal = (literal.replace('<', r'\u003c').replace('>', r'\u003e')
               .replace('&', r'\u0026').replace('\u2028', r'\u2028').replace('\u2029', r'\u2029'))
    timeline_literal = json.dumps(preview_timeline['frames'] if preview_timeline else [],
                                  ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    script = (SCRIPT.replace('__INITIAL__', literal)
             .replace('__TIMELINE__', timeline_literal))
    digest = base64.b64encode(hashlib.sha256(script.encode('utf-8')).digest()).decode('ascii')
    policy = ("default-src 'none'; script-src 'sha256-" + digest + "'; "
              "style-src 'unsafe-inline'; connect-src 'none'; img-src data:; "
              "object-src 'none'; base-uri 'none'; form-action 'none'")
    preview_html = ''
    body_attrs = ''
    if preview is not None:
        body_attrs = (f' data-frame-width="{preview["source_width"]}"'
                      f' data-frame-height="{preview["source_height"]}"')
        preview_html = ('<h2>Conferência visual das regiões</h2>'
                        '<p>Quadro aproximado extraído localmente; não comprova cartas, ação, '
                        'equity nem timestamp exato. Confira outras partes do vídeo antes de confirmar.</p>'
                        f'<p>Busca FFmpeg: {preview["requested_timestamp_seconds"]:.3f}s '
                        f'· JPEG SHA-256: {preview["jpeg_sha256"]}</p>'
                        '<div class="preview-wrap">'
                        '<img id="preview-frame" alt="Quadro aproximado da gravação" '
                        'src="data:image/jpeg;base64,' + preview['jpeg_b64'] + '">'
                        '<div id="region-overlay" aria-hidden="true"></div></div>')
        if preview_timeline is not None:
            preview_html += ('<p id="frame-label"></p>'
                             '<p><button type="button" id="frame-prev">Quadro anterior</button> '
                             '<button type="button" id="frame-next">Próximo quadro</button></p>'
                             '<label><input type="checkbox" id="frame-reviewed">'
                             'Conferi manualmente esta imagem e as regiões</label>'
                             '<p id="frame-progress"></p>'
                             '<p>É obrigatório conferir todos os quadros antes de confirmar as regiões. '
                             'Amostras não garantem estabilidade entre quadros.</p>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="' + escape(policy, quote=True) + '">'
            '<title>PLO Trainee — seleção offline de cortes</title><style>'
            'body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:1rem}'
            'section{border:1px solid #888;padding:1rem;margin:1rem 0}'
            'label{display:inline-flex;flex-direction:column;margin:.4rem;min-width:160px}'
            'input{padding:.3rem}textarea{display:block;width:95%;min-height:3rem}'
            'button{padding:.8rem;cursor:pointer}'
            '.preview-wrap{position:relative;max-width:960px;width:100%}'
            '.preview-wrap img{display:block;width:100%;height:auto}'
            '#region-overlay{position:absolute;inset:0;pointer-events:none}'
            '.region-box{position:absolute;box-sizing:border-box;border:3px solid #08c;'
            'background:rgba(0,130,210,.12);font-weight:bold;color:#fff;'
            'text-shadow:1px 1px 2px #000;overflow:hidden}'
            '.region-box.invalid{border-color:#f44;background:rgba(255,0,0,.3)}'
            '</style></head><body' + body_attrs + '>'
            '<h1>Seleção de cortes — PLO5/PLO6 offline</h1>'
            '<p>Confira o vídeo original. Regiões são sugestões, não detecção validada. '
            'Prioridades são subjetivas. Nenhuma seleção comprova erro, equity ou EV. '
            'O JSON exportado deve passar pela validação Python antes do FFmpeg.</p>'
            '<p>Gravação SHA-256: ' + template['recording_sha256'] + '</p>'
            + preview_html + '<h2>Regiões das mesas</h2><div id="regions"></div>'
            '<h2>Decisões disponíveis</h2><div id="decisions"></div>'
            '<h2>Intervalos</h2><div id="settings"></div>'
            '<p><button id="download" type="button">Exportar seleção JSON</button></p>'
            '<p id="status" role="status"></p><script>' + script + '</script></body></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('selection_template_json')
    parser.add_argument('output_html')
    parser.add_argument('--video', help='Local recording to embed an approximate frame preview')
    parser.add_argument('--timestamp', type=float, default=None, help='Single preview seek in seconds')
    parser.add_argument('--timeline', action='store_true', help='Preview 3 spaced timestamps (10/50/90 percent)')
    args = parser.parse_args(argv)
    source, output = Path(args.selection_template_json), Path(args.output_html)
    if output.exists() or output.is_symlink() or source.resolve() == output.resolve():
        raise ValueError('Output must be new and distinct from input')
    template = json.loads(source.read_text(encoding='utf-8'))
    if args.timeline and args.timestamp is not None:
        raise ValueError('--timeline cannot be combined with --timestamp')
    if args.timeline and args.video is None:
        raise ValueError('--timeline requires --video')
    if args.timestamp is not None and args.video is None:
        raise ValueError('--timestamp requires --video')
    preview = None
    preview_timeline = None
    if args.timeline:
        from activity_clip_region_timeline import build_region_preview_timeline
        preview_timeline = build_region_preview_timeline(args.video, template)
    elif args.video is not None:
        from activity_clip_region_preview import build_region_preview
        preview = build_region_preview(args.video, template, timestamp=args.timestamp)
    html = render_clip_selection_editor(template, preview=preview, preview_timeline=preview_timeline)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(html)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
