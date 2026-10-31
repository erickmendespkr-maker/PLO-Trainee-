# Ciclo 233 — contrato de entrada Monte Carlo para cenários manuais

## Entrega
- `offline_mc_input_contract.py` valida um cenário **transcrito independentemente** e explicitamente vinculado a um resumo de revisão por hash SHA-256, mão, mesa e hash declarado do vídeo.
- Não importa cartas do OCR/revisão visual como fatos. O resumo permanece `eligible_for_equity: 0`; a saída é `manual_scenario_validated_not_executed`.
- Aceita PLO5 e PLO6, 5/6 cartas privadas, board flop/turn/river (3–5 cartas), cartas canônicas, 1–3 ranges adversários explícitos com 1–100 combinações ponderadas cada.
- Rejeita cartas duplicadas, colisões com cartas conhecidas, ranges sem atribuição conjunta disjunta, pesos inválidos, sementes e contagens de simulações fora dos limites, potes/stacks inválidos, schema desconhecido, JSON com chaves repetidas ou NaN.
- Exige hipóteses narradas, semente determinística, número de simulações e modelo restrito a `showdown_equity_only`. A regra Omaha fica explícita: exatamente duas privadas e três comunitárias.
- Não calcula equity, EV, intervalo de confiança ou recomendação de jogada. A saída sinaliza esses estados como falsos.
- CLI local recusa sobrescrever saídas e verifica hashes das entradas antes e depois da validação.

## Testes realizados
- 31 testes sintéticos em Linux local: **31 aprovados**, repetidos após conferência do blob Git publicado.
- `python -m py_compile` para ambos os arquivos: aprovado.
- Conferência dos blobs Git dos dois arquivos publicados contra os arquivos locais testados: correspondência exata.
- Nenhum vídeo real foi utilizado; não executamos a suíte integral, GitHub Actions ou testes Windows.

## Uso
```bash
python video_analyzer/offline_mc_input_contract.py resumo_visual.json cenario_manual.json nova_entrada_validada.json
python -m unittest -v test_offline_mc_input_contract
```
O arquivo `cenario_manual.json` deve conter os campos exigidos no módulo, incluindo `input_origin: "independent_manual_transcription"`, `source_summary_sha256`, `source_video_sha256_claim`, `variant`, `hero_cards`, `board_cards`, `opponents`, `seed`, `simulations`, `assumptions`, `pot_before_call`, `to_call`, `effective_stack` e `future_action_model: "showdown_equity_only"`.

## Limitações e bloqueios
A validação de schema não comprova a identidade da pessoa que transcreveu o cenário nem a presença das cartas no vídeo. O hash do vídeo no resumo ainda é uma declaração, não uma verificação visual. O contrato ainda não executa Monte Carlo, EV ou cortes MP4. Falta gravação autorizada e anotada de 3–5 minutos para validar OCR, segmentação e reconstrução visual; sessões de 40–60 minutos e Windows não foram testados.

## Próximo ciclo
Acoplar um adaptador **offline** e separado para o motor de equity existente, verificando a regra Omaha e reportando intervalos de confiança, limites de amostragem e ranges hipotéticos, sem converter revisões OCR em entradas automáticas.
