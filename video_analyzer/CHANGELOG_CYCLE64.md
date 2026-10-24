# Ciclo 64 — intervalos entre mãos -> buscas FFmpeg para revisão

**Escopo:** somente análise assíncrona de gravações PLO5/PLO6. Não captura mesas ao vivo, não joga, não aposta, não cria adversários de IA.

## Entrega

- `activity_boundary_seek_plan.py`: conecta `activity_hand_boundary_review.py` ao extrator existente `activity_evidence_export.py`.
- Exige relatório com `review_only_candidate_inter_hand_windows`, bloqueios de EV/seleção automática e SHA-256 da gravação igual ao vídeo local efetivo.
- Preserva os hashes de proveniência da linha do tempo e do relatório de revisão, sem tratar hashes como prova da correção das anotações humanas.
- Sugere até cinco *requested seeks* estritamente dentro de cada intervalo positivo entre mãos **identificadas por um humano**. Intervalos sobrepostos/sem largura não geram buscas.
- Limites explícitos: até quatro mesas e 600 solicitações no total. Em excesso, falha sem truncar silenciosamente; rejeita parâmetros inválidos, identidade divergente, contagens inconsistentes, janelas falsas e tentativas de autorizar EV/erros.
- JSON resultante é compatível com `export_activity_evidence()`. O extrator produz PNGs e timestamps PTS efetivamente decodificados, podendo ser posteriores ao instante solicitado.
- Nenhuma janela se transforma em limite exato de mão; nenhum corte ou cálculo é autorizado por este adaptador.

## Exemplo de execução offline

Execute a partir de `video_analyzer/`, com uma gravação **autorizada** e relatório gerado por `activity_hand_boundary_review.py`:

```bash
python activity_boundary_seek_plan.py boundaries.json gravacao.mp4 boundary_seeks.json
python activity_evidence_export.py gravacao.mp4 boundary_seeks.json evidence_boundary_frames
```

O segundo comando exige que a gravação seja a mesma usada no relatório e que os tempos estejam dentro da duração. Audite `evidence_boundary_frames/manifest.json` e os PNGs antes de usar os dados em OCR. Para provas de identidade mais fortes, use `--expected-review-sha256` com hash canônico de relatório confiável.

## Verificação local desta entrega

- 19 testes novos de unidade/integração aprovados, incluindo FFmpeg real com vídeo sintético de quatro mesas.
- 80 testes de regressão selecionados aprovados.
- Suíte completa local: **853 testes aprovados**, 0 falhas (78,737 s).
- Demonstração sintética de 9 s: 4 janelas de revisão, 12 seeks, 12 PNGs, 12 PTS associados e auditoria SHA-256 aprovada.
- Não foi utilizada gravação de poker real. Precisão de OCR, limites reais das mãos e desempenho de vídeos longos **não foram avaliados**.

## Próximo passo

Associar cada PNG auditado a sua janela de revisão e fornecer prévias visuais para correção humana. Não permitir que quadros posteriores à decisão sejam usados como informação disponível no momento da decisão.
