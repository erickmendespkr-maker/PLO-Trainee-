# Bloco 48 — integração do cache OCR (PLO5 offline)

- Novo plo5_singleflight.py: cache LRU exato, cópia defensiva, deduplicação de chamadas simultâneas, retry após falha, sem aproximação ou descarte de observações.
- ExactReader preserva chave de pixels, geometria, campo e ROI; delega concorrência ao SingleFlight.
- Dense timeline reutiliza OCR de ações por job, inclusive entre janelas, mantendo as observações e limites anteriores.
- Financial observations reutiliza OCR de potes e stacks na janela, mantendo a leitura de ações do timeline, reextração independente, vínculos, hashes e classificação não verificada.
- Ambos os CLIs aceitam --cache-capacity 0 para desativar a reutilização; padrão 512. Estatísticas incluem shared_inflight.

## Evidência
Linux: 6 testes unitários novos aprovados; 6 testes de renderização visual do bloco 46 repetidos e aprovados. Benchmark sintético de 120 solicitações e 3 threads, com latência artificial de 10 ms: 120 chamadas sem cache em 0,406235 s; 40 chamadas com cache em 0,408014 s, 80 reutilizações concorrentes, respostas iguais. Redução de chamadas de 66,7%, sem ganho de tempo de parede demonstrado neste ensaio. Não representa OCR real ou sessão real. O blob publicado de SingleFlight foi conferido com git hash-object local.

## Pendências
Integrações nos módulos existentes publicadas, mas ainda não executadas ponta a ponta no Linux/Windows: checkout completo, vídeos reais e snapshot SQLite ausentes no ambiente de teste. Não ligar segmentos densos a decisões do relatório esparso sem vínculo verificado. Reconhecimento de cartas e posições, reconstrução integral de mãos, settlement, ranges e solver, integração estratégica e validação real continuam pendentes. Preservar todas as pendências dos blocos anteriores, inclusive documentação do bloco 46/47 que não foi publicada. Não houve deploy, mudança em main ou alteração na automação.
