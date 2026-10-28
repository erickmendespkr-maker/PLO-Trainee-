# Ciclo 172 — OCR offline de ROIs sobre quadros refinados

## Escopo e limites
Somente gravações PLO5/PLO6 já existentes, assíncronas e autorizadas, conforme `docs/VIDEO_ANALYZER_SCOPE.md`. Este ciclo **não** reconhece mãos automaticamente, não cria mesas jogáveis, não interage com pôquer real e não recomenda decisões.

## Implementação
- Novo `offline_refined_roi_ocr.py`: integra a cadeia SHA-256 de `offline_video_ingest_probe.py`, `offline_sampled_visual_change.py` e `offline_adaptive_change_refinement.py`.
- Aceita 1–64 tarefas de ROI escolhidas manualmente, vinculadas por SHA-256 ao manifesto de ingestão e ao relatório de refinamento. Cada tarefa identifica mesa (1–4), quadro esparso ou denso, campo (`hero_cards`, `board`, `pot`, `bet`, `stack`, `action`) e retângulo dentro da região da mesa.
- Revalida origem do vídeo, configuração das regiões, imagens esparsas/densas, índices de candidatos, timestamps decodificados e hashes antes de publicar a saída.
- FFmpeg recorta a região (`crop exact=1`) e amplia 2×; Tesseract `--psm 6 tsv` produz texto bruto e média da confiança do motor, explicitamente **não calibrada** como probabilidade de acerto.
- Gera `roi_ocr_proposals.json` e PNGs de evidência com hashes. Nenhum resultado é promovido a carta, aposta, ação, histórico de mão ou entrada de equity/EV. Todos exigem revisão humana.
- Recusa entradas com JSON duplicado, não finito, symlinks de quadros, caminhos fora do pacote, regiões fora da mesa, tarefas duplicadas, hash divergente ou diretório de saída preexistente. Não sobrescreve fontes.

## Reprodução local
Requer Python 3.11+, FFmpeg, FFprobe e Tesseract no PATH. Exemplo, a partir da pasta `video_analyzer`:

```bash
python offline_refined_roi_ocr.py recording.mp4 regions.json ingest/ changes/visual_changes.json refined/ roi_tasks.json new_ocr_output/
python -m unittest -v test_offline_video_ingest_probe test_offline_ingest_sparse_fps test_offline_sampled_visual_change test_offline_adaptive_change_refinement test_offline_refined_roi_ocr
```

Formato `roi_tasks.json`:

```json
{
  "schema_version": 1,
  "source_ingest_manifest_sha256": "<SHA-256 do ingest/manifest.json>",
  "source_dense_refinement_sha256": "<SHA-256 do refined/dense_refinement.json>",
  "tasks": [{"table_id": 1, "frame_file": "refine_000_001.jpg", "field": "pot", "roi": {"x": 0, "y": 0, "width": 220, "height": 90}}]
}
```

## Testes verificados localmente
- **23 testes novos** e **46 testes de regressão**: **69/69 aprovados** no Linux com FFmpeg 7.1.5 e Tesseract 5.5.0. Não foi usado GitHub Actions.
- Demonstração sintética de 8 segundos, 640×360, quatro regiões de mesa, 1 FPS: duas mudanças visuais refinadas; três ROIs processadas, incluindo leitura bruta **`POT 125`** em PTS 2,0 segundos, com confiança média do motor 0,930069 (não calibrada). Duas ROIs sem texto reconhecido permanecem inconclusivas.
- Testes de adulteração de vídeo, regiões, quadros e manifestos, symlinks, saída preexistente, ROIs com coordenadas ímpares e evidência com hashes.

## NÃO verificado / bloqueios
- Falta vídeo real autorizado e anotado de 3–5 minutos para medir precisão, calibrar OCR e identificar eventos reais de mãos.
- Não testado no Windows nem em sessões reais de 40–60 minutos. A suíte completa do repositório não foi executada.
- O texto do OCR não é validado como carta, valor ou ação; nenhuma inferência automática de limites de mão, equity ou EV neste módulo.
- `docs/VIDEO_ANALYZER_SCOPE.md` contém observação antiga de que não existe ingestão verificada; as implementações sintéticas dos ciclos 168–172 não substituem validação real.

## Próximo passo
Adicionar uma fila de revisão de campos OCR vinculada a quadros e PTS, com correção humana e estados de confiança separados. Somente campos confirmados podem compor rascunhos de histórico de mão, e nenhuma ação deve ser tomada ao vivo.
