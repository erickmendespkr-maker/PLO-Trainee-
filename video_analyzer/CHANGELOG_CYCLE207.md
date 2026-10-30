# Ciclo 207 — índice offline de análises para a galeria

Escopo: vídeos gravados de PLO5/PLO6, revisão humana, equity e EV condicionais. Sem mesas jogáveis, bots, captura ao vivo ou integração com poker real.

## Implementado
- `offline_gallery_attachment_index.py`: lê o `manifest.json` e os sidecars dos cortes já revisados; procura exclusivamente pares `HAND.ack.json` e `HAND.ev.json` dentro da mesma pasta.
- Reutiliza `offline_reviewed_clip_gallery.build` e `analysis` para validar SHA-256 do MP4, vídeo de origem declarado, identidade da mão, variante, cartas, hash do relatório e indicadores de incerteza.
- Rejeita pares incompletos, symlinks, alterações de hash, relatórios de mãos erradas e alegações de ação observada/avaliada. Ausência dos dois relatórios significa **sem análise**.
- Cria `auto_attachments.json` somente se não existir, valida a compatibilidade com a galeria e não sobrescreve evidências.
- Não executa Monte Carlo nem produz confirmação de cartas: somente indexa arquivos já produzidos.

## Execução offline

```bash
python video_analyzer/offline_gallery_attachment_index.py clips clips/auto_attachments.json
python video_analyzer/offline_reviewed_clip_gallery.py clips clips/with_analysis.html auto_attachments.json
```

Os arquivos de análise devem ter sido gerados anteriormente, com nomes correspondentes a cada mão, como `H001.ack.json` e `H001.ev.json`.

## Testes e demonstração
- Nove novos testes unitários sintéticos e 18 testes de regressão da galeria: **27/27 aprovados** no ambiente local, sem GitHub Actions.
- Demonstração com MP4 sintético de 2,2 segundos: índice com uma análise e HTML gerados; FFprobe confirmou a duração.
- Os arquivos JSON de análise usados na demonstração são **fixtures artificiais**; seus números não resultam de uma execução Monte Carlo neste ciclo e não devem ser tratados como jogadas observadas.
- Nenhum vídeo autorizado/anotado de poker real disponível; não foram medidos OCR, detecção de mãos, precisão de cartas, processamento 1080p/30 FPS ou desempenho de sessões reais de 40–60 minutos.
- A suíte integral do repositório e a execução no Windows permanecem não verificadas.

## Próximo
Adicionar navegação entre a interface de revisão e a galeria; preparar exportação de pacotes por sessão com proveniência dos quadros, timestamps e incertezas, e validar reconhecimento com gravação autorizada anotada.
