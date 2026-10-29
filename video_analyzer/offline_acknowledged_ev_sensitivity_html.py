"""Offline HTML: audited human-card equity plus *hypothetical* EV sensitivity.

CLI: python offline_acknowledged_ev_sensitivity_html.py ACK_REPORT.json \
    SENSITIVITY.json clip.mp4 NEW_HTML

The acknowledged report and sensitivity result must describe identical *declared*
hero/board cards. No action, OCR, range, or fold frequency is inferred from video.
The prior frame/clip audits are not rerun; hashes only bind the supplied clip.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path

from offline_equity_clip_explanation import render as render_equity
from offline_plo_equity_monte_carlo import read_json, require
from offline_reviewed_equity_clip_report import digest, safe_file


def _number(value, name, minimum=None, maximum=None):
    require(type(value) in (int, float) and math.isfinite(value), f'invalid {name}')
    x = float(value)
    require((minimum is None or x >= minimum) and
            (maximum is None or x <= maximum), f'invalid {name}')
    return x


def _close(a, b):
    return math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-7)


def validate(report, sensitivity):
    """Validate claims and internal arithmetic; not provenance of model inputs."""
    require(report.get('analysis_status') ==
            'offline_conditional_equity_after_human_frame_acknowledgement',
            'human frame acknowledgement required')
    require(type(sensitivity) is dict and sensitivity.get('schema_version') == 1 and
            sensitivity.get('analysis_status') ==
            'offline_hypothetical_ev_sensitivity_not_an_action_grade',
            'invalid EV sensitivity status')
    for key, expected in (
        ('range_models_are_reviewer_assumptions', True),
        ('fold_probabilities_are_assumptions', True),
        ('action_observed_or_graded', False),
        ('ocr_semantics_verified', False),
        ('hero_identity_verified', False),
        ('confidence_intervals_cover_sampling_only', True),
    ):
        require(sensitivity.get(key) is expected, f'unsafe sensitivity flag: {key}')
    equity = report['equity_result']
    for key in ('variant', 'hero_cards', 'board_cards'):
        require(sensitivity.get(key) == equity.get(key), f'{key} mismatch with acknowledged cards')
    pot = _number(sensitivity.get('pot_now_including_opponent_bet'), 'pot', 1e-6, 1e9)
    cost = _number(sensitivity.get('hero_call_cost'), 'call cost', 1e-6, 1e9)
    extra = _number(sensitivity.get('hero_raise_extra_above_call'), 'raise extra', 1e-6, 1e9)
    require(pot >= cost and pot + cost + 2*extra <= 1e9, 'invalid pot geometry')
    grid = sensitivity.get('fold_probabilities')
    hypotheses = sensitivity.get('hypotheses')
    require(type(grid) is list and 2 <= len(grid) <= 21 and
            type(hypotheses) is list and 1 <= len(hypotheses) <= 5,
            'invalid EV grid size')
    ps = [_number(x, 'fold probability', 0, 1) for x in grid]
    require(all(a < b for a, b in zip(ps, ps[1:])), 'unsorted fold probabilities')
    seen = set()
    for h in hypotheses:
        require(type(h) is dict, 'invalid hypothesis')
        label = h.get('label')
        require(type(label) is str and 1 <= len(label) <= 64 and
                all(c.isprintable() and c not in '<>\\' for c in label) and
                label not in seen, 'invalid/duplicate hypothesis label')
        seen.add(label)
        require(h.get('call_range_model') in ('uniform', 'weighted_combos') and
                h.get('raise_called_range_model') in ('uniform', 'weighted_combos'),
                'invalid range model')
        call_equity = _number(h.get('call_equity'), 'call equity', 0, 1)
        raise_equity = _number(h.get('raise_called_equity'), 'raise equity', 0, 1)
        for field in ('call_iterations', 'raise_called_iterations'):
            require(type(h.get(field)) is int and 2 <= h[field] <= 50000,
                    'invalid Monte Carlo iterations')
        for field in ('call_seed', 'raise_called_seed'):
            require(type(h.get(field)) is int and 0 <= h[field] < 2**32,
                    'invalid Monte Carlo seed')
        _number(h.get('baseline_fold_probability_assumed'), 'baseline fold probability', 0, 1)
        threshold = h.get('break_even_fold_probability_unclipped')
        if threshold is not None:
            _number(threshold, 'break-even threshold')
        points = h.get('points')
        require(type(points) is list and len(points) == len(ps), 'incomplete EV points')
        call_ev = call_equity * (pot + cost) - cost
        called_raise_ev = raise_equity * (pot + cost + 2*extra) - cost - extra
        for p, point in zip(ps, points):
            require(type(point) is dict, 'invalid EV point')
            observed_p = _number(point.get('fold_probability_assumed'), 'point probability', 0, 1)
            require(_close(observed_p, p), 'point probability mismatch')
            expected_raise = p*pot + (1-p)*called_raise_ev
            for key, expected in (
                ('fold_ev_incremental', 0.0),
                ('call_ev_incremental', call_ev),
                ('raise_ev_incremental', expected_raise),
                ('raise_minus_call_ev', expected_raise-call_ev),
            ):
                require(_close(_number(point.get(key), key), expected),
                        f'inconsistent EV arithmetic: {key}')
            for key, center in (
                ('raise_ev_ci95_sampling_only_fixed_ranges_and_fold_probability', expected_raise),
                ('raise_minus_call_bounds_from_marginals_not_joint_ci', expected_raise-call_ev),
            ):
                bounds = point.get(key)
                require(type(bounds) is list and len(bounds) == 2, 'invalid sampling bounds')
                lo, hi = [_number(v, key) for v in bounds]
                require(lo <= center+1e-7 and hi+1e-7 >= center and lo <= hi,
                        'sampling bounds exclude estimate')
    return pot, cost, extra


def _svg(sensitivity):
    """Small static SVG; points are numeric and labels never enter SVG attributes."""
    series = [(h['label'], [p['raise_ev_incremental'] for p in h['points']])
              for h in sensitivity['hypotheses']]
    all_values = [v for _, values in series for v in values] + [0.0]
    low, high = min(all_values), max(all_values)
    if high == low:
        high += 1
        low -= 1
    x0, x1, y0, y1 = 48, 620, 16, 202
    def x(p): return x0 + (x1-x0)*p
    def y(v): return y1 - (v-low)/(high-low)*(y1-y0)
    zero = y(0)
    colors = ('#2060a0', '#a44b22', '#247b58', '#7846a5', '#9b6a13')
    shapes = [f'<line x1="{x0}" y1="{zero:.2f}" x2="{x1}" y2="{zero:.2f}" stroke="#666" stroke-dasharray="4 4"/>']
    for idx, (_, values) in enumerate(series):
        coords = ' '.join(f'{x(p):.2f},{y(v):.2f}' for p, v in zip(sensitivity['fold_probabilities'], values))
        shapes.append(f'<polyline fill="none" stroke="{colors[idx]}" stroke-width="2.5" points="{coords}"/>')
    shapes.extend((f'<text x="{x0}" y="225" font-size="12">0% fold</text>',
                   f'<text x="{x1}" y="225" text-anchor="end" font-size="12">100% fold</text>',
                   f'<text x="{x0}" y="12" font-size="11">EV raise (fichas)</text>'))
    return ('<svg viewBox="0 0 660 238" role="img" '
            'aria-label="Curvas hipotéticas de EV do raise por probabilidade de fold" '
            'style="width:100%;height:auto;background:#f7f9fb;border-radius:8px">'
            + ''.join(shapes) + '</svg>')


def render(report, sensitivity, clip_sha):
    base = render_equity(report, clip_sha)  # verifies acknowledgement and clip binding
    pot, cost, extra = validate(report, sensitivity)
    blocks = ['<section aria-label="Sensibilidade do EV"><h2>EV condicional — hipóteses, não avaliação da jogada</h2>',
              '<p class="warning">As probabilidades de fold e os ranges foram fornecidos pelo revisor. '
              'Não foram inferidos do vídeo. Os intervalos são apenas de amostragem Monte Carlo; '
              'as diferenças entre ranges não são intervalos de confiança. '
              'A combinação de limites marginais não constitui IC conjunto de 95%.</p>']
    blocks.append(f'<p>Pote atual: {pot:.2f} fichas; custo do call: {cost:.2f}; '
                  f'raise adicional: {extra:.2f}. Modelo heads-up terminal, sem rake, '
                  'side pots, all-in ou apostas futuras. Fold = 0 fichas incrementais.</p>')
    blocks.append(_svg(sensitivity))
    colors = ('#2060a0', '#a44b22', '#247b58', '#7846a5', '#9b6a13')
    blocks.append('<p><strong>Curvas:</strong> ' + ' · '.join(
        f'<span style="color:{colors[i]}">●</span> {escape(h["label"])}'
        for i, h in enumerate(sensitivity['hypotheses'])) + '</p>')
    for h in sensitivity['hypotheses']:
        blocks.append(f'<h3>Hipótese: {escape(h["label"])}</h3>')
        blocks.append(f'<p>Range call: {escape(h["call_range_model"])}; '
                      f'range após raise pago: {escape(h["raise_called_range_model"])}. '
                      f'Equity call: {h["call_equity"]:.2%}; '
                      f'equity raise pago: {h["raise_called_equity"]:.2%}. '
                      f'Simulações: {h["call_iterations"]} / {h["raise_called_iterations"]}; '
                      f'sementes: {h["call_seed"]} / {h["raise_called_seed"]}.</p>')
        blocks.append('<div style="overflow-x:auto"><table><thead><tr>'
                      '<th>Fold assumido</th><th>EV call</th><th>EV raise</th><th>Raise − call</th>'
                      '</tr></thead><tbody>')
        for p in h['points']:
            blocks.append('<tr>' + ''.join(f'<td>{v}</td>' for v in (
                f'{p["fold_probability_assumed"]:.0%}',
                f'{p["call_ev_incremental"]:+.2f}',
                f'{p["raise_ev_incremental"]:+.2f}',
                f'{p["raise_minus_call_ev"]:+.2f}')) + '</tr>')
        blocks.append('</tbody></table></div>')
    blocks.append('<p><small>Comparação de cenários sintéticos ou hipotéticos; '
                  'nenhuma ação do vídeo foi classificada como correta ou incorreta. '
                  'O vínculo do relatório à gravação original e a auditoria de PNGs '
                  'não são refeitos nesta página.</small></p></section>')
    require(base.count('</main>') == 1, 'unexpected base HTML')
    css = '<style>table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}' \
          'th,td{border-bottom:1px solid #dce2e8;padding:.4rem;text-align:right}' \
          'th:first-child,td:first-child{text-align:left}h3{font-size:1rem;margin-top:1.5rem}</style>'
    return base.replace('</head>', css + '</head>').replace('</main>', ''.join(blocks) + '</main>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('acknowledged_report_json', 'sensitivity_json', 'clip_mp4', 'new_html'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    report_path = safe_file(args.acknowledged_report_json, max_bytes=2_000_000)
    sensitivity_path = safe_file(args.sensitivity_json, max_bytes=2_000_000)
    clip_path = safe_file(args.clip_mp4)
    out = Path(args.new_html)
    sources = (report_path, sensitivity_path, clip_path)
    require(len({p.resolve() for p in sources}) == len(sources), 'sources must differ')
    require(out.parent.is_dir() and not out.parent.is_symlink() and
            out.suffix == '.html' and not out.exists() and not out.is_symlink() and
            out.resolve() not in {p.resolve() for p in sources}, 'HTML output must be new')
    require(out.parent.resolve() == clip_path.parent.resolve() and clip_path.name == 'clip.mp4',
            'HTML must be next to clip.mp4')
    hashes = [digest(p) for p in sources]
    html = render(read_json(report_path), read_json(sensitivity_path), hashes[-1])
    require(hashes == [digest(p) for p in sources], 'source changed while rendering')
    with out.open('x', encoding='utf-8') as stream:
        stream.write(html)
    print(json.dumps({'html_created': str(out), 'clip_sha256': hashes[-1],
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
