# Ciclo 98 — cortes MP4 de cenários matemáticos hipotéticos (25/10/2026)

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente `feature/plo5-plo6-training`.

## Implementado

- `hand_math_clip_export.py`: ponte entre intake do Ciclo 95, cálculo Monte Carlo do Ciclo 96, relatório do Ciclo 97 e FFmpeg de cortes por região de mesa.
- Subcomando `template` produz seleção **não aprovada**: a pessoa deve confirmar regiões de mesa, cada decisão e uma nota explicativa. Não há seleção ou ranking automático por EV.
- Subcomando `export` revalida os hashes do vídeo e dos três JSON, refaz o cálculo com a semente original, rejeita mudanças, exige correspondência de mesa/intervalo/PTS e limita a 8 clipes de até 45 s.
- Recorta regiões aprovadas por FFmpeg, acrescenta um cartão explicativo de 8 s (equity, IC95 de amostragem, EV, semente, range hipotético, ressalvas e nota humana), verifica MP4 por FFprobe e produz manifesto JSON com hashes dos arquivos.
- Publicação em diretório novo, após estágio temporário; não sobrescreve artefatos anteriores. Sem captura de tela ao vivo, mesas jogáveis ou integração com plataformas.
- `test_hand_math_clip_export.py`: 21 testes novos com vídeo sintético, validação de fonte, PLO5/PLO6, quatro regiões, rejeição de dados adulterados, segurança de notas e exportação MP4 real.

## Testado localmente

- 21 testes novos: PASS (inclui FFmpeg/FFprobe e um MP4 exportado).
- 68 testes selecionados de módulo novo, relatório matemático, motor matemático, clipes e ranges: PASS.
- 34 testes em extração independente (módulo novo + relatório anterior): PASS.
- Demonstração com vídeo artificial de 5 s e quatro quadrantes: 2 MP4 com cartões matemáticos, 2 cenários não calculados. **Não é uma gravação de pôquer.**
- Execução ampliada incluindo módulos antigos de clipes: tempo excedido; **não** considerada aprovada.

## Uso

No diretório `video_analyzer/`:

```sh
python hand_math_clip_export.py template gravacao.mp4 intake.json preenchido.json math_result.json selecao_nao_aprovada.json
# Editar selecao_nao_aprovada.json: regiões, regions_human_confirmed=true,
# reviewer_approved=true em cada clip e reviewer_note explícita.
python hand_math_clip_export.py export gravacao.mp4 intake.json preenchido.json math_result.json selecao_aprovada.json nova_pasta_clipes
```

Os JSON devem ser consistentes com o mesmo vídeo local. O arquivo `hand_math_clip_manifest.json` registra hashes e timestamps. As cartas, ranges e ações continuam hipóteses informadas por humano, **não** reconhecimento verificado do vídeo.

## NÃO verificado / bloqueios

- Precisão real de OCR e reconstrução de mãos, sessões de 40–60 minutos, execução de ponta a ponta com gravação real, suíte completa e CI remoto.
- Modelo matemático simplificado heads-up all-in: sem rake, side pots, ICM ou apostas futuras. IC95 representa apenas erro de amostragem Monte Carlo.
- Ainda falta gravação autorizada de 3–5 minutos com anotações humanas de referência.

## Próximo

Validar cortes em gravação autorizada, avaliar precisão de OCR/reconstrução, desenvolver fila assíncrona de ponta a ponta e seleção humana por impacto estimado (sem diagnóstico definitivo automático).
