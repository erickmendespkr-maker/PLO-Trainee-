"""Generate an offline browser form for human OCR evidence annotations.

The HTML never submits data over the network. Its downloaded JSON must pass
offline_job_review_decisions.review_job() before it can be persisted.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import re

from offline_job_review_decisions import handoff_sha256
from offline_job_review_handoff import build_handoff
from offline_jobs import OfflineJobStore

IMAGE_PATH = re.compile(r"^table_0[1-4]/frame_[0-9]{5}\.png$")
MAX_BROWSER_HINTS = 3000


def render_editor(handoff):
    if handoff.get("analysis_status") != "unapproved_offline_review_handoff":
        raise ValueError("Expected unapproved handoff")
    rows = []
    for frame in handoff["frames"]:
        image = frame.get("image", "")
        if type(image) is not str or not IMAGE_PATH.fullmatch(image):
            raise ValueError("Unsafe frame path")
        for hint in frame["ocr_hints_unverified"]:
            rows.append({"table_id": frame["table_id"],
                         "nominal_timestamp_seconds": frame["nominal_timestamp_seconds"],
                         "field": hint["field"],
                         "candidate_index": hint["candidate_index"],
                         "ocr_text": hint["unverified_text"],
                         "image": "../" + image})
            if len(rows) > MAX_BROWSER_HINTS:
                raise ValueError("Too many hints for browser editor; use JSON import")
    payload = {"job_id": handoff["job_id"], "handoff_sha256": handoff_sha256(handoff),
               "rows": rows}
    # Keep untrusted OCR strings out of executable HTML/script syntax.
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace(
        "<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace(
        "\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return ("""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PLO Trainee — revisão humana de OCR</title>
