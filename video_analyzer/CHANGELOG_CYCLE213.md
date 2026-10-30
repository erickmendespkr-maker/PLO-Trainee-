# Ciclo 213 — painel offline de cortes com equity/EV condicionais

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente vídeos gravados; nenhum simulador de mesas, jogo ao vivo, login de pôquer, aposta ou integração com plataformas.

## Implementação

- `offline_reviewed_math_clip_gallery.py`: agrega **sem recalcular** a galeria de MP4 revisados e os resultados do motor Monte Carlo do ciclo 212 em `WORKSPACE/index.html` estático e offline.
- Valida novamente a fila a partir de `PLAN`, `ANNOTATIONS` e `QUEUE`; executa `offline_reviewed_math_runner.verify_results`, que confere os resultados matemáticos e hashes; valida `offline_reviewed_clip_gallery.build`, incluindo hashes de MP4 e sidecars.
- Exige correspondência exata entre hash do plano, hash declarado do vídeo, identificador da mão, mesa e timestamps de origem. Aceita que uma mão revisada não tenha corte, mas nunca associa um corte a outra mão/mesa.
- Mostra equity, IC 95% **somente amostral**, range hipotético, semente, número de iterações e EV incremental de call quando o modelo inclui seus parâmetros. Mãos bloqueadas continuam sem equity/EV.
- HTML com escape de explicações humanas, política CSP sem scripts, links relativos para os arquivos locais, `--verify` para detectar alterações na página, sem sobrescrever HTML existente.
- `build_cycle213_demo.py`: cria MP4 sintéticos com FFmpeg e valida durações com ffprobe, sem alegar reconhecimento visual de cartas.

## Testes executados localmente

Comando: `python -m unittest -q test_offline_reviewed_math_clip_gallery.py test_offline_reviewed_math_runner.py test_offline_reviewed_hand_math_queue.py test_offline_reviewed_clip_gallery.py`

Resultado: **74 testes aprovados**, dos quais **20 novos** no módulo de galeria integrada. Incluem quatro mesas, PLO6, mãos bloqueadas, discrepâncias de mesa/timestamp, hashes alterados, HTML adulterado, symlinks e injeção HTML escapada.

Demonstração adicional: `python build_cycle213_demo.py <NEW_DIR>` com FFmpeg e ffprobe: vídeo artificial de 30 segundos, dois MP4 com intervalos de 13 e 9 segundos, um resultado Monte Carlo de 120 iterações e uma mão bloqueada; geração e verificação da página concluídas.

## Limitações

- Nenhum vídeo real autorizado e anotado foi fornecido. O vídeo sintético não contém cartas, apostas nem decisões; a confiança declarada não é calibrada.
- Os MP4 são cortes por intervalos definidos manualmente. A análise não verifica as cartas contra o vídeo, não mede precisão de OCR, não avalia a qualidade de decisões reais e não modela todas as ações futuras.
- Testes no Windows, duração de 40–60 minutos e suíte integral do repositório não executados.
- Os hashes comprovam identidade dos arquivos fornecidos, não autenticidade das alegações humanas.

## Próximos passos

Validar abertura do HTML e reprodução dos MP4 no Windows; testar performance de sessões de quatro mesas; quando houver gravação autorizada de 3–5 minutos com anotações, medir OCR/segmentação e fazer revisão humana dos erros antes de habilitar qualquer análise automática de cartas.
