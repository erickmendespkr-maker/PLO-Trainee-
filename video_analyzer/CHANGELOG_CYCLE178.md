# Ciclo 178 — visualizador offline de evidências OCR vinculadas a ações

Escopo consultado: `docs/VIDEO_ANALYZER_SCOPE.md`. Apenas análise assíncrona de gravações PLO5/PLO6; sem jogo ao vivo, simulador ou integração com poker.

## Entregas

- `offline_action_evidence_viewer.py`: aceita diretório OCR com `roi_ocr_proposals.json`, relatório de revisão humana, rascunhos de mãos e linha do tempo de ações. Valida a cadeia SHA-256, os índices, as mesas, os timestamps e os valores revisados antes de copiar ROIs para um novo diretório.
- Exporta `index.html` local, `action_roi_report.json` e `assets/roi_NNN.png` (somente evidências usadas). O HTML é somente leitura, sem chamadas de rede; os textos são inseridos via `textContent`, com `<` escapado no JSON embutido.
- Recusa alteração de ROI, symlinks de entrada, caminhos de ROI não padronizados, timestamps divergentes, valores OCR fabricados, chaves JSON duplicadas, NaN, saída já existente e qualquer flag indevida de EV/ator validado.
- `test_offline_action_evidence_viewer.py`: 24 testes sintéticos, incluindo renderização Chromium, incluindo quatro mesas, proveniência e tentativas de injeção HTML.

## Execução

```sh
cd video_analyzer
python -m unittest -v test_offline_action_evidence_viewer.py
python offline_action_evidence_viewer.py OCR_DIR REVIEWED_JSON HAND_DRAFTS_JSON ACTION_TIMELINE_JSON NEW_OUTPUT_DIR
# Abrir NEW_OUTPUT_DIR/index.html localmente
```

## FEITO E TESTADO

- 135/135 testes locais aprovados: 111 regressões do Ciclo 177 e 24 novos, incluindo renderização no Chromium; reexecutados após a publicação.
- Os blobs SHA-1 Git dos dois arquivos Python publicados coincidiram com os arquivos locais testados.
- Um pacote demonstrativo sintético gerou `index.html`, JSON e imagem ROI sem alterar fontes.
- Somente a branch `feature/plo5-plo6-training` recebeu commits. Sem GitHub Actions, credenciais, produção ou gastos.

## NÃO VERIFICADO

- Precisão em vídeos reais, Windows, sessões de 40–60 minutos, inspeção visual humana da interface, e suíte completa do repositório.
- O hash SHA-256 vincula a ROI ao relatório OCR, mas este visualizador **não revalida os frames originais da gravação**. Não prova que o OCR ou a correção humana estejam corretos.
- Não identifica ator, não reconstrói sequência de apostas, não calcula equity/EV e não exporta MP4.

## PENDÊNCIA EXTERNA

Vídeo autorizado e anotado de 3–5 minutos de PLO5/PLO6 para medir precisão visual. O desenvolvimento com dados sintéticos pode continuar sem ele.

## PRÓXIMO CICLO

Revalidar também a cadeia de frames originais, integrar o visualizador ao fluxo de revisão e iniciar segmentação de clipes MP4 com FFmpeg a partir de limites humanos, sem tratá-los como limites automáticos confirmados.
