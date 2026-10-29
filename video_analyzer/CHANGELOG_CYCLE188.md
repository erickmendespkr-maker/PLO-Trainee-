# Ciclo 188 — vínculo de ação revisada, ROI reproduzida e clipe MP4

Escopo: análise offline/assíncrona de vídeos PLO5/PLO6, sem integração com plataformas de pôquer, decisões em tempo real, simulador de mesas ou jogadores artificiais.

## Novo módulo
- `offline_selected_roi_clip_binding.py`: recebe vídeo, configurações de mesas, artefatos de extração e OCR, revisão humana, rascunhos de mãos, timeline, fila de triagem e pacote MP4 previamente exportado.
- Reexecuta a auditoria FFmpeg vídeo → frame → ROI; reconstrói temporariamente o visualizador de evidências usando os arquivos originais; reconstrói a triagem determinística e compara o evento selecionado.
- Exige correspondência entre mão, mesa, índice da proposta, timestamp, texto de ação revisado, hash da ROI, hashes do vídeo original e do MP4, manifesto e atestado de exportação.
- Recusa saída existente, links simbólicos em entradas críticas, divergências e alegações de equity/EV validada; gera um novo JSON de vínculo com SHA-256 e ressalvas.
- Não modifica o pacote MP4 de entrada e não transmite dados pela rede.

## Testes locais
- 18 testes de contrato do novo módulo (com auditoria FFmpeg e construção do visualizador simuladas por mocks), incluindo adulteração de hashes, ação, timestamp, ROI, clipe e rejeição de sobrescrita.
- 62 testes selecionados de regressão dos módulos de replay/exportação anteriores.
- Total: 80/80 aprovados no ambiente Linux local. Os testes anteriores incluem casos que exercitam FFmpeg real, mas **o novo vínculo completo ainda não foi validado de ponta a ponta com artefatos reais coerentes**.
- O pacote demonstrativo do Ciclo 187 possui índice de ação 42, enquanto a gravação OCR sintética auditada contém apenas propostas 0–2; portanto não deve ser utilizado para declarar um vínculo positivo entre esses artefatos. A incompatibilidade deve permanecer bloqueada.

## Bloqueios
Falta vídeo autorizado e anotado de 3–5 minutos para avaliar precisão de OCR, mãos e ações. Faltam integração completa positiva com um conjunto de evidências consistente, Windows, sessão de 40–60 minutos e suíte integral do repositório. Não há equity, EV, atribuição de jogador nem validação de estratégia.

## Próximo ciclo
Criar um conjunto sintético *consistente* em que a mesma proposta OCR, revisão, timeline, triagem, ROI reproduzida e clipe MP4 pertençam à mesma mão; executar teste de integração real e teste negativo de adulteração. Depois avançar no Monte Carlo Omaha PLO5/PLO6 com parâmetros e incerteza explícitos.
