# PLO Trainee — referência técnica pública: PLO Mastermind (11/11/2026)

## Decisão
Usar [PLO Mastermind](https://plomastermind.com/) como **referência conceitual pública** de análises por ranges, equity, EV, diferenças entre ações, estudo por streets e relatórios, **não** como biblioteca, API ou fonte de dados. O produto mantém o escopo de [VIDEO_ANALYZER_SCOPE.md](VIDEO_ANALYZER_SCOPE.md): vídeos **gravados**, processamento offline/assíncrono e revisão de mãos. É expressamente proibido neste projeto criar mesas jogáveis, adversários de IA ou integração de jogo em tempo real.

A documentação oficial descreve soluções de quatro e cinco cartas baseadas em CFR multi-street e análise de ranges/EV. **Não** há evidência pública de uma API de acesso programático livre; a disponibilidade do PLO6 como curso não comprova um solver PLO6 equivalente.

Fontes:
- https://plomastermind.com/
- https://intercom.help/plo-mastermind/en/articles/12851145-plo-trainer-guide
- https://plomastermind.com/terms/ (21/09/2026)

## Restrições de propriedade intelectual
Os termos oficiais proíbem acesso automatizado não autorizado, scraping sistemático de ranges/soluções, reprodução para serviços concorrentes e redistribuição. Não conectar sessões, cookies, scripts, crawlers ou processos automatizados ao serviço. Não importar/capturar bancos de soluções, copiar código, interface ou materiais pagos. Nenhuma assinatura ou gasto está autorizado. Implementar os algoritmos com bibliotecas próprias ou licenças adequadas e com testes independentes.

## Mapeamento da referência para módulos independentes

| Referência pública | Implementação independente | Estágio |
|---|---|---|
| Equity e comparação de ranges | Monte Carlo PLO5/PLO6, regras exatas 2 cartas privadas + 3 board, side pots, ties, blockers e intervalos de confiança | MVP, não é solver GTO |
| EV e EV loss por ação | EV incremental de fold, call e raise, pot odds, rake, fold equity e branches de ações futuras declaradas | MVP condicionado a ranges, não GTO |
| Navegação por street | Histórico auditável, timestamps, cartas/ações visíveis e campos corrigíveis por humano | MVP |
| Classificação de erros | Diferença de EV modelado com faixa de incerteza e sensibilidade a ranges | MVP apenas após verificação |
| Categorias de mãos | Relatório de pares, suits, conectividade, blockers, nut potential, texture do board | etapa seguinte |
| CFR multi-street | Pesquisa para futuro solver independente, separada do pipeline de vídeo | fora do MVP |
| Treino multimesas interativo | **Não implementar**; quatro mesas são regiões detectadas em vídeo gravado | fora do escopo |

## Arquitetura alvo
1. **Ingestão offline:** validação, SHA-256, duração (incluindo contêineres com cauda ligeiramente >60m), trabalho por job e exclusão de arquivos conforme prazo.
2. **Extração de evidências:** FFprobe + FFmpeg, PTS decodificado e hashes por quadro, identificação de regiões (até quatro mesas) que podem aparecer/desaparecer.
3. **Visão/OCR:** cartas privadas apenas se visíveis, board, pot, ação, stack e apostas; confidência por campo. Armazenar texto bruto, ROI, frame, PTS e proposta separadamente.
4. **Reconstrução:** intervalos de mãos, mudanças de street, ações ordenadas, estados de revisão, campos desconhecidos e vínculos SHA/PTS. Nunca inventar cartas ocultas.
5. **Equity:** simulações reproduzíveis com seed, numero de iterações, amostragem de ranges de rivais, validação de duplicatas, regra Omaha correta, divisão de potes. Relatar erro de Monte Carlo e intervalos. Comparar casos conhecidos com enumeração exata onde viável.
6. **EV:** modelar explicitamente tamanho do pote antes da ação, custo adicional, rake, fold equity, ranges e linhas futuras. **Equity não é EV**. EV de call, num cenário heads-up simplificado sem rake ou apostas futuras: `E = q * P - (1-q) * C`, com `P` sendo o pote antes de pagar, `C` o custo da call e `q` equity incluindo a fração de empates; em cenários com split pots, múltiplos adversários ou rake, calcular payoffs por resultado, não usar a expressão simplificada.
7. **Seleção de clipes:** priorizar apenas decisões cuja diferença de EV permanece informativa nas hipóteses testadas; mostrar cenários alternativos. Exportar MP4 com início/fim verificáveis, nunca sobrepor explicações não sustentadas pelo vídeo.
8. **Revisão web:** upload, status assíncrono, galeria de mãos com frames vinculados, correção de campos, relatório de confiabilidade e exportação.

## Critérios mínimos antes de chamar algo de erro ou acerto
- Identificação da mesma mesa e mão confirmada visualmente.
- Cartas privadas visíveis validadas, board condizente, ação e montantes reconstituídos.
- Ranges assumidos, stacks, rake e possíveis branches explicitados, ou mostrar `INSUFFICIENT_DATA`.
- Equity com seed/iterações/intervalo de confiança e método; EV em unidade bb/fichas e sensibilidade dos ranges.
- Se decisão ótima variar materialmente conforme range/incerteza, rotular `range_sensitive`, **não** `blunder`.
- Indicar que resultado é modelo condicional; não fingir ser uma solução exata de CFR/GTO.

## Próximas tarefas verificáveis
1. Revisar amostras reais do vídeo enviado e anotar manualmente 2–5 mãos para referência; não enviar vídeo privado para GitHub.
2. Construir matriz de campo OCR: leitura, frame/ROI/PTS, valor corrigido e taxa de acerto.
3. Vincular mãos confirmadas ao motor PLO5, produzir equity com hipóteses explícitas e comparar benchmarks sintéticos.
4. Desenvolver EV de call e raise com exemplos analíticos e testes de conservação de fichas.
5. Gerar clipes MP4 completos com relatório JSON e avisos de evidência insuficiente.

Status: **documentação técnica de referência**, não validação experimental das funções nem autorização de uso dos dados proprietários do PLO Mastermind.
