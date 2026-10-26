# Ciclo 131 — busca com fallback, benchmark sintético e painel temporal

Escopo confirmado em `docs/VIDEO_ANALYZER_SCOPE.md`: revisão **offline/assíncrona** de vídeos gravados PLO5/PLO6, sem mesas jogáveis, adversários, integração com pôquer ao vivo, credenciais ou gastos.

## Implementado

- `offline_ffmpeg_seek_frame_provenance.py`: corrige falha observada com MPEG-4 e quadros B perto do fim do GOP. Um seek rápido pode saltar de 5,5 s para 5,7 s; o código detecta o PTS incorreto e usa uma segunda decodificação desde o início com seleção pelo PTS. Falha de forma conservadora se ambos os métodos não reproduzirem o frame esperado. Diagnóstico opcional contabiliza fallbacks. **Não** afirma que o seek é sempre mais rápido.
- `offline_ffmpeg_extraction_benchmark.py`: gera apenas vídeos sintéticos 160×120, mede a extração por decodificação completa versus FFprobe + seeks individuais (incluindo indexação e eventuais fallbacks), compara PTS e SHA-256 dos PNGs, rejeita divergências, e grava relatório JSON sem sobrescrita.
- `offline_clip_temporal_review_page.py`: gera HTML local sem JavaScript para revisar até 40 cortes MP4, seus relatórios temporais do Ciclo 130, alertas/indeterminações e players. Verifica SHA-256 da fonte e dos cortes, rejeita caminhos inseguros, duplicatas, symlinks, JSON com chaves duplicadas/NaN e saída preexistente. Nunca autoriza equity/EV ou dispensa revisão humana.
- Testes novos em `test_offline_ffmpeg_extraction_benchmark.py` e `test_offline_clip_temporal_review_page.py`.

## Testes locais realizados

- Python 3.13.5, FFmpeg 7.1.5; 20 testes novos aprovados.
- 84 testes selecionados aprovados, incluindo módulos anteriores de extração, seek, auditoria de duração e auditoria dos últimos quadros.
- Benchmark sintético de 12 segundos, 10 FPS, 160×120, GOP 10 e 60, quadros 5, 60 e 110: resultados variam por máquina e execução; relatório JSON acompanha o ciclo. Neste ambiente a busca indexada **foi mais lenta** que a decodificação completa nos dois GOPs. Um fallback por PTS foi registrado no GOP 10.
- Painel demonstrado com três MP4 sintéticos e relatórios do Ciclo 130: dois alertas/indeterminações temporais, zero autorização de análise estratégica.

## Limites e bloqueios

- Os tempos não representam sessões de 40–60 minutos nem resoluções reais de quatro mesas.
- O fallback de correção pode eliminar a vantagem de desempenho da busca indexada; ainda não existe seleção automática de estratégia por perfil de vídeo.
- Sem vídeo autorizado anotado, não é possível medir OCR, reconstrução de mãos, precisão de decisões, equity/EV nem cortes reais.
- Nenhum resultado heurístico comprova origem visual ou erro estratégico.

## Próximo ciclo

- Medir mais combinações de duração, codec, GOP e quantidade de quadros com repetição estatística e limites de recursos.
- Adicionar diagnóstico de uso de fallback no manifesto de extração, sem mudar contratos existentes.
- Integrar alertas temporais aos vínculos de mãos revisadas; manter análise matemática explicitamente hipotética até validação humana.
