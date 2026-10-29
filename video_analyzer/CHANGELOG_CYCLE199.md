# Ciclo 199 — bundle offline de EV a partir de cartas confirmadas

## Mudança
`offline_acknowledged_sensitivity_bundle.py` cria, em uma execução, o JSON de sensibilidade de EV e a página HTML offline com vídeo. **As cartas são copiadas exclusivamente do relatório de confirmação humana**; o JSON separado de hipóteses não pode fornecer/substituir cartas, ações ou flags de reconhecimento. Cada hipótese informa ranges condicionais de call e raise pago, sementes, iterações e probabilidade hipotética de fold. Os cálculos usam `offline_conditional_ev_sensitivity.py` e o HTML existente.

```bash
python video_analyzer/offline_acknowledged_sensitivity_bundle.py \
  ACKNOWLEDGED_REPORT.json ASSUMPTIONS.json clip.mp4 \
  NEW_SENSITIVITY.json NEW_EXPLANATION.html
```

Formato de `ASSUMPTIONS.json`:

```json
{
  "schema_version": 1,
  "pot_now": 100,
  "call_cost": 20,
  "raise_extra": 40,
  "fold_probabilities": [0, 0.35, 1],
  "hypotheses": [{
    "label": "uniforme",
    "call_model": {"kind": "uniform"},
    "raise_called_model": {"kind": "uniform"},
    "call_iterations": 500,
    "raise_called_iterations": 500,
    "call_seed": 42,
    "raise_called_seed": 43,
    "fold_probability_assumed": 0.35
  }]
}
```

## Integridade e limitações
- Reutiliza a validação do relatório humano e o vínculo SHA-256 ao clipe `clip.mp4`; preserva status de não verificação automática.
- JSON e HTML carregam SHA-256 do relatório, das hipóteses e do clipe; são gerados apenas como arquivos novos, lado a lado com o MP4. Entradas são verificadas novamente após o cálculo.
- Não reexecuta auditoria do vídeo original, OCR, PNGs ou confirmação humana. A integridade por hash **não prova** que as cartas aparecem no vídeo.
- Ranges, fold equity e parâmetros do pote são **hipóteses**, não observações. Monte Carlo fornece apenas incerteza de amostragem condicional aos parâmetros. Modelo heads-up terminal sem rake, side pots, all-in ou futuras apostas. Não classifica decisões.
- Não usa serviços externos, dados de poker ao vivo, automação de apostas ou interface de jogo.

## Verificação local em 29/10/2026
- 13 testes novos do bundle aprovados; 76 testes selecionados aprovados (incluindo regressões de equity/EV/HTML).
- Demonstração sintética com MP4 de 2,0 segundos (FFprobe) e CLI completa: JSON, HTML, gráfico e hashes gerados. O vídeo não mostra cartas correspondentes à anotação artificial.
- Sem teste da suíte integral do repositório, Windows, navegador gráfico ou gravações reais de 40–60 minutos.

## Bloqueio e próxima etapa
Ainda falta um vídeo autorizado e anotado de 3–5 minutos para medir precisão de OCR, segmentação e atribuição de ações. Próximo: validar consistência de ranges por cenário, oferecer UI de hipóteses com aviso de incerteza e benchmark sintético de quatro mesas.
