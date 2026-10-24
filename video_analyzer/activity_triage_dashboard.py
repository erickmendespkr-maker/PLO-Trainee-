"""Generate a read-only, self-contained OFFLINE HTML dashboard for PLO review triage.

Consumes the output of activity_review_triage_math. This is a *review workload*
viewer, not a visual-evidence audit, decision adviser, EV ranker, or automatic
clip selector. Browser notes are exported separately and never authorize math.
No networking, video autoplay, remote assets, or access to the source MP4 files.
"""
import argparse
import base64
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re

from activity_hypothetical_math import digest
from activity_review_triage_math import FIELDS, STATUS

SHA = re.compile(r'[0-9a-f]{64}\Z')
FILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,180}\.mp4\Z')
CATEGORIES = {
    'needs_evidence': 'Faltam evidências',
    'human_attention_suggested': 'Revisão sugerida',
    'human_review_optional': 'Revisão opcional',
}

# Inline code is permitted by its EXACT SHA-256 CSP hash, not unsafe-inline.
SCRIPT = r'''"use strict";
const root = document.getElementById("decisions");
const tableFilter = document.getElementById("table-filter");
const categoryFilter = document.getElementById("category-filter");
const searchFilter = document.getElementById("search-filter");
const count = document.getElementById("visible-count");
const cards = Array.from(root.querySelectorAll("article[data-category]"));
function filter() {
  const query = searchFilter.value.toLocaleLowerCase("pt-BR").trim();
  let shown = 0;
  for (const card of cards) {
    const matches = (tableFilter.value === "all" || card.dataset.table === tableFilter.value)
      && (categoryFilter.value === "all" || card.dataset.category === categoryFilter.value)
      && (!query || card.dataset.search.includes(query));
    card.hidden = !matches;
    if (matches) shown += 1;
  }
  count.textContent = String(shown) + " de " + String(cards.length) + " decisões exibidas";
}
for (const input of [tableFilter, categoryFilter, searchFilter]) {
  input.addEventListener("input", filter);
}
filter();
document.getElementById("export-notes").addEventListener("click", () => {
  const entries = cards.map(card => ({
    table_id: Number(card.dataset.table),
    hand_id: card.dataset.hand,
    event_index: Number(card.dataset.event),
    review_workflow_checked: card.querySelector("input[type=checkbox]").checked,
    reviewer_notes_unverified: card.querySelector("textarea").value.slice(0, 1000),
    visual_evidence_verified: false,
    strategic_error_established: false,
    ev_ranking_authorized: false,
    clip_selection_authorized: false
  }));
  const output = {
    schema_version: 1,
    analysis_status: "local_notes_not_evidence_or_math_authorization",
    source_triage_sha256: document.body.dataset.triageSha,
    recording_sha256: document.body.dataset.recordingSha,
    visual_evidence_verified: false,
    ready_for_equity_or_ev: false,
    strategic_error_established: false,
    entries
  };
  const blob = new Blob([JSON.stringify(output, null, 2) + "\n"], {type:"application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "plo_review_notes_" + output.source_triage_sha256.slice(0, 12) + ".json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});'''

CSS = '''body{font:16px system-ui,sans-serif;max-width:1100px;margin:1.5rem auto;padding:0 1rem;background:#f8f8f5;color:#20242a}
h1{margin-bottom:.3rem}p{line-height:1.5}.warning{background:#fff0cd;border-left:5px solid #ad6d00;padding:1rem}
.filters{display:flex;gap:.8rem;flex-wrap:wrap;margin:1.2rem 0;align-items:end}
label{display:flex;flex-direction:column;gap:.3rem}input,select,textarea,button{font:inherit;padding:.4rem}
article{background:white;border:1px solid #cbd0d4;border-radius:8px;margin:1rem 0;padding:1rem;overflow-wrap:anywhere}
article[data-category=needs_evidence]{border-left:6px solid #b94c20}
article[data-category=human_attention_suggested]{border-left:6px solid #306b96}
article[data-category=human_review_optional]{border-left:6px solid #768576}
.meta{color:#39495a;font-size:.94rem}.notes{margin-top:1rem}.notes textarea{width:min(100%,800px);min-height:4rem;box-sizing:border-box}
.notes label{margin-top:.6rem}.notes .checkbox{flex-direction:row;align-items:center}
code{overflow-wrap:anywhere}article[hidden]{display:none}button{cursor:pointer}
@media print{.filters,.notes,button{display:none}body{background:white}article{break-inside:avoid}}'''


def _sha(value, name):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError('Invalid ' + name)


