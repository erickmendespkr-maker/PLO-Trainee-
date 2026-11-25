# F1/F3 — referências GTO e solver restrito PLO5 (25/11/2026)

## Entregas
- plo5_cfr_restricted.py: núcleo original de regret matching convencional e variante inspirada em CFR+ (regret flooring, média linear, atualizações simultâneas), parada por gap entre melhores respostas. Usa pares legais ponderados preparados pelo modelo HU river existente, sem alterar o solver de produção. Sem rake, check termina em showdown, uma aposta fixa, fold/call, sem árvore completa.
- plo5_restricted_cache.py: SQLite separado para reaproveitar políticas de matriz ponderada e configuração idênticas; valida novamente probabilidades, parâmetros e gap. Somente grava políticas que atingem a meta. Não armazena dados de fornecedores nem certifica GTO completo.
- 12 testes unitários aprovados no Linux Python 3.13.5 em 0,013 s. Quatro blobs publicados conferidos com git hash-object local. Adaptador solve_prepared e integração ao fluxo de evidência ainda não executados ponta a ponta.

## Benchmark analítico (não vídeo real)
Jogo polar: duas mãos do Hero e uma do adversário, massas 1/3 e 2/3, aposta pot. Valor teórico 0,5 do pote. Meta gap <= 0,01 do pote. Sete repetições:
- CFR convencional: 1750 iterações; mediana 0,003517812 s; gap 0,0099028600.
- Variante CFR+: 300 iterações; mediana 0,000768291 s; gap 0,0097264072.
Não generalizar este ganho a árvores maiores, multiway ou sessões reais. Nenhuma frequência de solver externo importada.

## Fontes externas e próximos passos
- https://github.com/jejellyroll-fr/poker-eval — documentação de árvores HU PLO5 por street e árvore completa restrita, ferramentas de exportação CFR. LICENCE histórico GPLv3+ e LICENSE para material mais recente; revisar escopo por componente antes de incorporar. git ls-remote falhou por DNS no Linux. Compilação e validação diferencial pendentes.
- https://github.com/nicoseijas/gto-research — metodologia pública, engine privada, textos CC BY 4.0 e exemplos MIT. Aproveitados conceitos de regret flooring, média linear e comparação por qualidade; código novo independente.
- https://hydraviewer.com/packs — amostras gratuitas PLO5 disponíveis para estudo. https://hydraviewer.com/terms exige autorização de uso em ferramenta de estudo; pedir licença a support@hydrasolver.com antes de importar. Nenhum pack adquirido/importado.
- https://solvepoker.app/methodology — estratégias Monker distintas do CSV de equity CC BY 4.0. Não supor licença de estratégias a partir da licença do CSV.

Manter a base estratégica de produção fechada a dados não autorizados; o strategic_store atual aceita apenas fixtures sintéticos. Cache novo é separado e experimental. Preservar F1 parcial, F2 próximo, F3 parcial e todas as pendências anteriores. Sem compras, alterações em main, automação ou deploy.
