# R3 — Estratégia, integração e desempenho PLO5 (26/11/2026)

## Entregas
- plo5_river_report_audit.py recalcula EV de cada ação, marginais, pesos de pares legais, probabilidades e certificado de melhores respostas a partir do jogo e políticas declarados. Rejeita valores adulterados, inclusive gap fictício internamente coerente. Não repete iterações CFR, não certifica GTO.
- plo5_study_report.py exige essa auditoria no relatório de river restrito. Compatível com solver convencional e acelerado; integração publicada, suíte completa deste módulo não executada no Linux por dependências indisponíveis no checkout parcial.
- plo5_review_pipeline.py e plo5_visual_report.py: links entre prints densos e explicações do relatório estratégico separado somente por igualdade de job, fonte, mesa, PTS e SHA-256 do recorte. Chaves ambíguas e prints sem decisão são ignorados. Links não comprovam mão compartilhada, histórico reconstruído nem erro estratégico. Mantém flags de não certificação.
- Testes locais: 102 selecionados (15 novos e 87 regressões), todos aprovados em 0,424 s. Núcleo matemático original recuperado, quatro hashes Git conferidos. Testes de fluxo visual usam mocks de ingestão/OCR e relatório estratégico. Outros 80 cenários sintéticos de river com variações de aposta e pesos dos ranges passaram na verificação.
- Benchmark 101 repetições do mesmo jogo polar, cache de ranking aquecido: mediana 0,208312 ms para verificar o relatório e 0,901399 ms para executar novamente o solver acelerado (4,33x). A verificação é uma operação distinta, não uma aceleração medida da análise completa de vídeo. Não inclui I/O de vídeo ou OCR.

## Limites
R3 parcial. Sem recuperação do checkout completo (DNS), gravação real ou snapshot de equity. Não medimos precisão visual, tempo total de sessão, consumo de RAM de sessão real, cobertura pré-flop/pós-flop integral, padrões recorrentes reais nem GTO externo. Nenhuma mudança de main. Preservar R1/R2 e as pendências F1–F5 e históricas. Próximo disparo R4.
