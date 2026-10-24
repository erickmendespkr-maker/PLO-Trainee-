# PLO Trainee — Ciclo 63: intervalos de revisão entre mãos

## Entrega

`activity_hand_boundary_review.py` transforma a linha do tempo **já revisada por uma pessoa** (`activity_reviewed_hand_timeline.py`) em intervalos de revisão entre identificadores de mãos consecutivos da mesma mesa. O resultado **não** determina o instante exato de início/fim, não atribui identificadores ausentes e não seleciona clipes automaticamente.

- Quatro mesas independentes; timestamps PTS decodificados; janelas entre a última observação de A e a primeira de B.
- Bloqueios explícitos para observações não atribuídas, timestamps coincidentes, mãos sobrepostas, flags de inconsistência e lacunas excessivas.
- Possibilidade de anexar `boundary_hints.py` apenas como pistas OCR não verificadas. Sem `recording_sha256` no relatório de pistas, a identidade da gravação é declarada **não vinculada**; quando presente, o hash deve coincidir.
- Vinculação SHA-256 canônica à linha do tempo e ao relatório de revisão original. Hash de conteúdo JSON **não comprova** a verdade visual das cartas ou a existência dos quadros de origem.
- CLI com saída JSON nova e proteção contra sobrescrita, e testes sintéticos de quatro mesas.

## Execução

```bash
python video_analyzer/activity_hand_boundary_review.py timeline.json revisao_limites.json \
  --expected-timeline-sha256 HASH_SHA256_CANONICO
```

Opcional: `--hints-json pistas.json --max-gap-seconds 120`. O hash canônico é calculado com `canonical_sha256` de `activity_snapshot_chain.py`, **não** com `sha256sum` do arquivo JSON formatado.

## Limites

O sistema não infere cartas, ações, resultados, ranges ou EV. A observação humana não é uma garantia de precisão. Sem gravação real autorizada, a qualidade de OCR e a segmentação automática continuam **não verificadas**. A seleção/exportação de MP4 continua exigindo confirmação humana.

## Verificação local

- `pytest` direcionado aos módulos de linha do tempo, limites, pistas OCR, PTS e extração de clipes: **66 testes aprovados, 15 subtestes aprovados**.
- A suíte total foi iniciada mas excedeu o tempo disponível; **não** se declara um total atualizado.
- Nenhuma alteração em `main`, infraestrutura, credenciais ou custos.
