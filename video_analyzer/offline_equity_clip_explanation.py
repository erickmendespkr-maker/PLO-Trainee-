"""Render a standalone, offline HTML explanation beside a previously audited clip.

Never presents OCR text as a verified hero action or equity as a decision grade.
The page loads no remote resources. The source report must match the clip hash.
Usage: python offline_equity_clip_explanation.py REPORT_JSON CLIP_MP4 NEW_HTML
"""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path

from offline_plo_equity_monte_carlo import read_json, require
from offline_reviewed_equity_clip_report import digest, safe_file


def render(report, clip_sha):
    require(type(report) is dict and report.get('schema_version') == 1 and
            report.get('analysis_status') == 'offline_conditional_manual_cards_equity_not_action_grade',
            'invalid conditional equity report')
    require(report.get('source_clip_sha256') == clip_sha,
            'report does not match clip')
    require(report.get('binding_replay_audit_rerun') is False and
            report.get('manual_cards_claimed_reviewed_not_independently_verified') is True and
            report.get('hero_actor_at_selected_action_verified') is False and
            report.get('selected_action_strategic_correctness_verified') is False and
            report.get('ocr_semantics_verified') is False and
            report.get('opponent_range_is_assumption') is True,
            'unsafe strategic or OCR verification claims')
    result = report.get('equity_result')
    require(type(result) is dict and
            result.get('analysis_status') == 'offline_manual_assumptions_monte_carlo_only' and
            result.get('strategic_correctness_verified') is False and
            result.get('ocr_semantics_verified') is False and
            result.get('player_identity_verified') is False,
            'invalid Monte Carlo analysis status')
    equity = result.get('equity')
    ci = result.get('equity_ci95_sampling_only')
    require(type(equity) in (float,int) and math.isfinite(equity) and
            type(ci) is list and len(ci) == 2 and
            all(type(x) in (int,float) and math.isfinite(x) for x in ci) and
            0 <= ci[0] <= equity <= ci[1] <= 1,
            'invalid equity confidence interval')
    iterations, seed = result.get('iterations'), result.get('seed')
    require(type(iterations) is int and 2 <= iterations <= 50000 and
            type(seed) is int and 0 <= seed < 2**32, 'invalid simulation parameters')
    require(report.get('variant') == result.get('variant') and
            result['variant'] in ('PLO5','PLO6'), 'variant mismatch')
    hand = report.get('hand_id')
    require(type(hand) is str and 1 <= len(hand) <= 64, 'invalid hand identifier')
    action = report.get('selected_action_ocr_text_not_graded')
    require(type(action) is str and 0 < len(action) <= 128, 'invalid action label')
    model = result.get('opponent_model_kind')
    require(model in ('uniform','weighted_combos'), 'invalid range model')
    ev = result.get('terminal_call_ev_model')
    if ev is None:
        ev_html = '<p><strong>EV:</strong> não calculado (pote e custo não informados).</p>'
    else:
        require(type(ev) is dict and ev.get('raise_ev') is None and
                type(ev.get('call_ev_incremental')) in (int,float) and
                math.isfinite(ev['call_ev_incremental']), 'invalid terminal EV')
        ev_html = (f'<p><strong>EV hipotético de call:</strong> '
                   f'{ev["call_ev_incremental"]:+.3f} fichas. '
                   'Modelo terminal heads-up, sem rake ou apostas futuras; '
                   'não avalia a ação observada.</p>')
    frame_count = report.get('card_frame_evidence_count', 0)
    frame_claimed = report.get('card_frame_evidence_claimed_not_independently_verified', False)
    require(type(frame_count) is int and 0 <= frame_count <= 11 and
            type(frame_claimed) is bool and (frame_count > 0) == frame_claimed,
            'invalid manual frame evidence metadata')
    frame_html = (f'<p><strong>Quadros anotados pelo revisor:</strong> {frame_count} cartas. '
                  'Os timestamps são declarações humanas, não verificação automática de cartas.</p>'
                  if frame_claimed else
                  '<p><strong>Quadros por carta:</strong> não informados nesta revisão.</p>')
    pct = lambda x: f'{100*x:.2f}%'
    # Static media basename: no user-controlled URL or JavaScript.
    return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PLO Trainee — análise condicional offline</title>
<style>body{{font:16px system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#172332;background:#fafbfc}}
main{{background:white;border:1px solid #dce2e8;border-radius:12px;padding:1.4rem}}
video{{width:100%;max-height:480px;background:#101820;border-radius:8px}}
strong{{font-weight:700}}.warning{{border-left:4px solid #d58b25;padding:0.7rem 1rem;background:#fff8eb}}
small{{color:#4c5b69}}h1{{font-size:1.6rem}}h2{{font-size:1.2rem}}</style></head>
<body><main><h1>Revisão offline — {escape(str(report['variant']))} / mão {escape(hand)}</h1>
<p class="warning"><strong>Não é avaliação da jogada.</strong> A ação OCR “{escape(action)}”
 não foi atribuída com segurança ao jogador. Cartas foram declaradas em revisão manual,
 sem verificação independente. Ranges são hipóteses; o IC cobre somente a amostragem.</p>
<video controls preload="metadata" src="clip.mp4" aria-label="Corte MP4 revisado"></video>
<h2>Equity condicional: {pct(equity)}</h2>
<p>Intervalo aproximado de 95% (somente Monte Carlo): {pct(ci[0])}–{pct(ci[1])}.</p>
<p>Variante: {escape(str(result['variant']))}. Range adversário: {escape(model)}.
 Simulações: {iterations:,}. Semente: {seed}.</p>
{ev_html}
{frame_html}
<p><strong>Limitações:</strong> sem confirmação independente de OCR, identidade do jogador,
 cartas digitadas, precisão do range ou qualidade estratégica da decisão.
 Não considera múltiplos adversários nem estratégia de apostas futuras.</p>
<small>SHA-256 do clipe: {clip_sha}. Página local, sem recursos externos.</small>
</main></body></html>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_json')
    parser.add_argument('clip_mp4')
    parser.add_argument('new_html')
    args = parser.parse_args(argv)
    report_path = safe_file(args.report_json, max_bytes=2_000_000)
    clip_path = safe_file(args.clip_mp4)
    out = Path(args.new_html)
    require(out.parent.is_dir() and not out.parent.is_symlink() and
            out.suffix == '.html' and not out.exists() and not out.is_symlink(),
            'HTML output must be new')
    require(out.parent.resolve() == clip_path.parent.resolve() and clip_path.name == 'clip.mp4',
            'HTML and clip.mp4 must be in the same directory')
    require(out.resolve() not in {report_path.resolve(), clip_path.resolve()},
            'cannot overwrite source evidence')
    report_hash, clip_hash = digest(report_path), digest(clip_path)
    html = render(read_json(report_path), clip_hash)
    require(report_hash == digest(report_path) and clip_hash == digest(clip_path),
            'source changed during rendering')
    with out.open('x', encoding='utf-8') as stream:
        stream.write(html)
    print(json.dumps({'html_created': str(out), 'clip_sha256': clip_hash}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
