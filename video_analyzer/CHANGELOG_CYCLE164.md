# Ciclo 164 — registro offline de revisão humana de observações

## Escopo
Conforme `docs/VIDEO_ANALYZER_SCOPE.md`, o módulo `offline_human_observation_review.py` importa anotações manuais referentes ao relatório estático do Ciclo 163. Permite marcar cada decisão como `confirmed`, `corrected` ou `inconclusive`, preservando a observação original, o vídeo, o clipe e os relatórios matemáticos. **Não** afirma que as anotações vieram de uma pessoa autenticada; não altera a análise de EV/equity e não declara erro de poker.

## Execução
```bash
python video_analyzer/offline_human_observation_review.py \
  recording.mp4 exported_batch/ session_review.json manual_annotations.json \
  reviewed_observations.json reviewed_observations.html
```

O JSON manual deve conter exatamente `schema_version`, `source_session_review_sha256` (SHA-256 dos bytes de `session_review.json`), `reviewer_alias` e `entries`. Cada entrada contém `table_id`, `hand_id`, `decision_id`, `outcome`, `corrected_observed_action`, `corrected_action_pts_seconds` e `note`.

- `confirmed`: campos corrigidos devem ser `null`; apenas confirma a observação, **não** a qualidade da decisão.
- `corrected`: exige ação válida (`fold`, `call`, `raise`), timestamp dentro da mão, mudança real e explicação de pelo menos 10 caracteres.
- `inconclusive`: não permite correções e exige explicação; deixa a observação sem confirmação.
- Entradas não enviadas continuam pendentes. Os campos de revisão humana são declarados pelo arquivo fornecido, **não autenticados**.

## Proteções
- Vincula o JSON manual ao relatório original por SHA-256; revalida hashes da gravação e de todos os clipes.
- Rejeita identidades desconhecidas/duplicadas, timestamps fora da mão, arquivos simbólicos, caminhos inseguros, JSON com chaves duplicadas/NaN, promoção de flags de confiabilidade e saídas existentes.
- Produz novos JSON/HTML offline somente leitura, com escaping de HTML, CSP sem scripts e aviso de que a análise matemática precisa ser recalculada se a observação for corrigida.
- Não toca em `main`, produção, credenciais, rede ou integrações com plataformas de poker.

## Testes locais
- 39 testes novos de validação, integridade, segurança, correção, estados de revisão e CLI.
- 33 testes selecionados do Ciclo 163 (32 de dashboard e 1 integração real FFmpeg/FFprobe).
- Total selecionado: **72 testes aprovados** localmente. Não utilizou GitHub Actions nem a suíte completa do repositório.
- Demonstração sintética de 4 mesas: 3 anotações declaradas (confirmada, corrigida, inconclusiva) e 1 pendente. **Não são revisões humanas reais.**

## Limitações
Ainda não existe editor visual para registrar anotações no navegador. A interface HTML é somente leitura; o usuário fornece um JSON manual. Não há autenticação do revisor, verificação independente de OCR ou recálculo de EV após correção. Sem vídeo autorizado anotado de 3–5 minutos, não é possível medir precisão visual, e sessões reais de 40–60 minutos não foram validadas.