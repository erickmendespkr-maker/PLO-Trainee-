# Ciclo 182 — auditoria reprodutível vídeo → frames → ROIs OCR

Escopo consultado: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente análise offline de gravações fornecidas pelo usuário; sem mesas jogáveis, integrações com poker ou decisões em tempo real.

## Implementado

- `offline_ocr_source_replay_audit.py`: auditoria **somente leitura** que verifica hashes SHA-256 da gravação, configuração de mesas, ingestão, mudanças visuais, refinamento e relatório OCR. Reexecuta com FFmpeg a extração dos JPEGs referenciados e o crop/scale dos PNGs OCR, exigindo igualdade byte a byte e PTS coincidente.
- Usa os timestamps solicitados originalmente, distingue amostras esparsas e refinadas e evita reextrair o mesmo frame para várias ROIs. Limita a 64 tarefas OCR e processa os arquivos temporários fora das evidências.
- Rejeita alterações no vídeo, ROIs, timestamps, regiões, hashes, symlinks e declarações indevidas de equity/EV. Um PNG modificado **e re-hasheado no JSON** também falha ao ser reextraído da gravação.
- `test_offline_ocr_source_replay_audit.py`: 18 testes sintéticos novos, incluindo replays FFmpeg reais, adulterações e verificação de que a auditoria não modifica evidências.

## Como executar

```sh
cd video_analyzer
python offline_ocr_source_replay_audit.py VIDEO.mp4 REGIONS.json INGEST_DIR CHANGES.json REFINED_DIR ROI_TASKS.json OCR_DIR
python -m unittest -v test_offline_ocr_source_replay_audit
```

## FEITO E TESTADO

- **87/87** testes selecionados aprovados em Linux (18 novos e 69 testes dos módulos de ingestão, amostragem, mudança visual, refinamento e OCR).
- Demonstração sintética de quatro mesas: 3 frames distintos e 3 PNGs OCR reproduzidos exatamente, com SHA-256 e timestamps conferidos.
- Os arquivos Python publicados foram comparados por blob SHA Git com os arquivos testados localmente.
- Sem GitHub Actions, alterações na `main`, credenciais, produção ou gastos.

## NÃO VERIFICADO

- A igualdade byte a byte depende da mesma versão/build de FFmpeg e bibliotecas de codec. Diferenças entre builds podem gerar falhas de replay sem adulteração. O resultado é reprodutibilidade **na ferramenta testada**, não assinatura digital ou prova de autenticidade da gravação.
- Nenhuma precisão de OCR, identificação de mãos, equity/EV, sessão real de 40–60 minutos ou Windows foi validada. A suíte completa do repositório não foi executada.

## PENDÊNCIA EXTERNA

Vídeo autorizado e anotado de PLO5/PLO6 de 3–5 minutos para validar reconhecimento visual; testes sintéticos podem prosseguir sem ele.

## PRÓXIMO CICLO

Integrar o resultado da auditoria ao visualizador offline e ao pacote de cortes MP4, mantendo as flags de análise matemática bloqueadas. Preparar seleção de decisões importantes apenas a partir de dados revisados, com hipóteses e confiança explícitas.
