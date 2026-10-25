"""Generate an offline, read-only HTML report for *hypothetical* PLO5/PLO6 math.

Recomputes the bounded Monte Carlo run from pristine intake + manually completed
worksheet and rejects a changed result. Never verifies OCR, hand reconstruction,
video provenance, opponent ranges or strategic correctness. No remote resources.
"""
import argparse
from html import escape
import hashlib
import json
from pathlib import Path

from hand_math_scenario_run import _load, run

MAX_HTML_BYTES = 2 * 1024 * 1024


def _text(value):
    return escape(str(value), quote=True)


def _number(value, decimals=3):
    return f'{value:.{decimals}f}'


def _row(label, value):
    return f'<div class="row"><dt>{_text(label)}</dt><dd>{_text(value)}</dd></div>'


def render(intake, filled, math_result, *, intake_sha256, filled_sha256, math_sha256):
    """Verify math by deterministic recomputation before rendering any HTML."""
    expected = run(intake, filled, intake_sha256)
    if expected != math_result:
        raise ValueError('Mathematical result differs from reproducible calculation')
    for digest in (intake_sha256, filled_sha256, math_sha256):
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid source SHA-256')
    cards = []
    for task, completed_task, result in zip(intake['tasks'], filled['tasks'], math_result['results']):
        if (result['entry_id'], result['table_id']) != (task['entry_id'], task['table_id']):
            raise ValueError('Mismatched task/result ordering')
        status = result['status']
        if status == 'hypothetical_only_not_video_verified':
            ci = result['equity_sampling_ci95']
            ev_ci = result['ev_sampling_ci95']
            scenario = completed_task['manual_scenario_draft']
            fields = scenario['reviewed_fields']
            assumptions = scenario['model_assumptions']
            sample_range = '; '.join(
                ' '.join(item['cards']) + ' (peso ' + str(item['weight']) + ')'
                for item in scenario['call_range'][:3]
            )
            if len(scenario['call_range']) > 3:
                sample_range += f"; +{len(scenario['call_range']) - 3} combinações"
            body = ''.join((
                _row('Modalidade', result['variant']),
                _row('Ação assumida', result['observed_action_assumed']),
                _row('Cartas privadas declaradas', ' '.join(fields['hero_cards']['value'])),
                _row('Board declarado', ' '.join(fields['board']['value']) or '(sem board)'),
                _row('Pote antes da ação', fields['pot_before_action']['value']),
                _row('Valor para pagar', fields['call_amount']['value']),
                _row('Range adversário (amostra, não inferido)', sample_range),
                _row('Probabilidade de fold hipotética',
                     'não aplicável' if scenario['fold_probability'] is None else
                     _number(scenario['fold_probability'] * 100, 1) + '%'),
                _row('Aporte extra herói / adversário se pago',
                     'não aplicável' if assumptions['hero_extra_chips'] is None else
                     f"{assumptions['hero_extra_chips']} / {assumptions['villain_extra_chips_if_called']}"),
                _row('Equity estimada', _number(result['equity'] * 100, 2) + '%'),
                _row('IC 95% da amostragem de equity',
                     f'{_number(ci[0] * 100, 2)}% – {_number(ci[1] * 100, 2)}%'),
                _row('EV modelado vs. fold = 0', _number(result['ev_vs_fold_zero'], 2) + ' fichas'),
                _row('IC 95% propagado da amostragem de EV',
                     f'{_number(ev_ci[0], 2)} – {_number(ev_ci[1], 2)} fichas'),
                _row('Simulações / semente', f"{result['trials']} / {result['seed']}"),
                _row('Range adversário (combinações)', result['opponent_range_combinations']),
                _row('Confiança observacional (estimativa humana)',
                     _number(result['observation_confidence_human_estimate'] * 100, 1) + '%'),
                _row('Observações do modelo', result['model_notes']),
                _row('Limitações', result['model_limitations']),
            ))
        elif status == 'blocked_invalid_manual_scenario':
            body = _row('Motivo do bloqueio', result['reason'])
        else:
            body = _row('Motivo', 'Formulário matemático não preenchido; sem cálculo.')
        cards.append('<article class="card"><h2>Mesa ' + _text(task['table_id']) +
                     ' · Intervalo ' + _text(task['entry_id']) + '</h2>' +
                     '<p class="badge">' + _text(status) + '</p>' +
                     '<dl>' + body + '</dl><p class="caution">Não é uma mão reconstruída ou erro comprovado.</p></article>')
    counts = math_result['counts']
    summary = (f"{counts['total']} intervalos · {counts['hypothetical']} cálculos hipotéticos · "
               f"{counts['blocked']} bloqueados · {counts['skipped']} sem cálculo")
    html = '''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; form-action 'none'; base-uri 'none'">
<title>PLO Trainee · Relatório matemático hipotético</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#101827;color:#e9f0fa}
body{max-width:1050px;margin:0 auto;padding:24px;line-height:1.5}
h1{font-size:1.9rem}h2{font-size:1.2rem}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}
.card{background:#1c2a3e;border:1px solid #35465b;border-radius:12px;padding:18px;min-width:0}
.row{display:grid;grid-template-columns:1fr 1.2fr;gap:10px;border-bottom:1px solid #35465b;padding:8px 0}
dt{color:#aebed0}dd{margin:0;overflow-wrap:anywhere}.badge{color:#f5d28e;overflow-wrap:anywhere}
.caution,.warning{color:#ffd38b}.warning{background:#46301f;padding:14px;border-radius:8px}
.provenance{overflow-wrap:anywhere;font-size:.85rem;color:#b8c7d8}footer{margin-top:22px}
</style></head><body><header><h1>PLO Trainee · Análise matemática hipotética</h1>
<p class="warning"><strong>ATENÇÃO:</strong> estes cálculos dependem de cartas, ranges e apostas informados manualmente.
Não demonstram reconstrução do vídeo, precisão de OCR, validade dos ranges ou erro estratégico.
O intervalo de 95% cobre apenas amostragem Monte Carlo, não incerteza do modelo.</p>
<p>__SUMMARY__</p></header><main>__CARDS__</main>
<footer><h2>Rastreabilidade dos arquivos de entrada</h2>
<p class="provenance">Intake SHA-256: __INTAKE__<br>
Formulário preenchido SHA-256: __FILLED__<br>
Resultado matemático SHA-256: __MATH__</p>
<p>Relatório estático, sem JavaScript, serviços externos ou integração com mesas ao vivo.
Os hashes identificam arquivos, não autenticam a gravação ou as anotações humanas.</p></footer></body></html>'''
    html = (html.replace('__SUMMARY__', _text(summary))
            .replace('__CARDS__', ''.join(cards))
            .replace('__INTAKE__', _text(intake_sha256))
            .replace('__FILLED__', _text(filled_sha256))
            .replace('__MATH__', _text(math_sha256)))
    if len(html.encode('utf-8')) > MAX_HTML_BYTES:
        raise ValueError('HTML report exceeds size limit')
    return html


def export(intake_path, filled_path, math_path, output_path):
    paths = [Path(p) for p in (intake_path, filled_path, math_path)]
    output = Path(output_path)
    if (output.exists() or output.is_symlink() or
            output.resolve() in [p.resolve() for p in paths]):
        raise ValueError('Output must be new and different from inputs')
    documents, raws = [], []
    for path in paths:
        doc, raw = _load(path)  # bounded, duplicate-key-safe JSON parser
        documents.append(doc)
        raws.append(raw)
    hashes = [hashlib.sha256(raw).hexdigest() for raw in raws]
    html = render(*documents, intake_sha256=hashes[0],
                  filled_sha256=hashes[1], math_sha256=hashes[2])
    if any(path.read_bytes() != raw for path, raw in zip(paths, raws)):
        raise ValueError('Input changed during report generation')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as target:
        target.write(html)
    return {'report': str(output), 'source_sha256': hashes,
            'counts': documents[2]['counts']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_intake_json')
    parser.add_argument('manually_completed_json')
    parser.add_argument('math_result_json')
    parser.add_argument('new_report_html')
    args = parser.parse_args(argv)
    print(json.dumps(export(args.original_intake_json, args.manually_completed_json,
                            args.math_result_json, args.new_report_html), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
