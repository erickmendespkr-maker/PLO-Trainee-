# Ciclo — auditoria de incerteza de equity/EV (19/11/2026)

Módulo: `video_analyzer/offline_equity_ev_confidence.py`.

Após `offline_equity_ev_report.analyze(...)`, chamar
`enrich(report, pot_before_call_bb, call_cost_bb)`. Os valores de pote/call
precisam ser os mesmos usados em `analyze`; inconsistências são rejeitadas.

O intervalo de Hoeffding cobre somente a aleatoriedade IID da amostragem de
frações de pote no modelo fixo de mãos conhecidas/oponentes aleatórios.
Não mede a qualidade do range assumido, erro de OCR, identificação da mão,
seleção de street ou EV de outras linhas. Não é GTO. A classificação permanece
`REVIEW_REQUIRED`, com `video_evidence_status=NOT_VERIFIED`.

Para enumeração exata, os limites colapsam no valor de equity calculado.
Não associar o relatório a uma decisão real sem reconstrução e revisão humana.

Testes locais: 10 testes sintéticos passaram antes da publicação; os arquivos
publicados no GitHub ainda não foram executados diretamente após o commit.
A gravação real PLO5 não foi localizada no ambiente deste ciclo.
