"""Generate a read-only, local HTML review page for one manually linked PLO clip.

Inputs are an existing Cycle 111 provenance manifest and its MP4, plus an
optional Cycle 112 visual similarity report. This is a *presentation* layer:
no OCR, hand reconstruction, Monte Carlo recomputation, strategic verdict,
network access, JavaScript, automatic selection or source-video modification.
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
import stat
from urllib.parse import quote

MAX_LINK = 128 * 1024
MAX_VISUAL = 32 * 1024
MAX_HTML = 128 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
LINK_STATUS = "manual_clip_linked_to_hypothetical_math_not_video_verified"
VISUAL_STATUS = "sampled_visual_similarity_only_not_pts_or_hand_verified"
LINK_FALSE_FLAGS = (
    "math_result_independently_recomputed",
    "hand_start_or_end_pts_verified",
    "hand_reconstruction_verified",
    "strategic_error_established",
    "automatic_clip_selection_authorized",
)
VISUAL_FALSE_FLAGS = (
    "actual_decoded_frame_pts_measured",
    "frame_exact_export_verified",
    "hand_start_or_end_pts_verified",
    "hand_reconstruction_verified",
    "strategic_error_established",
    "automatic_clip_selection_authorized",
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def sha(value):
    return type(value) is str and HEX64.fullmatch(value) is not None


def pairs_unique(items):
    obj = {}
    for key, value in items:
        require(key not in obj, "Duplicate JSON key")
        obj[key] = value
    return obj


def read_json(path, maximum):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= maximum,
            "Unsafe, empty or oversized JSON input")
    raw = p.read_bytes()
    require(0 < len(raw) <= maximum, "JSON input size changed")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs_unique,
                          parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid UTF-8 JSON") from exc
    require(type(data) is dict, "Expected JSON object")
    return data, raw


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bounded_text(value, name, *, limit=2000, allow_empty=False):
    require(type(value) is str and len(value) <= limit and
            (allow_empty or len(value) > 0), f"Invalid {name}")
    return value


def check_interval(value, name, *, lower=None, upper=None):
    require(type(value) is list and len(value) == 2 and
            all(number(x) for x in value) and value[0] <= value[1],
            f"Invalid {name}")
    if lower is not None:
        require(value[0] >= lower, f"Invalid {name} lower bound")
    if upper is not None:
        require(value[1] <= upper, f"Invalid {name} upper bound")
    return value


def validate_link(link, clip_digest):
    require(link.get("schema_version") == 1 and link.get("status") == LINK_STATUS,
            "Expected manual, unverified provenance manifest")
    require(all(link.get(k) is False for k in LINK_FALSE_FLAGS),
            "Provenance cannot claim verification or automatic selection")
    require(link.get("clip_and_math_linked_by_manual_identifiers") is True,
            "Missing manual identity association")
    require(sha(link.get("clip_mp4_sha256")) and
            link["clip_mp4_sha256"] == clip_digest and
            sha(link.get("source_recording_sha256")), "Clip/source digest mismatch")
    require(type(link.get("table_id")) is int and 1 <= link["table_id"] <= 4,
            "Invalid table ID")
    bounded_text(link.get("hand_label_human_assigned"), "hand label", limit=64)
    require(type(link.get("job_id")) is str and
            re.fullmatch(r"[0-9a-f]{32}", link["job_id"]), "Invalid job ID")
    shas = link.get("input_json_sha256")
    require(type(shas) is dict and set(shas) ==
            {"sidecar", "audit", "draft", "worksheet", "filled", "math"} and
            all(sha(x) for x in shas.values()), "Invalid input digest manifest")
    clip_window = check_interval(link.get("clip_selection_seconds_human"), "clip window", lower=0)
    require(clip_window[1] > clip_window[0] and clip_window[1] <= 86400,
            "Invalid clip window duration")
    hand_window = check_interval(link.get("hand_interval_seconds_human_claimed"), "hand window", lower=0)
    require(hand_window[1] > hand_window[0] and hand_window[1] <= 86400,
            "Invalid hand window duration")
    decision = link.get("decision_timestamp_seconds_human")
    require(number(decision) and clip_window[0] <= decision <= clip_window[1] and
            hand_window[0] <= decision <= hand_window[1], "Decision outside claimed windows")
    require(type(link.get("frame_pts_audit_within_tolerance_observed")) is bool,
            "Missing bounded PTS observation flag")
    math_data = link.get("hypothetical_math")
    require(type(math_data) is dict and math_data.get("variant") in ("PLO5", "PLO6") and
            math_data.get("action_assumed") in ("call", "raise"), "Invalid hypothetical math")
    require(number(math_data.get("equity")) and 0 <= math_data["equity"] <= 1,
            "Invalid equity")
    check_interval(math_data.get("equity_sampling_ci95"), "equity CI", lower=0, upper=1)
    check_interval(math_data.get("ev_sampling_ci95"), "EV CI")
    require(number(math_data.get("ev_vs_fold_zero")), "Invalid EV")
    require(type(math_data.get("monte_carlo_trials")) is int and
            1 <= math_data["monte_carlo_trials"] <= 10_000_000 and
            type(math_data.get("monte_carlo_seed")) is int and
            0 <= math_data["monte_carlo_seed"] <= 2**63 - 1, "Invalid Monte Carlo settings")
    require(number(math_data.get("human_confidence_subjective")) and
            0 <= math_data["human_confidence_subjective"] <= 1,
            "Invalid subjective confidence")
    combinations = math_data.get("opponent_range_combinations")
    require(combinations is None or (type(combinations) is int and
                                     0 <= combinations <= 10_000_000), "Invalid range size")
    bounded_text(math_data.get("model_notes"), "model notes", allow_empty=True)
    bounded_text(math_data.get("model_limitations"), "model limitations")
    bounded_text(link.get("warning"), "provenance warning", limit=4000)
    return link


def validate_visual(visual, link):
    require(visual.get("schema_version") == 1 and visual.get("status") == VISUAL_STATUS,
            "Expected sampled-only visual report")
    require(all(visual.get(k) is False for k in VISUAL_FALSE_FLAGS),
            "Visual report cannot claim frame/hand verification")
    require(visual.get("source_sha256") == link["source_recording_sha256"] and
            visual.get("clip_sha256") == link["clip_mp4_sha256"] and
            visual.get("table_id_human_selected") == link["table_id"] and
            sha(visual.get("selection_sha256")), "Visual report media/table mismatch")
    samples = visual.get("samples")
    require(type(samples) is list and len(samples) == 3, "Expected three visual samples")
    means = []
    duration = link["clip_selection_seconds_human"][1] - link["clip_selection_seconds_human"][0]
    for sample in samples:
        require(type(sample) is dict and number(sample.get("requested_clip_second")) and
                0 <= sample["requested_clip_second"] <= duration and
                sha(sample.get("clip_decoded_gray_sha256")), "Invalid sample")
        best = sample.get("best_candidate")
        require(type(best) is dict and number(best.get("normalized_gray_mae")) and
                0 <= best["normalized_gray_mae"] <= 1, "Invalid sampled image difference")
        means.append(best["normalized_gray_mae"])
    reported = visual.get("mean_best_normalized_gray_mae")
    require(number(reported) and 0 <= reported <= 1 and
            abs(reported - sum(means) / len(means)) <= .000002,
            "Visual similarity mean inconsistent with samples")
    return visual


def esc(value):
    return html.escape(str(value), quote=True)


def fmt(value, places=2):
    return f"{value:.{places}f}"


def render(link, clip_filename, visual=None, *, link_sha, visual_sha=None):
    """Render an inert HTML document; never interpolate raw user text into markup."""
    math_data = link["hypothetical_math"]
    window = link["clip_selection_seconds_human"]
    relative = link["decision_timestamp_seconds_human"] - window[0]
    filename_url = quote(clip_filename, safe="")
    # HTML-escape even percent-encoded path to protect attribute syntax.
    video_src = esc("./" + filename_url)
    v_status = (f"Amostragem visual: MAE médio {fmt(visual['mean_best_normalized_gray_mae'], 6)} "
                "(sem prova de PTS exato)." if visual is not None else
                "Comparação visual: não fornecida.")
    v_hash = f"<p>SHA-256 relatório visual: <code>{esc(visual_sha)}</code></p>" if visual_sha else ""
    ci = math_data["equity_sampling_ci95"]
    ev_ci = math_data["ev_sampling_ci95"]
    range_count = math_data["opponent_range_combinations"]
    return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee · Revisão offline · {esc(link['hand_label_human_assigned'])}</title>
<style>
:root{{color-scheme:dark}}body{{font:16px/1.55 system-ui,sans-serif;max-width:1080px;margin:0 auto;padding:2rem;background:#101827;color:#e7eef8}}
header,section{{background:#192539;border:1px solid #354760;border-radius:14px;padding:1.2rem;margin:1rem 0}}
h1{{margin:0 0 .4rem}}h2{{font-size:1.18rem}}.warn{{background:#402d1b;border-color:#bc8246;color:#ffe5bf}}
video{{display:block;width:100%;max-height:560px;background:black;border-radius:10px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem}}
.metric{{padding:.7rem;border:1px solid #354760;border-radius:10px}}.metric strong{{display:block;font-size:1.3rem}}code{{overflow-wrap:anywhere;font-size:.83rem}}
small{{color:#c0d1e8}}p{{overflow-wrap:anywhere}}@media print{{video{{display:none}}body{{background:white;color:black}}section,header{{background:white;color:black}}}}
</style></head><body>
<header><h1>PLO Trainee · Revisão offline</h1><p>Vídeo gravado · {esc(math_data['variant'])} · Mesa {link['table_id']} · Mão {esc(link['hand_label_human_assigned'])}</p>
<p><strong>Somente leitura.</strong> Nenhuma integração ao vivo, aposta, análise automática de vídeo ou requisição à internet.</p></header>
<section class="warn" role="note"><h2>⚠️ Análise hipotética — não verificada no vídeo</h2>
<p>Cartas, limites da mão, timestamp da decisão e ranges não foram confirmados independentemente. O EV depende do modelo; o intervalo de 95% cobre apenas a amostragem Monte Carlo, não erros de OCR, range ou modelo. Não há erro estratégico comprovado.</p></section>
<section><h2>Corte MP4 selecionado manualmente</h2><video controls preload="metadata" playsinline>
<source src="{video_src}" type="video/mp4">Seu navegador não suporta reprodução MP4 local.</video>
<p>Seleção humana: {fmt(window[0],3)}–{fmt(window[1],3)} s · Decisão alegada: {fmt(link['decision_timestamp_seconds_human'],3)} s na origem, ~{fmt(relative,3)} s dentro do corte.</p>
<p>PTS próximo às bordas observado na auditoria: {'sim' if link['frame_pts_audit_within_tolerance_observed'] else 'não'} — isso não confirma início/fim da mão.</p></section>
<section><h2>Equity e EV sob hipóteses</h2><div class="grid">
<div class="metric">Equity estimada<strong>{fmt(100*math_data['equity'])}%</strong><small>IC 95% amostral: {fmt(100*ci[0])}%–{fmt(100*ci[1])}%</small></div>
<div class="metric">EV vs. fold = 0<strong>{fmt(math_data['ev_vs_fold_zero'])} fichas</strong><small>IC 95% amostral: {fmt(ev_ci[0])} a {fmt(ev_ci[1])} fichas</small></div>
<div class="metric">Ação assumida<strong>{esc(math_data['action_assumed'])}</strong><small>Não é uma recomendação de jogo</small></div>
<div class="metric">Confiança humana subjetiva<strong>{fmt(100*math_data['human_confidence_subjective'])}%</strong><small>Não é a confiança estatística do modelo</small></div></div>
<p>Monte Carlo: {math_data['monte_carlo_trials']} simulações; semente {math_data['monte_carlo_seed']}; combinações de range: {esc(range_count if range_count is not None else 'não informado')}.</p>
<p><strong>Hipóteses:</strong> {esc(math_data['model_notes'])}</p><p><strong>Limitações:</strong> {esc(math_data['model_limitations'])}</p></section>
<section><h2>Auditoria visual e proveniência</h2><p>{esc(v_status)}</p>
<p>SHA-256 MP4: <code>{esc(link['clip_mp4_sha256'])}</code></p>
<p>SHA-256 gravação de origem (declarado no manifesto): <code>{esc(link['source_recording_sha256'])}</code></p>
<p>SHA-256 manifesto de associação: <code>{esc(link_sha)}</code></p>{v_hash}
<p>Job: <code>{esc(link['job_id'])}</code> · Os identificadores e resultados foram associados manualmente, não recalculados neste relatório.</p>
<p><strong>Aviso do manifesto:</strong> {esc(link['warning'])}</p></section>
<footer><small>Documento HTML estático gerado localmente. Não altera o MP4 ou os relatórios de origem.</small></footer></body></html>
'''


def export_page(clip_path, link_path, output_path, visual_path=None):
    clip, link_file, target = map(Path, (clip_path, link_path, output_path))
    visual_file = Path(visual_path) if visual_path is not None else None
    paths = [clip, link_file, target] + ([visual_file] if visual_file else [])
    require(len({p.resolve() for p in paths}) == len(paths), "Input/output paths overlap")
    require(clip.is_file() and not clip.is_symlink() and clip.suffix.lower() == '.mp4',
            "Expected a regular local MP4")
    require(target.suffix.lower() == '.html' and target.parent.is_dir() and
            not target.parent.is_symlink() and target.parent.resolve() == clip.parent.resolve() and
            not target.exists(), "HTML output must be new and beside the MP4")
    require(not clip.parent.is_symlink() and clip.stat().st_size > 0,
            "Unsafe MP4 directory or empty file")
    clip_digest = file_sha(clip)
    link, link_raw = read_json(link_file, MAX_LINK)
    validate_link(link, clip_digest)
    visual, visual_raw = (read_json(visual_file, MAX_VISUAL) if visual_file else (None, None))
    if visual is not None:
        validate_visual(visual, link)
    markup = render(link, clip.name, visual,
                    link_sha=hashlib.sha256(link_raw).hexdigest(),
                    visual_sha=hashlib.sha256(visual_raw).hexdigest() if visual_raw else None)
    payload = markup.encode('utf-8')
    require(len(payload) <= MAX_HTML, "HTML output too large")
    require(link_file.read_bytes() == link_raw and
            (visual_file is None or visual_file.read_bytes() == visual_raw) and
            file_sha(clip) == clip_digest, "Input changed during page generation")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output file")
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {'status': 'offline_read_only_review_not_video_verified',
            'output': str(target), 'clip_sha256': clip_digest,
            'visual_spot_check_included': visual is not None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exported_clip_mp4')
    parser.add_argument('manual_clip_math_link_json')
    parser.add_argument('new_review_html')
    parser.add_argument('--visual-report', default=None,
                        help='Optional Cycle 112 sampled visual comparison JSON')
    args = parser.parse_args(argv)
    print(json.dumps(export_page(args.exported_clip_mp4, args.manual_clip_math_link_json,
                                 args.new_review_html, args.visual_report)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
