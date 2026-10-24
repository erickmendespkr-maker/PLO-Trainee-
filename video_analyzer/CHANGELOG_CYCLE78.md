# Ciclo 78 — recortes de navegação por mesa a partir de quadros verificados

## Entrega

- `activity_math_review_table_stills.py`: recebe o diretório de PNGs e manifesto do ciclo 77, os quatro JSONs originais (handoff, triagem, pacote e timeline), o vídeo original e a configuração de regiões. Recalcula o plano original e valida SHA-256 de cada PNG, gravação e manifesto antes de recortar.
- Suporta grades de até quatro mesas (`layout: grid`) e caixas manuais não sobrepostas (`layout: manual`), validadas contra as dimensões do vídeo. **Não detecta mesas automaticamente.**
- Usa FFmpeg para recortar cada combinação única (mesa, quadro), reutilizando o mesmo quadro completo em tarefas distintas. Verifica dimensões de entrada/saída com FFprobe e calcula SHA-256 dos recortes.
- Exporta `math_review_table_stills.json` com vínculos mesa/mão/evento, timestamps **solicitados** (PTS decodificado continua desconhecido), região e proveniência. Publicação atômica em pasta nova; rejeita sobrescrita e symlinks de arquivos de origem.
- Sinalizadores de reconhecimento, equity, EV, aprovação de clipe e erro estratégico permanecem **falsos**.

## Execução

Na pasta `video_analyzer`, após executar `activity_math_review_frames.py`:

```bash
python activity_math_review_table_stills.py sessao.mp4 quadros_revisao math_review_handoff.json math_triage.json hand_review_packet.json reviewed_timeline.json regions.json recortes_mesas
python -m pytest -q test_activity_math_review_table_stills.py test_activity_math_review_frames.py
```

Exemplo de `regions.json` para um vídeo com quatro mesas em grade 2×2:

```json
{"schema_version":1,"layout":"grid","rows":2,"columns":2}
```

Exemplo de regiões manuais (coordenadas ilustrativas, não detectadas):

```json
{"schema_version":1,"layout":"manual","regions":[
  {"table_id":1,"x":0,"y":0,"width":80,"height":60},
  {"table_id":2,"x":80,"y":0,"width":80,"height":60},
  {"table_id":3,"x":0,"y":60,"width":80,"height":60},
  {"table_id":4,"x":80,"y":60,"width":80,"height":60}
]}
```

## Limitações

Recortes de navegação não autenticam cartas, apostas ou ações. A grade só funciona se a disposição das mesas realmente corresponder às caixas; coordenadas manuais exigem inspeção humana. O tempo do quadro efetivamente decodificado não é medido. Testes usam vídeo sintético; sem gravação autorizada de 3–5 minutos não é possível medir precisão de OCR/reconstrução. Sessões reais de 40–60 minutos permanecem não verificadas.
