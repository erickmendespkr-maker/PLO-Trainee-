# Ciclo 192 — auditoria offline de quadros declarados na revisão manual

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente a branch `feature/plo5-plo6-training`.

## Implementação

`offline_manual_frame_snapshot_audit.py` aceita binding da ação/ROI/clipe, MP4 local e revisão manual JSON do ciclo 191. Confere SHA-256 dos três arquivos, identidade da mão/mesa/variante/ação, confirmação de revisão, conjunto de cartas e timestamps dentro da duração real obtida por FFprobe. Extrai com FFmpeg um PNG por timestamp distinto, associa as cartas declaradas ao PNG, grava hashes SHA-256 e manifesto JSON em um diretório novo. Não sobrescreve saídas preexistentes. Falhas antes da publicação removem a pasta temporária.

Uso:

```bash
python video_analyzer/offline_manual_frame_snapshot_audit.py \
  binding.json clip.mp4 manual_review.json new_frame_audit_directory
```

O manifesto **não comprova** que as cartas declaradas estão visíveis ou corretas, que a ação pertence ao herói, nem que o timestamp solicitado é exatamente o PTS do quadro decodificado. Os PNGs são evidências para inspeção humana, não OCR validado.

## Testes locais

- 18 testes novos com MP4 sintético gerado por FFmpeg; extração real de PNG, hashes, deduplicação de timestamps e rejeições de entradas inconsistentes.
- 98 testes selecionados passaram no pacote local do ciclo 191 mais o novo módulo.
- Integração com `demo/browser_review.json`, `demo/clip.mp4` e `demo/selected_roi_clip_binding.json` do pacote anterior: 11 cartas declaradas, um timestamp distinto e um PNG exportado.
- Não foi executada a suíte integral do repositório nem a execução no Windows. Nenhum vídeo real foi usado.

## Bloqueios e próximos passos

Falta gravação autorizada/anotada de 3–5 minutos para medir reconhecimento visual. Em seguida, integrar os PNGs auditados à interface HTML e exigir revisão explícita de correspondência visual antes de classificar mãos como completas. Testar a origem real do PTS do frame, sessões longas e ambiente Windows. Não alterar produção, credenciais, `main` ou gastos.
