# Ciclo 171 — refinamento temporal offline de mudanças visuais

## Escopo
Conforme `docs/VIDEO_ANALYZER_SCOPE.md`: análise exclusivamente assíncrona de vídeos autorizados PLO5/PLO6. Sem mesas jogáveis, integração ao vivo ou recomendação de apostas.

## Implementação
- `offline_adaptive_change_refinement.py` recebe vídeo original, regiões, manifesto de ingestão e relatório de mudanças do ciclo 170.
- Valida SHA-256 da fonte, configuração de regiões, manifesto e imagens amostradas; rejeita referências inconsistentes, symlinks de entrada e sobrescrita da saída.
- Reamostra somente intervalos candidatos, alinhando timestamps ao FPS nominal quando disponível; PTS efetivo é registrado.
- Calcula diferenças em escala de cinza entre quadros e registra subintervalos onde ocorreu uma mudança visual, sem inferir limites de mãos.
- Exporta JPEGs adicionais e `dense_refinement.json` em diretório novo com publicação atômica.
- Limites: no máximo 64 intervalos, 60 segundos por intervalo, 1024 quadros novos e passo de 0,25 a 5 segundos.

## Demonstração sintética
- Gravação artificial de 8 segundos, 1 FPS, resolução 640×360, quatro regiões.
- Detector esparso identificou duas mudanças (mesas 1 e 4).
- Refinamento acrescentou cinco quadros (3+2) e reduziu os intervalos visuais de [0,4] para [1,2] segundos na mesa 1 e de [4,7] para [4,5] segundos na mesa 4.
- Esses intervalos não representam limites de mãos de pôquer.

## Verificação
- 15 testes novos, cobrindo integração FFmpeg, dados adulterados, timestamps inválidos, limites, hashes, chaves JSON duplicadas e falhas seguras.
- 31 testes de regressão dos módulos de ingestão e mudanças visuais.
- 46 testes selecionados aprovados no ambiente local, sem GitHub Actions.
- Arquivos de código e testes publicados devem ser conferidos por hash Git e testes locais após a publicação.

## Limitações e bloqueios
- Não há gravação real anotada para calibrar OCR, detecção de ações, identificação de mãos ou acurácia de intervalos.
- Reamostragem visual pode não detectar mudanças sutis, animações, overlays ou eventos entre quadros; o valor de confiança de limite de mão permanece nulo.
- Não há teste completo com vídeo real de 40–60 minutos nem suíte completa do repositório.
- Não foram feitos gastos nem alterações em produção, credenciais ou `main`.
