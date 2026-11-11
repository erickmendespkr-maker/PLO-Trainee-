# Ciclo 286 — 11/11/2026 — equity contra ranges ponderados explícitos

## FEITO E TESTADO
- Estado inicial da branch: `13d75b0a4c274d41f2861363b107a77b2b4487b5`. Consultados `docs/VIDEO_ANALYZER_SCOPE.md` e `docs/PLO_MASTERMIND_TECHNICAL_REFERENCE.md`.
- Criado `offline_weighted_ranges.py`: Monte Carlo PLO5/PLO6 contra lista de holdings de adversário com pesos **fornecidos explicitamente**. Rejeita cartas duplicadas, pesos inválidos, holdings repetidos por permutação, combinações incompatíveis com blockers e ranges totalmente bloqueados. Reporta fração de massa de peso rejeitada e renormalização condicional.
- A cada iteração amostra holding pelo peso condicional e board futuro sem reposição; avalia showdown Omaha usando exatamente 2 privadas + 3 comunitárias através do motor existente.
- Semente reproduzível, contagem de vitórias/empates/derrotas e intervalo Hoeffding para o **erro de amostragem condicionado ao range informado**. A incerteza do range assumido **não** está incluída no intervalo. Monte Carlo não equivale a GTO/CFR.
- Adicionada `exact_river`, que calcula média ponderada determinística no river e permite comparar cenários controlados.
- Criado `test_offline_weighted_ranges.py` com 14 testes sintéticos. **14/14 passaram localmente** usando uma cópia local compatível do motor Omaha; a versão remota exata ainda não foi executada em checkout. Os dois arquivos foram publicados no GitHub, mas seus hashes de blob não coincidem byte a byte com os arquivos locais (diferenças de apresentação). Não alegar teste remoto.
- Nenhuma alteração na `main`, produção, credenciais, custos ou integração com poker real.

## NÃO VERIFICADO
- O motor não infere ranges de OCR nem de vídeo. Não houve cálculo com mãos reais, medição de OCR ou corte MP4 neste ciclo.
- Não foram verificados CI remoto, checkout integral nem equivalência byte a byte entre arquivos testados e publicados.
- Não há modelagem de múltiplos adversários, side pots, rake, fold equity, raise EV ou incerteza epistemológica do range.

## PENDÊNCIAS MINHAS
- Reexecutar testes com o conteúdo exato publicado no GitHub, integrando regressões da árvore.
- Medir erro MC contra enumeração exata de turn e river, com benchmarks independentes.
- Revisar 2–5 mãos da gravação real e ligar holdings confirmadas ao pipeline de auditoria e cortes.

## PRÓXIMO CICLO
1. Verificar a árvore publicada e adicionar benchmark com casos exatos.
2. Adicionar modelo de EV de call condicionado à distribuição ponderada, mantendo separadas as hipóteses e a incerteza de amostragem.
3. Implementar contrato entre range, mão revisada e relatório MP4, sem atribuir ranges hipotéticos à gravação como fato.
