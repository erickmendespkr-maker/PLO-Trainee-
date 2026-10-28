# Ciclo 169 — amostragem offline de vídeos com FPS baixo

Escopo: somente vídeos gravados autorizados, sem pôquer ao vivo, sem simulação de mesas jogáveis e sem recomendações de ação.

## Alterações

- Corrigida a extração de quadros próximos ao fim de gravações de 1 fps, evitando seek além do último quadro nominal.
- Acrescentado fallback de busca anterior para vídeos com FPS baixo ou irregular.
- Manifesto registra separadamente `timestamp_seconds` (alvo nominal) e `actual_frame_timestamp_seconds` (PTS decodificado por FFmpeg `showinfo` com `-copyts`), além de `seek_timestamp_seconds` e tentativas. O PTS não comprova a identidade de cartas ou ações.
- Adicionada amostragem periódica (30 s por padrão, configurável entre 5 e 120 s) além dos quadros inicial/central/final; alinhamento por FPS nominal é aproximação para VFR.
- Amostras com timestamps nominais duplicados são deduplicadas; nomes agora têm três dígitos. Diretório de saída continua atômico e somente novo.
- CLI: `python video_analyzer/offline_video_ingest_probe.py VIDEO.mp4 REGIONS.json NOVO_DIRETORIO --interval-seconds 30`.

## Testes realizados no ambiente local

- `python -m unittest -v test_offline_video_ingest_probe test_offline_ingest_sparse_fps`: **18/18 aprovados** (12 regressões + 6 novos), repetidos após publicação e hashes Git comparados com arquivos locais.
- FFmpeg/FFprobe com gravações sintéticas de 1 fps e 2 fps, duas regiões, integridade SHA-256 e PTS verificado.
- Smoke adicional: vídeo sintético de **65 segundos, 1 fps, quatro mesas**: **20 JPGs** produzidos; PTS distintos 0, 30, 32, 60 e 64 s. Nenhum OCR ou reconstrução de mão executado.
- Planejamento de amostragem de 3600 s verificado sem decodificar sessão inteira neste ciclo.

## Limitações e bloqueios

- Falta vídeo de 3–5 minutos autorizado e anotado para medir OCR e início/fim de mãos.
- A periodicidade não detecta limites de mãos nem substitui amostragem por mudanças de cena.
- A estimativa de FPS pode ser imprecisa em VFR; o PTS real é preservado no manifesto.
- Não foi testada a suíte completa do repositório, nem sessão real de 40–60 minutos, nem Windows.
- Sem GitHub Actions, custos, credenciais ou alterações na branch `main`.
