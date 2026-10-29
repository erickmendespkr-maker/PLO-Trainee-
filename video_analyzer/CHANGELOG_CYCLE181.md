# Ciclo 181 — auditoria independente de pacotes MP4 revisados

Escopo consultado: `docs/VIDEO_ANALYZER_SCOPE.md`. Exclusivamente análise assíncrona de vídeos enviados pelo usuário; sem mesa jogável, assistência em tempo real ou integração com pôquer online.

## Implementado na branch `feature/plo5-plo6-training`

- `offline_clip_artifact_audit.py`: auditoria **somente leitura** dos cinco artefatos gerados pelo pipeline do Ciclo 180: `manifest.json`, `gate/request.json`, `gate/provenance.json`, `clip.mp4` e `clip.mp4.json`.
- Compara hashes SHA-256 do MP4, requisição, proveniência e sidecar; confere IDs da mão/mesa, hash declarado do vídeo original, timestamps e crop.
- Executa FFprobe independentemente para validar dimensões, duração e ausência de áudio. Opcionalmente compara o SHA-256 com o vídeo original informado por `--source-video`.
- Rejeita arquivos ausentes, symlinks diretos, chaves JSON duplicadas, NaN, adulterações e flags que declarem equity, EV ou vínculo OCR-vídeo como verificados.
- Retorna `bundle_integrity_verified_only`, nunca `poker_hand_verified`.
- `test_offline_clip_artifact_audit.py`: 16 testes sintéticos, incluindo geração real de MP4 com FFmpeg e integração com `offline_reviewed_clip_pipeline.py` publicado.

## Execução

```sh
cd video_analyzer
python offline_reviewed_clip_pipeline.py VIDEO.mp4 drafts.json boundary_review.json H1 crop.json NOVO_DIRETORIO
python offline_clip_artifact_audit.py NOVO_DIRETORIO --source-video VIDEO.mp4
python -m unittest -v test_offline_clip_artifact_audit test_offline_clip_review_gate
```

## FEITO E TESTADO

- 16 testes novos de auditoria + 16 testes selecionados do gate anterior: **32/32 aprovados** em ambiente Linux local com FFmpeg/FFprobe.
- Teste end-to-end: MP4 sintético de 4 s; clipe exportado de 2 s (160×120) na suíte de testes; além de pacote demonstrativo de quatro quadrantes de 6 s com recorte de 320×180 e 2 s.
- Os blobs Git dos dois arquivos Python publicados coincidiram com as cópias locais executadas.
- Não foi usado GitHub Actions; nenhuma alteração na `main`, em produção ou em credenciais; nenhum gasto.

## NÃO VERIFICADO

- Hashes SHA-256 demonstram **consistência**, não autenticidade contra alguém que altere todos os arquivos e recalcule os hashes. Não há assinatura digital.
- O vídeo original não está criptograficamente associado à fonte do OCR. Nenhuma mão real, precisão OCR, equity, EV ou qualidade de decisão foi validada.
- Não houve teste Windows, sessões reais de 40–60 minutos nem suíte integral do repositório.

## PENDÊNCIA EXTERNA

Gravação autorizada e anotada de PLO5/PLO6 de 3–5 minutos para aferir reconhecimento visual. Testes sintéticos independentes podem continuar.

## PRÓXIMO CICLO

Criar vínculo verificável entre o vídeo de origem e as imagens/ROIs usadas pelo OCR, sem atribuir confiança matemática a observações não revisadas; depois integrar a auditoria à interface de revisão de cortes.
