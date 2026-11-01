# Ciclo 253 — entrada matemática controlada após revisão humana (offline)

## Entrega publicada
- `video_analyzer/offline_math_input_gate.py`: converte **uma mão** de `street_human_review.json` e hipóteses **manualmente declaradas** em `reviewed_math_candidate` auditável.
- `video_analyzer/test_offline_math_input_gate.py`: 17 testes sintéticos para PLO5/PLO6, conflitos de cartas, sobreposição de ranges, hash de origem, duplicação de chaves JSON, NaN, rejeição e arquivo de saída exclusivo.
- Não interage com sites, clientes ou mesas de poker. Nenhum simulador jogável.

## Execução
```bash
cd video_analyzer
python -m unittest -v test_offline_math_input_gate.py
python offline_math_input_gate.py /dados/street_human_review.json /dados/manual_assumptions.json /saida/math_candidate.json
```

## Contrato de hipóteses (manual_assumptions.json)
```json
{
  "schema_version": 1,
  "table_id": "table_1",
  "hand_id": "hand_1",
  "source_review_sha256": "<sha256 do street_human_review.json>",
  "reviewer_attestation": true,
  "range_source": "Range hipotético definido manualmente, não inferido por OCR",
  "villain_combos": [
    {"cards": ["6c", "7d", "8h", "9s", "Tc"], "weight": 1.0}
  ],
  "pot_before_call": 100,
  "to_call": 20,
  "seed": 1234,
  "trials": 1000,
  "model": "heads_up_call_all_in_no_future_betting_no_rake"
}
```
Para PLO6 cada combo e a mão do herói devem conter seis cartas. O pote informado inclui a aposta adversária já feita, mas não a futura chamada do herói. Todas as unidades monetárias devem ser coerentes. Os pesos do range são hipóteses, não observações.

## Comportamento seguro
O módulo falha fechado quando faltam cartas privadas, existe conflito/rejeição de evidência de cartas, há sobreposição com board/cartas privadas, falta a declaração humana, há hashes incompatíveis ou o modelo não é suportado. Não autoriza OCR automaticamente nem calcula equity/EV. Produz status `reviewed_math_candidate_manual_ranges_not_computed`.

## Testes
Executados localmente em 31/10/2026: `python -m unittest -v test_offline_math_input_gate.py`, **17/17 aprovados**. Hash Git do código publicado: `6dc6d34512413f5bf10b249128379b906badbee1`; hash Git dos testes: `a9f762adec21f987e65dac76ca8803df74ebc1d8`. Não houve teste de vídeo real ou suíte completa.

## Limitações e próximo passo
Já existe `offline_omaha_equity_mc.py` no repositório, com range **uniforme** e equity condicional; **não** substituí nem modifiquei esse motor. A nova entrada suporta pesos por combo, portanto a integração precisa rejeitar ranges não uniformes ou implementar amostragem ponderada validada. Não conectar automaticamente um candidato ao motor sem revalidar origem e hipóteses. O motor existente não calcula EV; estimativas de EV de call/fold requerem modelo explícito de pote, custo, rake e futuras apostas.

Continua faltando vídeo real autorizado/anotado de 3–5 minutos. Não validados OCR real, Windows, 40–60 minutos ou pipeline completo.
