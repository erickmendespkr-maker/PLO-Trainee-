# Ciclo 70 — Reamostragem direcionada para OCR a partir de alterações visuais

Escopo: [`docs/VIDEO_ANALYZER_SCOPE.md`](../docs/VIDEO_ANALYZER_SCOPE.md). Somente vídeos gravados, processamento offline e revisão humana; sem mesas jogáveis, captura ao vivo ou apostas.

## Entrega

`activity_roi_ocr_seek_plan.py` converte a fila de alterações visuais de regiões manuais (`activity_region_review_queue.py`) em um plano de extração de quadros **de resolução original**, aceito pelo exportador FFmpeg `activity_evidence_export.py`. Isso evita tentar ler cartas a partir das miniaturas 48×48 usadas para detectar diferenças de pixels.

O planejador confere identidade SHA-256 da gravação, hashes de proveniência da fila, contagens, limites, ranks, mesas, timestamps, rótulos e as quatro proibições de autorização estratégica. O hash canônico opcional da fila protege contra alteração posterior. Gera até cinco buscas **interiores** por candidato, deduplica tempos iguais por mesa, ordena cronologicamente e aplica limite global de 600 buscas. Quando o limite é atingido, omite o candidato inteiro em vez de produzir associação parcial. Todas as buscas permanecem hipóteses não verificadas.

**Não é um OCR novo**: usa o `activity_ocr_bridge.py` já existente para extrair e analisar recortes configurados manualmente com Tesseract. O perfil 48×48 que identifica regiões de alteração **não** deve ser reutilizado automaticamente como ROI de OCR em resolução original. Configurar ROIs para as dimensões reais de cada mesa.

## Uso offline

```bash
# 1. Criar buscas para examinar candidatos de pixels (não cartas confirmadas).
python video_analyzer/activity_roi_ocr_seek_plan.py \
  fila_roi.json sessao_gravada.mp4 buscas_ocr.json \
  --samples-per-candidate 3 --max-total-requests 600

# 2. Exportar PNGs das mesas com PTS decodificados e hashes.
# Exemplo Python (substituir retângulos pelas posições reais das mesas):
python - <<'PY'
import json
from video_analyzer.activity_evidence_export import export_activity_evidence
from video_analyzer.table_regions import Region
plan = json.load(open('buscas_ocr.json', encoding='utf-8'))
export_activity_evidence('sessao_gravada.mp4', plan, 'evidencia_ocr',
                         regions=[Region(1, 0, 0, 640, 360)])
PY

# 3. Criar roi_ocr.json com {"tasks": [{"table_id": 1,
#    "field": "board", "region": {"x": 0, "y": 0,
#    "width": 200, "height": 80}}]} (exemplo apenas).
python video_analyzer/activity_ocr_bridge.py evidencia_ocr roi_ocr.json candidatos_ocr.json
```

No passo 2, especificar **somente mesas presentes no plano** e usar regiões corretas. A API `export_activity_evidence` recusa sobrescrita. O passo 3 também não sobrescreve resultados existentes. Os candidatos OCR continuam com `analysis_status=unverified_ocr_candidates_only` e precisam de revisão humana.

## Verificações

- `python -m unittest -v test_activity_roi_ocr_seek_plan`: 12 testes sintéticos aprovados, incluindo CLI, quatro mesas, orçamento, deduplicação, rejeição de dados adulterados e integração com FFmpeg real → evidências auditadas → tarefas de OCR.
- Suíte de integração selecionada com sete módulos: 87 testes aprovados (ver `integration_tests.log`).
- A suíte completa foi iniciada, mas excedeu o tempo de execução; **não** foi declarada aprovada.

## Limites

A diferença de pixels não é carta, aposta, ação, início/fim de mão ou evidência de erro estratégico. Os PTS de origem devem ser conferidos em gravações reais; as buscas são tempos **solicitados**, não tempos decodificados. A deduplicação por timestamp não comprova amostras independentes. Sem gravação autorizada de 3–5 minutos, não há métrica real de OCR nem reconstrução de mãos verificável.
