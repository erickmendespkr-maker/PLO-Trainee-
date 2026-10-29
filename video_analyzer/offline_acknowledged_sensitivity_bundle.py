"""Create an offline EV-sensitivity JSON and MP4 explanation from acknowledged cards.

CLI: python offline_acknowledged_sensitivity_bundle.py ACK_REPORT.json \
     ASSUMPTIONS.json clip.mp4 NEW_SENSITIVITY.json NEW_EXPLANATION.html

The assumptions file intentionally cannot supply cards, observed actions, or
verified status. Cards are copied exclusively from the previously acknowledged
report. Hashes bind inputs, but DO NOT re-audit frames, OCR or video provenance.
No poker site, real-time interaction, opponent inference or action grading.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from offline_acknowledged_ev_sensitivity_html import render as render_html
from offline_conditional_ev_sensitivity import build as build_sensitivity
from offline_equity_clip_explanation import render as render_equity
from offline_plo_equity_monte_carlo import read_json, require
from offline_reviewed_equity_clip_report import digest, safe_file


CONFIG_FIELDS = {'schema_version', 'pot_now', 'call_cost', 'raise_extra',
                 'fold_probabilities', 'hypotheses'}
HYPOTHESIS_FIELDS = {'label', 'call_model', 'raise_called_model',
                     'call_iterations', 'raise_called_iterations', 'call_seed',
                     'raise_called_seed', 'fold_probability_assumed'}


def build(report, config, clip_sha, report_sha, assumptions_sha):
    """Return (sensitivity, HTML); Monte Carlo uses ONLY acknowledged cards."""
    # Reuse the existing human-acknowledgement and clip-hash safety gate.
    render_equity(report, clip_sha)
    require(type(config) is dict and set(config) == CONFIG_FIELDS and
            type(config.get('schema_version')) is int and config['schema_version'] == 1,
            'invalid assumptions schema; cards and actions are not accepted')
    hypotheses = config['hypotheses']
    require(type(hypotheses) is list and 1 <= len(hypotheses) <= 5,
            'one to five range hypotheses required')
    equity = report['equity_result']
    common = {'variant': equity['variant'],
              'hero_cards': equity['hero_cards'].copy(),
              'board_cards': equity['board_cards'].copy(),
              'manual_review_confirmed': True}
    scenarios = []
    for h in hypotheses:
        require(type(h) is dict and set(h) == HYPOTHESIS_FIELDS,
                'invalid hypothesis schema; cards/actions cannot be overridden')
        call = {**common, 'hero_cards': common['hero_cards'].copy(),
                'board_cards': common['board_cards'].copy(),
                'opponent_model': h['call_model'], 'iterations': h['call_iterations'],
                'seed': h['call_seed']}
        raised = {**common, 'hero_cards': common['hero_cards'].copy(),
                  'board_cards': common['board_cards'].copy(),
                  'opponent_model': h['raise_called_model'],
                  'iterations': h['raise_called_iterations'],
                  'seed': h['raise_called_seed']}
        scenarios.append({'label': h['label'], 'ev_input': {
            'call_scenario': call, 'raise_called_scenario': raised,
            'pot_now': config['pot_now'], 'call_cost': config['call_cost'],
            'raise_extra': config['raise_extra'],
            'fold_probability_assumed': h['fold_probability_assumed']}})
    result = build_sensitivity({'hypotheses': scenarios,
                                'fold_probabilities': config['fold_probabilities']})
    result.update({
        'source_acknowledged_report_sha256': report_sha,
        'source_assumptions_sha256': assumptions_sha,
        'source_clip_sha256': clip_sha,
        'source_hand_id': report['hand_id'],
        'cards_copied_from_human_acknowledged_report': True,
        'source_frame_audit_rerun': False,
        'assumptions_and_ranges_not_observed': True,
    })
    html = render_html(report, result, clip_sha)
    # Only fixed SHA-256 digests and the already validated hand ID enter this
    # section; the full user-provided assumptions never enter raw HTML.
    provenance = ('<section aria-label="Proveniência das hipóteses">'
                  '<h2>Rastreabilidade dos parâmetros</h2>'
                  '<p>Cartas copiadas do relatório de confirmação humana. '
                  'Ranges e probabilidades fornecidos separadamente pelo revisor; '
                  'não são inferidos do vídeo. A auditoria de quadros não foi repetida.</p>'
                  f'<small>SHA-256 relatório: {report_sha}<br>'
                  f'SHA-256 hipóteses: {assumptions_sha}<br>'
                  f'SHA-256 clipe: {clip_sha}</small></section>')
    require(html.count('</main>') == 1, 'unexpected HTML layout')
    return result, html.replace('</main>', provenance + '</main>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('acknowledged_report_json', 'assumptions_json', 'clip_mp4',
                 'new_sensitivity_json', 'new_explanation_html'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    report_path = safe_file(args.acknowledged_report_json, max_bytes=2_000_000)
    assumptions_path = safe_file(args.assumptions_json, max_bytes=2_000_000)
    clip_path = safe_file(args.clip_mp4)
    sources = (report_path, assumptions_path, clip_path)
    require(len({p.resolve() for p in sources}) == 3, 'source files must differ')
    out_json, out_html = Path(args.new_sensitivity_json), Path(args.new_explanation_html)
    outputs = (out_json, out_html)
    require(clip_path.name == 'clip.mp4', 'clip must be named clip.mp4')
    require(out_json.suffix == '.json' and out_html.suffix == '.html' and
            all(p.parent.is_dir() and not p.parent.is_symlink() and
                p.parent.resolve() == clip_path.parent.resolve() and
                not p.exists() and not p.is_symlink() for p in outputs) and
            len({p.resolve() for p in sources + outputs}) == 5,
            'outputs must be new distinct files beside clip.mp4')
    before = [digest(p) for p in sources]
    result, html = build(read_json(report_path), read_json(assumptions_path),
                         before[2], before[0], before[1])
    require(before == [digest(p) for p in sources], 'source changed during analysis')
    # Serialize before creating either output. Never overwrite evidence.
    payload = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    created_json = created_html = False
    try:
        with out_json.open('x', encoding='utf-8') as stream:
            created_json = True
            stream.write(payload)
        with out_html.open('x', encoding='utf-8') as stream:
            created_html = True
            stream.write(html)
    except Exception:
        # Roll back only files successfully created by this process.
        if created_html:
            out_html.unlink()
        if created_json:
            out_json.unlink()
        raise
    print(json.dumps({'analysis_status': result['analysis_status'],
                      'hypotheses': len(result['hypotheses']),
                      'source_assumptions_sha256': before[1],
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
