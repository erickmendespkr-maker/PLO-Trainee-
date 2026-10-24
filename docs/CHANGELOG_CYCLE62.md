# PLO Trainee — Ciclo 62: linha do tempo de mãos revisadas

Escopo: processamento **offline/assíncrono** de gravações PLO5/PLO6. Não há integração com mesas ao vivo, jogos jogáveis ou apostas.

## Implementado

- `video_analyzer/activity_reviewed_hand_timeline.py`: consome **somente** o JSON de observações OCR revisadas por humanos, com validação de proveniência realizada por `activity_snapshot_chain`.
- Agrupa eventos por `table_id` e `hand_id` **explicitamente atribuídos**, sem inventar identificadores para eventos não atribuídos.
- Registra PTS decodificado, índice da observação, ação anotada, valores visíveis, campos de origem OCR e confiança **subjetiva** do revisor.
- Marca as transições de board entre dois PTS, distinguindo extensões compatíveis de mudanças incompatíveis; não estima o instante exato da mudança.
- Sinaliza conflito de cartas privadas, colisão entre cartas privadas e board, mudanças de variante, anotações com PTS idênticos conflitantes, mãos intercaladas e inícios/finais ausentes.
- Preserva eventos sem `hand_id` em uma fila de revisão, sem agrupamento automático.
- Todos os resultados permanecem **bloqueados para equity/EV, classificação de erros e seleção automática de cortes**.

## Executar

```bash
cd video_analyzer
python activity_reviewed_hand_timeline.py reviewed_activity.json reviewed_hand_timeline.json --expected-review-sha256 SHA256_CANONICO
python -m unittest -v test_activity_reviewed_hand_timeline
```

O SHA-256 opcional é calculado sobre JSON canônico com `activity_snapshot_chain.canonical_sha256`, não substitui a auditoria dos bytes originais da gravação ou das imagens.

## Limitações

A entrada pressupõe revisão humana; **não** prova que as cartas ou ações foram reconhecidas corretamente. Uma extensão de board compatível não prova continuidade da mão, e uma mudança incompatível não prova início de outra mão. A reconstrução automática real e os testes com vídeos de 40–60 minutos continuam pendentes de material autorizado.
