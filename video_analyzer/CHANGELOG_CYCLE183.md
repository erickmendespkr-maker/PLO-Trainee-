# Ciclo 183 — integração replay FFmpeg + visualizador de evidências revisadas

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Apenas vídeos gravados enviados pelo usuário; sem simulador, IA adversária, conexão com poker real ou recomendações em tempo real.

## Implementado

- `offline_verified_evidence_bundle.py`: executa **de verdade** a auditoria de replay FFmpeg do vídeo → JPEG → ROI OCR antes de construir o visualizador de ações revisadas. Exige correspondência SHA-256 do relatório OCR entre auditoria e visualizador.
- Executa **segunda auditoria completa** após montar a interface e antes de publicar o diretório final; verifica também que os arquivos JSON e a origem não mudaram. Publicação por renomeação de diretório somente após sucesso; falhas deixam o destino inexistente.
- Gera `source_replay_attestation.json`, com hashes da gravação, OCR, relatório e HTML, contagens dos frames/ROIs reproduzidos e limitações explícitas. Inclui aviso no HTML: replay de mídia não significa precisão OCR, reconstrução de mãos, equity ou EV.
- Rejeita diretório de saída existente, saída dentro das evidências, links simbólicos nas entradas principais, adulteração do vídeo e PNG re-hasheado.

## Execução

```bash
cd video_analyzer
python offline_verified_evidence_bundle.py VIDEO.mp4 REGIONS.json INGEST_DIR CHANGES.json REFINED_DIR ROI_TASKS.json OCR_DIR REVIEWED.json DRAFTS.json TIMELINE.json NEW_OUTPUT_DIR
python -m unittest -v test_offline_verified_evidence_bundle
```

## Limitações

O replay exige ambiente FFmpeg compatível. O atestado é um relatório local com hashes, **não uma assinatura digital**, nem prova da autenticidade da gravação. A interface ainda depende de revisões humanas e de limites manuais. Nenhum cálculo de equity/EV é liberado. Testes com vídeos reais, Windows e sessões longas seguem pendentes. Vídeo autorizado e anotado de 3–5 minutos continua necessário para medir precisão.