def _number(value, name, *, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError('Invalid ' + name)
    return float(value)


def validate_triage(triage, *, expected_sha256=None):
    """Reject contradictory or unsafe reports before rendering a local HTML file.

    This is a *schema/integrity* check, not authentication of the source video.
    For source hash/MP4/replayed Monte Carlo validation use the upstream triage
    builder and its original source inputs, not this dashboard.
    """
    if not isinstance(triage, dict) or triage.get('schema_version') != 1:
        raise ValueError('Expected triage schema 1')
    if triage.get('analysis_status') != STATUS:
        raise ValueError('Expected unverified review triage')
    for flag in ('auto_clip_selection_authorized', 'authorized_for_ev_based_ranking',
                 'strategic_error_established'):
        if triage.get(flag) is not False:
            raise ValueError('Unsafe authorization flag: ' + flag)
    if triage.get('sort_order') != 'timestamp_only_not_mathematical_rank':
        raise ValueError('Expected chronological, non-EV order')
    if triage.get('attention_threshold_call_to_pot') != .25:
        raise ValueError('Unexpected heuristic threshold')
    for name in ('recording_sha256', 'source_explanations_sha256',
                 'source_clip_manifest_sha256'):
        _sha(triage.get(name), name)
    rows = triage.get('candidates')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Invalid candidate list')
    source_sha = digest(triage)
    if expected_sha256 is not None:
        _sha(expected_sha256, 'expected SHA-256')
        if expected_sha256 != source_sha:
            raise ValueError('Triage SHA-256 mismatch')
    seen = set()
    previous = None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid candidate')
        table, hand, event = row.get('table_id'), row.get('hand_id'), row.get('event_index')
        if (type(table) is not int or not 1 <= table <= 4 or not isinstance(hand, str)
                or not hand or len(hand) > 200 or type(event) is not int or event < 0):
            raise ValueError('Invalid decision identity')
        key = (table, hand, event)
        if key in seen:
            raise ValueError('Duplicate decision identity')
        seen.add(key)
        timestamp = _number(row.get('decision_timestamp'), 'timestamp')
        chronological = (timestamp, table, hand, event)
        if previous is not None and chronological < previous:
            raise ValueError('Triage candidates are not chronological')
        previous = chronological
        filename = row.get('filename')
        if (not isinstance(filename, str) or not FILE.fullmatch(filename)
                or '..' in filename or any(ord(c) < 32 for c in filename)):
            raise ValueError('Unsafe MP4 filename')
        _sha(row.get('original_mp4_sha256'), 'MP4 SHA-256')
        category = row.get('review_category')
        if category not in CATEGORIES:
            raise ValueError('Unknown review category')
        reason = row.get('reason')
        if not isinstance(reason, str) or not reason or len(reason) > 500:
            raise ValueError('Invalid reason')
        missing = row.get('missing_fields')
        if (not isinstance(missing, list) or any(not isinstance(field, str) for field in missing)
                or len(set(missing)) != len(missing)
                or any(field not in FIELDS for field in missing)):
            raise ValueError('Invalid missing fields')
        if bool(missing) != (category == 'needs_evidence'):
            raise ValueError('Missing evidence/category contradiction')
        ratio = row.get('call_to_pot_ratio')
        if ratio is not None:
            ratio = _number(ratio, 'call/pot ratio')
            if missing or (category == 'human_attention_suggested') != (ratio >= .25):
                raise ValueError('Contradictory call/pot heuristic')
        elif category == 'human_attention_suggested':
            raise ValueError('Attention requires an observed call/pot ratio')
        if type(row.get('has_conditional_what_if')) is not bool:
            raise ValueError('Invalid what-if marker')
        ci = row.get('sampling_ci95_if_available')
        if ci is not None:
            if (not row['has_conditional_what_if'] or not isinstance(ci, list)
                    or len(ci) != 2):
                raise ValueError('Invalid sampling interval')
            lo = _number(ci[0], 'CI lower')
            hi = _number(ci[1], 'CI upper')
            if not 0 <= lo <= hi <= 1:
                raise ValueError('Invalid sampling bounds')
        elif row['has_conditional_what_if']:
            raise ValueError('Missing sampling interval for hypothetical calculation')
        if (row.get('visual_evidence_confidence') != 'unverified'
                or row.get('range_confidence') != 'unverified_user_hypothesis'):
            raise ValueError('Unverified confidence required')
        for flag in ('strategic_error_established', 'auto_clip_selection_authorized',
                     'ev_ranking_authorized'):
            if row.get(flag) is not False:
                raise ValueError('Unsafe candidate authorization')
    return source_sha


def build_triage_dashboard(triage, *, expected_sha256=None):
    """Return safe self-contained HTML and source SHA; no external resources."""
    source_sha = validate_triage(triage, expected_sha256=expected_sha256)
    cards = []
    for row in triage['candidates']:
        table, hand, event = row['table_id'], row['hand_id'], row['event_index']
        category = row['review_category']
        missing = ', '.join(row['missing_fields']) or 'nenhum informado'
        ratio = row['call_to_pot_ratio']
        ratio_text = f'{100 * ratio:.1f}%' if ratio is not None else 'não calculado'
        ci = row['sampling_ci95_if_available']
        ci_text = (f'{100 * ci[0]:.1f}%–{100 * ci[1]:.1f}% (amostragem apenas)'
                   if ci is not None else 'não disponível')
        attrs = (' data-category="' + escape(category, quote=True) + '"'
                 ' data-table="' + str(table) + '"'
                 ' data-hand="' + escape(hand, quote=True) + '"'
                 ' data-event="' + str(event) + '"'
                 ' data-search="' + escape((hand + ' ' + row['filename'] + ' ' +
                                           row['reason']).lower(), quote=True) + '"')
        cards.append(
            '<article' + attrs + '><h2>Mesa ' + str(table) + ' · Mão ' + escape(hand) +
            ' · Evento ' + str(event) + '</h2><p><strong>' + escape(CATEGORIES[category]) +
            '</strong> · PTS ' + f'{row["decision_timestamp"]:.3f}' + 's</p>' +
            '<p>' + escape(row['reason']) + '</p>' +
            '<p>Campos pendentes: <strong>' + escape(missing) + '</strong></p>' +
            '<p>Exposição call/pote: ' + escape(ratio_text) +
            ' (heurística de atenção, não EV).</p>' +
            '<p>IC 95% da equity hipotética: ' + escape(ci_text) +
            '. Não cobre incerteza de range ou OCR.</p>' +
            '<p class="meta">Arquivo MP4 local (apenas referência textual): <code>' +
            escape(row['filename']) + '</code><br>SHA-256: <code>' +
            row['original_mp4_sha256'] + '</code></p>' +
            '<div class="notes"><label class="checkbox"><input type="checkbox">'
            'Marcar como examinado na fila (NÃO confirma cartas, ação ou EV)</label>' +
            '<label>Observações pessoais, sem efeito nos cálculos<textarea maxlength="1000" '
            'placeholder="Anote o que ainda precisa conferir"></textarea></label></div></article>')
    counts = {name: sum(c['review_category'] == name for c in triage['candidates'])
              for name in CATEGORIES}
    csp_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode('utf-8')).digest()).decode('ascii')
    csp = ("default-src 'none'; script-src 'sha256-" + csp_hash +
           "'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; "
           "media-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; "
           "base-uri 'none'")
    html = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">'
            '<title>PLO Trainee — triagem offline</title><style>' + CSS + '</style></head>'
            '<body data-triage-sha="' + source_sha + '" data-recording-sha="' +
            triage['recording_sha256'] + '"><h1>PLO Trainee · triagem offline</h1>'
            '<p class="warning"><strong>Sem diagnóstico de erro.</strong> Esta lista organiza '
            'revisões humanas de gravações; não valida OCR, ranges ou EV real. '
            'Nenhum corte é selecionado automaticamente. Notas exportadas não '
            'autorizam cálculos nem decisões de jogo.</p>'
            '<p>Decisões: ' + str(len(triage['candidates'])) +
            ' · Precisam de evidências: ' + str(counts['needs_evidence']) +
            ' · Revisão sugerida: ' + str(counts['human_attention_suggested']) +
            ' · Revisão opcional: ' + str(counts['human_review_optional']) + '</p>'
            '<p class="meta">SHA-256 do relatório de triagem: <code>' + source_sha + '</code></p>'
            '<div class="filters"><label>Mesa<select id="table-filter">'
            '<option value="all">Todas</option>' + ''.join(
                '<option value="' + str(i) + '">Mesa ' + str(i) + '</option>'
                for i in range(1, 5)) + '</select></label>'
            '<label>Categoria<select id="category-filter"><option value="all">Todas</option>' +
            ''.join('<option value="' + name + '">' + escape(label) + '</option>'
                    for name, label in CATEGORIES.items()) + '</select></label>'
            '<label>Buscar mão, arquivo ou motivo<input id="search-filter" type="search"></label>'
            '<button id="export-notes" type="button">Exportar notas locais (JSON)</button>'
            '<span id="visible-count" aria-live="polite"></span></div>'
            '<main id="decisions">' + ''.join(cards) + '</main>'
            '<p>As notas são exportadas pelo navegador, não enviadas pela internet. '
            'Não há links automáticos para vídeos nem execução de pôquer ao vivo.</p>'
            '<script>' + SCRIPT + '</script></body></html>')
    return {'html': html, 'source_triage_sha256': source_sha,
            'counts': counts, 'total': len(triage['candidates'])}


def write_triage_dashboard(triage_json, output_html, *, expected_sha256=None):
    source, output = Path(triage_json), Path(output_html)
    if (not source.is_file() or source.is_symlink() or output.exists() or output.is_symlink()
            or source.resolve() == output.resolve()):
        raise ValueError('Require regular source and new distinct HTML output')
    packet = build_triage_dashboard(json.loads(source.read_text(encoding='utf-8')),
                                    expected_sha256=expected_sha256)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as fp:
        fp.write(packet['html'])
    return {key: packet[key] for key in ('source_triage_sha256', 'counts', 'total')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('triage_json')
    parser.add_argument('output_html')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args(argv)
    print(json.dumps(write_triage_dashboard(args.triage_json, args.output_html,
                                            expected_sha256=args.expected_sha256),
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
