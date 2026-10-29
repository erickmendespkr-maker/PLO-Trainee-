# Ciclo 187 — source-replayed triage clip (offline)

## Escopo

Novo módulo `offline_source_replayed_triage_clip.py`: audita a cadeia de mídia vídeo original → JPEG → ROI PNG via FFmpeg, executa a exportação de um clipe MP4 de ação triada com limites revisados manualmente e repete a auditoria antes de publicar um diretório novo. Nenhuma mesa jogável, assistência em tempo real, integração com poker, IA adversária ou uso de credenciais.

## Comando

```bash
python video_analyzer/offline_source_replayed_triage_clip.py \
  VIDEO.mp4 REGIONS.json INGEST_DIR CHANGES.json REFINED_DIR TASKS.json OCR_DIR \
  DRAFTS.json BOUNDARY_REVIEW.json CROP.json TIMELINE.json TRIAGE.json \
  HAND_ID PROPOSAL_INDEX NOVO_DIRETORIO
```

O pacote contém `reviewed_clip/clip.mp4`, os arquivos já existentes do exportador (gate, sidecar, manifesto e link da triagem) e `source_replay_clip_attestation.json`. O diretório é publicado apenas após duas auditorias e conferência dos hashes SHA-256. Uma falha deixa o diretório de saída ausente.

## Limites de confiança

A auditoria comprova reprodutibilidade dos pixels da mídia **no ambiente FFmpeg usado**, e que o clipe veio do mesmo arquivo de vídeo. **Não** comprova que a ação da fila corresponde a um ROI específico: o histórico OCR revisado ainda não possui vínculo criptográfico de cada evento ao ROI reproduzido. Também não valida texto OCR, jogador, cartas, mãos, equity, EV, ranges ou qualidade estratégica. Os relatórios registram esses limites como `false`.

## Testes locais (ambiente Linux)

- 24 testes unitários novos com casos de falha e integridade.
- 20 testes de regressão do exportador de triagem e 18 da auditoria de origem (62/62 aprovados no conjunto selecionado).
- Demonstração de integração real com gravação **sintética** de quatro regiões, oito segundos, reextração exata de três frames e três ROIs e exportação de MP4 da mesa 4, mão H4, proposta 42. O clipe e seu hash foram verificados.
- Não houve teste no Windows, gravação real, sessão de 40–60 minutos ou suíte integral do repositório. A tentativa da suíte ampliada excedeu o tempo disponível e não deve ser tratada como aprovada.

## Próxima etapa

Vincular cada evento da fila de triagem a `proposal_index`, `roi_png_sha256` e origem OCR revisada, com validação ponta a ponta. Só depois habilitar cálculo matemático de mãos realmente reconstruídas com ranges e confiança explícitos.

## Bloqueio

Falta gravação autorizada e anotada de 3–5 minutos de PLO5/PLO6 para medir acurácia do reconhecimento.
