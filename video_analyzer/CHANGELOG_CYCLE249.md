# PLO Trainee — Ciclo 249 (2026-10-31)

## Entrega

Novo `video_analyzer/offline_street_human_review.py`: revisão humana explícita, por evento, das evidências por street criadas em `offline_street_evidence.py`. Opera somente sobre gravações offline, sem acesso a clientes de poker ou ações em tempo real.

A revisão aceita `confirm` (mantém valor, `value: null`, `reason: ""`), `correct` (substitui valor com justificativa) e `reject` (descarta valor com justificativa). Exige uma decisão para cada observação e uma entrada para cada mão; rejeita IDs duplicados, valores inválidos, cartas repetidas, contagens incompatíveis com PLO5/PLO6, alterações de origem, hashes divergentes e JSON com chaves duplicadas. Preserva timestamp, origem, confiança *não calibrada*, valor original e decisão humana.

O módulo recompõe o relatório de streets a partir das observações originais, confere os hashes SHA-256, detecta divergências nas cartas revisadas e gera `street_human_review.json` e `street_human_review.html`. Saída atômica por hard links, com limpeza se ocorrer falha. O resultado **não autoriza automaticamente** equity, EV, leitura OCR, range adversário ou julgamento estratégico. A confirmação é uma alegação humana, não prova de verdade visual.

## Uso

Na raiz do repositório, depois de gerar `STREET_DIR/street_evidence_report.json`:

```bash
python video_analyzer/offline_street_human_review.py VIDEO.mp4 OBSERVATIONS.json STREET_DIR REVIEW.json OUTPUT_DIR
```

Criar `OUTPUT_DIR` vazio antes da execução. `REVIEW.json` deve ter o formato:

```json
{
  "schema_version": 1,
  "status": "manual_offline_street_review",
  "source_street_report_sha256": "<SHA256 do street_evidence_report.json>",
  "reviewer_label": "operator_1",
  "hands": [{
    "table_id": "T1",
    "hand_id": "H1",
    "decisions": [
      {"event_index": 0, "decision": "confirm", "value": null, "reason": ""},
      {"event_index": 1, "decision": "correct", "value": ["2C", "3D", "4H"], "reason": "quadro revisto"},
      {"event_index": 2, "decision": "reject", "value": null, "reason": "ação encoberta"}
    ]
  }]
}
```

A lista `decisions` precisa conter **exatamente um item para cada evento da mão** na ordem apresentada pelo relatório por street. O exemplo acima só é válido para uma mão com três eventos e uma correção de board efetivamente diferente da proposta original.

## Testes executados

- 18 testes novos com vídeo FFmpeg sintético de quatro segundos, correção, rejeição, validação de cartas, proveniência, hashes, HTML escapado, symlinks, colisões e rollback.
- 75 testes selecionados passaram (incluindo regressão por street e índice de cortes) no ambiente local de desenvolvimento. Não equivalem à suíte integral.
- Os blobs Git do módulo e dos testes publicados coincidem com as versões locais executadas.

## Pendências e limites

Não há gravação real autorizada e anotada de 3–5 minutos; reconhecimento OCR, calibração de confiança, processamento de 40–60 minutos, Windows e suíte completa não foram validados. A revisão ainda é realizada por JSON, sem interface gráfica de correção. Próximo passo: interface local de revisão e adaptação de dados revisados a um contrato matemático **explícito e não automático**, com ranges e intervalos de confiança.