<style>
body{font:15px system-ui;background:#111b26;color:#eef3f9;margin:0}
main{max-width:1100px;margin:auto;padding:20px}
.card{border:1px solid #415568;border-radius:9px;padding:14px;margin:12px 0;background:#1d2b38}
img{max-width:100%;height:auto;max-height:230px;object-fit:contain}
label{display:block;margin:7px 0}input,select,button{font:inherit;padding:7px}
input,select{background:#fff;color:#15202b}input[type=text]{width:min(95%,680px)}
button{cursor:pointer}small{color:#bfd1e2}a{color:#b9e1ff}
.notice{background:#4d3424;padding:12px}strong{color:#ffdd9c}
</style></head><body><main>
<h1>Revisão humana — OCR não verificado</h1>
<p class="notice">Apenas gravações offline. Esta página NÃO confirma mãos completas,
NÃO calcula equity/EV e NÃO autoriza cortes automáticos. Timestamps nominais.</p>
<label>Identificação do revisor <input id="reviewer" type="text" maxlength="80"
placeholder="Nome ou pseudônimo"></label>
<p id="summary"></p><div id="items"></div>
<button id="prev" type="button">Anterior</button>
<button id="next" type="button">Próxima</button>
<button id="export" type="button">Exportar JSON para validação Python</button>
<p><small>Selecione uma decisão explícita. Campos pendentes não são exportados.
O arquivo gerado só é aceito após reauditoria da gravação e das evidências.</small></p>
</main><script>
"use strict";
const DATA = """ + serialized + """;
const PAGE_SIZE = 30;
let page = 0;
const edits = new Map();
const items = document.getElementById("items");
const summary = document.getElementById("summary");
function node(tag, text, parent) {
  const el = document.createElement(tag);
  if (text !== null) el.textContent = text;
  if (parent) parent.appendChild(el);
  return el;
}
function labeled(parent, caption, child) {
  const label = node("label", caption + " ", parent);
  label.appendChild(child);
  return child;
}
function render() {
  items.replaceChildren();
  const start = page * PAGE_SIZE;
  const end = Math.min(DATA.rows.length, start + PAGE_SIZE);
  summary.textContent = DATA.rows.length + " candidatos OCR · página " +
    (page + 1) + " · " + edits.size + " decisões preenchidas";
  for (let i = start; i < end; i++) {
    const row = DATA.rows[i];
    const edit = edits.get(i) || {status:"pending",value:"",confidence:"",reason:""};
    const card = node("section", null, items); card.className = "card";
    node("h3", "Mesa " + row.table_id + " · " + row.nominal_timestamp_seconds +
        "s · " + row.field, card);
    const img = node("img", null, card); img.src = row.image; img.loading = "lazy";
    img.alt = "Quadro da mesa " + row.table_id;
    node("p", "OCR não verificado: " + row.ocr_text, card);
    const status = node("select", null, null);
    for (const [value, label] of [
      ["pending","Pendente"],["confirmed","Confirmar OCR"],["corrected","Corrigir OCR"],
      ["rejected","Rejeitar"],["uncertain","Incerto"]]) {
      const opt = node("option", label, status); opt.value = value;
    }
    status.value = edit.status; labeled(card, "Decisão", status);
    const value = node("input", null, null); value.type="text"; value.maxLength=160;
    value.value=edit.value; labeled(card, "Valor confirmado/corrigido", value);
    const confidence = node("input", null, null);
    confidence.type="number"; confidence.min="0"; confidence.max="1";
    confidence.step="0.01"; confidence.value=edit.confidence;
    labeled(card, "Confiança subjetiva (0 a 1)", confidence);
    const reason = node("input", null, null); reason.type="text";
    reason.maxLength=300; reason.value=edit.reason;
    labeled(card, "Justificativa", reason);
    function sync() {
      if (status.value === "pending") edits.delete(i);
      else edits.set(i, {status:status.value, value:value.value,
                         confidence:confidence.value, reason:reason.value});
      summary.textContent = DATA.rows.length + " candidatos OCR · página " +
        (page + 1) + " · " + edits.size + " decisões preenchidas";
    }
    status.addEventListener("change", () => {
      if (status.value === "confirmed") value.value = row.ocr_text;
      if (status.value === "rejected" || status.value === "uncertain") {
        value.value=""; confidence.value="";
      }
      sync();
    });
    for (const el of [value, confidence, reason]) el.addEventListener("input", sync);
  }
  document.getElementById("prev").disabled = page === 0;
  document.getElementById("next").disabled = end >= DATA.rows.length;
}
document.getElementById("prev").addEventListener("click", () => {page--;render();});
document.getElementById("next").addEventListener("click", () => {page++;render();});
document.getElementById("export").addEventListener("click", () => {
  const reviewer = document.getElementById("reviewer").value.trim();
  if (reviewer.length < 2 || reviewer.length > 80) {
    alert("Informe identificação do revisor (2 a 80 caracteres)."); return;
  }
  const decisions = [];
  for (const [index, edit] of edits) {
    const row = DATA.rows[index];
    if (!edit.reason.trim() || edit.reason.trim().length < 3) {
      alert("Cada decisão precisa de justificativa com pelo menos 3 caracteres."); return;
    }
    const accepted = edit.status === "confirmed" || edit.status === "corrected";
    if (accepted && (!edit.value.trim() || edit.confidence.trim() === "" ||
        !Number.isFinite(Number(edit.confidence)) || Number(edit.confidence) < 0 ||
        Number(edit.confidence) > 1)) {
      alert("Confirmações e correções exigem valor e confiança de 0 a 1."); return;
    }
    if (edit.status === "confirmed" && edit.value !== row.ocr_text) {
      alert("Valor diferente do OCR exige o estado Corrigir OCR."); return;
    }
    if (edit.status === "corrected" && edit.value === row.ocr_text) {
      alert("Correção precisa ser diferente do OCR."); return;
    }
    decisions.push({table_id:row.table_id,
      nominal_timestamp_seconds:row.nominal_timestamp_seconds,
      field:row.field,candidate_index:row.candidate_index,
      status:edit.status,value:accepted?edit.value:null,
      confidence:accepted?Number(edit.confidence):null,reason:edit.reason.trim()});
  }
  const payload={schema_version:1,job_id:DATA.job_id,
    handoff_sha256:DATA.handoff_sha256,reviewer,decisions};
  const blob = new Blob([JSON.stringify(payload,null,2)], {type:"application/json"});
  const link=document.createElement("a");
  link.href=URL.createObjectURL(blob);link.download="ocr_review_submission.json";
  link.click();setTimeout(()=>URL.revokeObjectURL(link.href),5000);
});
render();
</script></body></html>""")


def export_editor(store, job_id, results_root):
    handoff = build_handoff(store, job_id, results_root)
    html = render_editor(handoff)
    folder = Path(results_root) / job_id / "review_handoff"
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("Generate review_handoff before creating editor")
    path = folder / "ocr_review_editor.html"
    with path.open("x", encoding="utf-8") as output:
        output.write(html)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("job_id")
    parser.add_argument("results_root")
    args = parser.parse_args(argv)
    store = OfflineJobStore(args.database)
    print(export_editor(store, args.job_id, args.results_root))


if __name__ == "__main__":
    main()
