# Ciclo 168 — pré-ingestão offline e amostragem de até quatro mesas

Escopo consultado: `docs/VIDEO_ANALYZER_SCOPE.md`. O novo módulo `offline_video_ingest_probe.py` usa FFprobe para validar um vídeo gravado MP4/WebM/MOV/MKV e FFmpeg para gerar quadros de amostra por região de mesa, sem conexão com sites de pôquer ou captura ao vivo.

## Entregas

- Rejeita mídia sem vídeo único, duração fora de 0,5–3.600 s, resolução acima de 3840×2160, arquivo acima de 30 GiB, extensões não permitidas e links simbólicos diretos.
- Exige JSON explícito com 1–4 regiões retangulares, IDs únicos, dimensões dentro do quadro, coordenadas pares e regiões sem sobreposição. Não detecta automaticamente as mesas.
- Extrai até três quadros JPEG por mesa (início, meio e fim), registra timestamp, tamanho, dimensões, hashes SHA-256 do vídeo, configuração e cada imagem.
- Produz `manifest.json` e imagens em **novo** diretório, após revalidar os hashes das entradas. Não altera gravações, não realiza OCR nem infere cartas, mãos, ranges ou EV.

## Testes locais verificáveis

- 12/12 testes `unittest` aprovados novamente após publicação dos dois arquivos Python. Os Git blob SHAs remotos coincidiram com os hashes Git locais.
- Integração real FFmpeg/FFprobe: vídeo sintético de 2 s, 640×360, quatro regiões de 320×180, 12 JPEG com dimensões e SHA-256 conferidos.
- Smoke test separado: vídeo artificial de 2.400 s (40 min), 320×180, 5 fps, quatro regiões e 12 JPEG gerados. Smoke test separado de 3.600 s (60 min), mesmas condições, também concluiu com 12 JPEG.
- Testes negativos: configuração inválida, IDs duplicados, sobreposição, coordenadas ímpares, links simbólicos, sobrescrita e adulteração simulada durante extração.

## Limitações e bloqueios

- **Não** é um pipeline completo de análise: não detecta mesas, não segmenta mãos, não faz OCR, equity/EV, nem cortes de decisões.
- Os testes de 40–60 min foram feitos com vídeo artificial de 320×180 e 5 fps; não validam desempenho em vídeo real, alta resolução ou quatro mesas reais.
- Amostragem perto do fim usa `duration - 0.25s`; vídeos com FPS muito baixo (por exemplo 1 fps) podem não possuir quadro nesse instante. Adaptar à cadência dos quadros no próximo ciclo.
- O tamanho máximo de 30 GiB é um limite inicial de proteção, não dimensionamento de armazenamento ou memória em produção.
- Falta gravação autorizada e anotada de PLO5/PLO6 de 3–5 min para medir reconhecimento visual. Não executar GitHub Actions, não alterar `main`, produção ou credenciais.

## Exemplo

```bash
python video_analyzer/offline_video_ingest_probe.py \
  recording.mp4 regions.json new_ingest_directory
```

Exemplo de configuração:

```json
{"tables":[{"table_id":1,"x":0,"y":0,"width":320,"height":180}]}
```
