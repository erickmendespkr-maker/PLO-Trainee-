# PLO Trainee — Ciclo 93 (25/10/2026)

## Escopo e isolamento
Apenas `feature/plo5-plo6-training`. A referência é `docs/VIDEO_ANALYZER_SCOPE.md`: análise **offline/assíncrona** de sessões gravadas PLO5/PLO6, sem simulador, adversários jogáveis, integração com mesas reais ou assistência em tempo real.

## Implementação
- `hand_action_review_form.py`: cria um arquivo HTML **autocontido** para inspecionar as imagens auditadas e registrar vereditos humanos sem editar JSON manualmente. Filtra por mesa, mostra PTS e SHA-256, permite `pending`, `confirmed_visual`, `rejected_visual` e `uncertain`, e mantém `unreviewable` bloqueado.
- O formulário não faz requisições de rede; usa JavaScript local e exporta `visual_review_edited.json` pelo navegador. Uma Content Security Policy (CSP) com hash do script restringe recursos ativos; valores fornecidos pelo revisor são inseridos no DOM com `textContent`, não HTML bruto. Nomes de PNG são validados contra o padrão esperado.
- Antes de gerar HTML, a ferramenta reconstrói a galeria a partir das entradas originais e revalida as evidências, hashes e timestamps. Não sobrescreve arquivos nem grava no diretório de evidências.
- `hand_action_visual_verdicts.py`: ajuste de compatibilidade com a serialização JSON do navegador: `2.0` pode voltar como `2`. Somente o campo **numérico de PTS** protegido admite essa equivalência exata; identificadores, booleanos, SHA-256, campos de autoridade e alterações de valor permanecem protegidos.
- O JSON exportado **não é aceito como fato**: o comando `finalize` revalida os dados contra vídeo, histórico, galeria e PNGs antes de produzir o relatório. Todas as permissões de matemática e seleção automática continuam `false`.

## Uso local
Com os arquivos gerados pelos ciclos anteriores:

```bash
cd video_analyzer
python hand_action_review_form.py VIDEO.mp4 navigation.json review.json stills/ gallery/ visual_review_form.html --regions-json regions.json
# Abrir visual_review_form.html no navegador e exportar visual_review_edited.json.
python hand_action_visual_verdicts.py finalize VIDEO.mp4 navigation.json review.json stills/ gallery/ visual_review_edited.json visual_verdicts.json --regions-json regions.json
```

O HTML pode ser aberto localmente sem backend, mas **o comando Python `finalize` é obrigatório** para validar e salvar os vereditos. Preserve os PNGs na posição relativa usada na geração. Em vídeos de uma mesa, `--regions-json` pode ser omitido quando não foi utilizado nas etapas anteriores.

## Verificações locais reproduzíveis
- `python -m unittest -q test_hand_action_review_form test_hand_action_visual_verdicts` — **25 testes aprovados** (11 do formulário e 14 do módulo de vereditos).
- `node test_hand_action_review_form_js.js visual_review_form.html visual_review_edited_from_js.json` — **smoke test sintético de DOM**, 24 linhas, exportação JSON e manutenção das permissões matemáticas falsas.
- `python hand_action_visual_verdicts.py finalize ... visual_review_edited_from_js.json visual_verdicts_from_js.json ...` — **aprovado** para a demonstração sintética de quatro mesas; o teste detectou e motivou a correção da serialização numérica `2.0` → `2`.
- Navegador Chromium automatizado **não verificado**: o ambiente bloqueou tanto `file://` quanto o acesso a `127.0.0.1` com `ERR_BLOCKED_BY_ADMINISTRATOR`. O smoke test Node verifica lógica JavaScript com DOM sintético, **não** equivale a teste visual no navegador.
- Executar testes de regressão selecionados adicionais e registrar resultados separadamente. Não confundir com a suíte completa ou CI remoto.

## Bloqueios
Não foi fornecido vídeo real autorizado de 3–5 minutos com anotações de referência. Não estão verificados OCR em mãos reais, processamento integral de 40–60 minutos, nem equity/EV e cortes MP4 explicativos de ponta a ponta.

## Próximo ciclo
Vincular os vereditos finais a um histórico estruturado somente como **evidência visual revisada**, sem promover confirmação de mão completa ou liberar automaticamente cálculos. Melhorar usabilidade/validação em navegador real quando possível.
