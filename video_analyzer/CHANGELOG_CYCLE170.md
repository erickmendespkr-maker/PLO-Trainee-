# Ciclo 170 — triagem conservadora de mudanças visuais por mesa

Escopo: análise offline/assíncrona de gravações autorizadas PLO5/PLO6, sem pôquer ao vivo, simulação de adversários ou recomendações de ação.

## Implementação

- Novo `offline_sampled_visual_change.py`: consome o `manifest.json` e os JPEGs gerados por `offline_video_ingest_probe.py` sem alterar os arquivos originais.
- Confere SHA-256 de cada JPEG, rejeita caminhos inseguros, links simbólicos, manifestos com chaves JSON duplicadas e amostras malformadas.
- Usa FFmpeg para converter cada recorte amostrado em imagem de 32×32 pixels em escala de cinza e calcula diferença absoluta média e fração de pixels alterados.
- Produz intervalos delimitados por timestamps **PTS efetivamente decodificados**, separadamente para cada mesa (até quatro), com indicação de lacunas temporais e timestamps repetidos.
- Gera `visual_changes.json` em diretório novo, via staging atômico. Cada ocorrência é apenas uma **mudança visual não localizada**, sujeita a revisão humana. O campo `hand_boundary_confidence` permanece `null`; não se afirma início/fim de mão, cartas, ações ou equity.
- CLI: `python video_analyzer/offline_sampled_visual_change.py DIRETORIO_INGESTAO NOVO_DIRETORIO_SAIDA`.

## Testes locais

- `python -m unittest -v test_offline_sampled_visual_change test_offline_video_ingest_probe test_offline_ingest_sparse_fps`: **31 testes aprovados**, 13 novos e 18 regressões.
- Integração real FFmpeg/FFprobe com vídeo sintético de 6 s, duas mesas: mudança intencional detectada apenas na mesa 1.
- Demonstração adicional: vídeo sintético de 8 s, 1 fps, quatro mesas: 12 JPEGs e **dois intervalos candidatos**, nas mesas 1 e 4; mesas 2 e 3 permaneceram estáveis.
- Casos de teste: integridade SHA-256, arquivo ausente/adulterado, symlink, traversal, JSON duplicado, parâmetros inválidos, saída existente, PTS repetido e intervalos esparsos.

## Limitações e bloqueios

- **Não** há reconhecimento de cartas, ações, início/fim de mãos ou precisão calibrada. O indicador de força do sinal é heurístico e não probabilidade de mão.
- Amostragem de 30 segundos pode deixar mudanças sem observação; o intervalo entre quadros não é instante exato do evento.
- Falta vídeo autorizado e anotado de 3–5 minutos para medir falsos positivos, falsos negativos e ajustar limiares por layout.
- Não foram executados a suíte completa do repositório, processamento real de 40–60 minutos ou testes Windows. Não utilizar GitHub Actions.
- Nenhuma alteração em `main`, produção, credenciais ou custos.
