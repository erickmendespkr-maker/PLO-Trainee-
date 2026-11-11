# Ciclo 283 — 11/11/2026 — vínculo auditável de anotações e EV hipotético

## FEITO E TESTADO
- Consultado HEAD inicial da branch `feature/plo5-plo6-training`: `98f91c5d4bc8470e51a723f6eef3a8b96bf79167`. Revisados `docs/VIDEO_ANALYZER_SCOPE.md` e `docs/PLO_MASTERMIND_TECHNICAL_REFERENCE.md`.
- Criado `offline_math_evidence_gate.py`: vincula **uma alegação humana de call** (PLO5/PLO6, mesa, intervalo, cartas e pote) a um cenário de EV **hipotético**. Exige que o pote e o custo do call coincidam numericamente, que as cartas não se repitam e que o cenário passe pelo módulo existente `offline_conditional_call_sensitivity.compute`.
- Produz JSON com SHA-256 dos arquivos de entrada, SHA declarado do vídeo, parâmetros de cenário e resultado EV. Todos os flags de confirmação estratégica permanecem `false`. Nenhum vídeo é aberto pelo gate, portanto o vínculo **não** prova que as cartas, o pote ou o range aparecem na gravação.
- Desenvolvido protótipo local e executados **17/17 testes sintéticos aprovados**, incluindo casos negativos de divergência de pote/call, cartas duplicadas, variantes PLO5/PLO6, flags indevidas, JSON malformado, valores booleanos, sobrescrita e ambiguidade de mãos.
- Publicados módulo e suíte de 17 testes na branch autorizada. **A versão exata publicada não foi reexecutada em checkout GitHub**; os testes locais usaram uma cópia local da interface `compute` do módulo existente. Não declarar CI ou validação integral da árvore.
- No ambiente está disponível `/mnt/data/23-25-30(1).rar` (RAR5, aproximadamente 203 MB), mas não há extrator RAR instalado. Não foi extraído nem processado; não publicar gravações ou quadros privados no GitHub.

## NÃO VERIFICADO
- A gravação real PLO5 não foi extraída nem revisada neste ciclo. Não houve reconstrução visual de mãos, medida de OCR, Monte Carlo de uma mão real, nem novos cortes MP4.
- O gate valida **consistência de alegações** e parâmetros, não a veracidade das cartas ou a origem das equities. Os intervalos de confiança permanecem condicionais aos ranges fornecidos.
- A versão publicada e a integração completa no checkout remoto ainda precisam de execução independente de testes; não houve CI remoto.

## PENDÊNCIAS MINHAS
1. Conseguir acesso de leitura ao MP4 dentro do RAR por extrator RAR5 disponível, sem alterar o arquivo original.
2. Revisar manualmente 2–5 mãos, com PTS, mesa, cartas, board, ações e apostas confirmados em quadros; construir referência humana para acurácia de OCR.
3. Integrar a saída auditável com o compositor MP4 e bloquear classificações de erro estratégico enquanto faltar confirmação.
4. Testar os arquivos publicados diretamente em checkout da branch, incluindo regressões.

## PRÓXIMO CICLO
- Testar a nova interface do gate com `offline_review_queue_annotations.validate` e ampliar contratos de proveniência por campo/PTS.
- Se houver extrator RAR5, extrair apenas a gravação autorizada para ambiente privado e iniciar revisão de mãos; caso contrário avançar com testes sintéticos e integração offline.
- Implementar cálculo de equity PLO5/PLO6 com regras exatas de duas cartas privadas e três do board, verificando casos conhecidos e incerteza; não chamar Monte Carlo de GTO.

Nenhuma alteração em main, produção, credenciais ou gastos. PLO Mastermind é apenas referência conceitual pública.
