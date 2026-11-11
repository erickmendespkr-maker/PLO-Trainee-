# PLO Trainee — Ciclo 280 — 11/11/2026

## FEITO E TESTADO
- Inspecionados `docs/VIDEO_ANALYZER_SCOPE.md`, `docs/PLO_MASTERMIND_TECHNICAL_REFERENCE.md`, a branch de trabalho e os validadores de anotações do ciclo 279 antes de escrever.
- Criado `offline_conditional_call_sensitivity.py`: estimativa independente e **condicional** de EV de call contra 2–12 hipóteses de ranges, com equidade de entrada e intervalo de confiança declarados, pot odds, EV por hipótese, direção robusta ou sensível ao range. A fórmula `EV(call)=equity*(pot_before_call+call_cost)-call_cost` aplica-se **somente** ao cenário heads-up de showdown sem rake, side pots ou apostas futuras. Fold é baseline zero. O módulo **não gera equity Monte Carlo**; recebe estimativas com semente, iterações e CI e não verifica sua procedência.
- Proibida promoção de saída hipotética a mão verificada, diagnóstico de erro estratégico, seleção automática de clipes ou GTO.
- Entradas JSON limitadas, sem chaves duplicadas ou números não finitos; hash SHA-256 de origem, sem overwrite do resultado, com gravação atômica por hardlink.
- Um protótipo local da mesma lógica foi submetido a **14 testes sintéticos, todos aprovados**, cobrindo EV +10/-10 BB em ranges alternativos, break-even 25%, IC cruzando limiar, entradas malformadas e prevenção de overwrite. O código publicado no GitHub foi reformatado, portanto **os testes da versão publicada ainda precisam ser reexecutados em CI/checkout**. O arquivo de testes correspondente também foi publicado.
- Somente branch `feature/plo5-plo6-training`; nenhum vídeo ou quadro privado enviado ao GitHub.

## NÃO VERIFICADO
- Não foi obtido acesso à gravação original neste ciclo, nem reconstrução visual de mãos reais.
- Os intervalos de confiança são os informados na entrada; não incluem incerteza do range, rake ou estrutura multiway.
- Não há ainda integração entre o validador de anotações humanas e o motor matemático. Não se afirma execução de testes remotos nem clipes MP4 novos.

## PENDÊNCIAS MINHAS
- Reexecutar a suíte sobre checkout exato da branch e adicionar exemplo de cenário JSON.
- Desenvolver interface entre mãos **independentemente verificadas** e cenário matemático; impedir uso de anotações apenas esquematicamente validadas como fatos.
- Validar vídeo autorizado com revisão visual e ground truth antes de atribuir EV a jogadas reais.

## PRÓXIMO CICLO
- Integrar proveniência de cenário ao pipeline offline de revisão sem contornar bloqueios de confiança.
- Testar casos de range-sensitive e decisão robusta em conjunto com o gerador de relatórios.
- Gerar um MP4 explicativo de exemplo **sintético** com texto que não alegue jogada real verificada.

Referência pública do PLO Mastermind é exclusivamente conceitual; sem scraping, uso de API ou dados proprietários.
