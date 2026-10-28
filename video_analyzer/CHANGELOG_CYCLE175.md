# Ciclo 175 — validação temporal e protótipo local de revisão

Escopo: apenas análise offline de vídeos gravados PLO5/PLO6 conforme `docs/VIDEO_ANALYZER_SCOPE.md`. Sem mesas jogáveis, integração com poker real, captura ao vivo ou gastos.

## Publicado nesta branch
- `offline_hand_temporal_consistency.py`: lê `hand_drafts.json` do Ciclo 174, exige proveniência de rascunho não reconstruído, valida cartas e timestamps e emite alertas sobre regressão do board, mudança não-prefixada, street intermediária ausente, cartas privadas alteradas, colisão de cartas e OCR inconclusivo.
- `test_offline_hand_temporal_consistency.py`: 12 testes sintéticos, incluindo a proibição de declarar equity/EV pronto.
- Saída JSON preserva SHA-256 do rascunho original e mantém `ready_for_equity_or_ev=false`.

## Protótipo local — ainda não publicado no GitHub
- `offline_hand_timeline_review.py`: relatório JSON e HTML autossuficiente, com seletor de MP4/WebM local, busca por timestamp, observações OCR por mão e exportação de anotações de limites.
- `test_offline_hand_timeline_review.py`: 22 testes, incluindo Chromium headless e exportação de JSON.
- Esse protótipo exige revisão adicional de segurança e integração antes de ser publicado.

## FEITO E TESTADO
- 52 testes locais aprovados: 18 regressões do Ciclo 174, 12 do módulo publicado e 22 do protótipo HTML local.
- Os hashes Git SHA-1 dos dois arquivos Python publicados foram comparados aos arquivos locais e coincidiram.
- FFmpeg gerou MP4 sintético de 8 s (160x90, 2 FPS); Chromium abriu o vídeo selecionado localmente e navegou ao timestamp de 4 s.
- Não utilizamos GitHub Actions.

## NÃO VERIFICADO
- Compatibilidade no Windows, suíte completa do repositório, precisão em gravações reais, processamento integral de 40–60 minutos, reconstrução automática de mãos, equity e EV em dados reais.
- O módulo publicado gera apenas avisos temporais; não transforma rascunhos em mãos verificadas.
- O protótipo HTML não foi publicado na branch neste ciclo.

## PENDÊNCIA EXTERNA
- Vídeo autorizado e anotado de 3–5 minutos para aferir segmentação, cartas, ações e OCR.

## PRÓXIMO CICLO
- Validar e publicar o protótipo HTML de revisão; criar importador validado para anotações exportadas e ligação segura com os limites de mãos.
- Expandir a validação temporal das ações e apostas sem inferir decisões ou EV quando faltarem dados.
