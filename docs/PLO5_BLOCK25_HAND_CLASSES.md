# Bloco 25 — classes exatas de mãos iniciais PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_hand_classes.py valida cinco cartas distintas com _cards do núcleo de showdown. Representa cada naipe por uma máscara de 13 bits (A,K,Q,J,T,9,...,2), ordena as quatro máscaras incluindo vazias e gera class_id versionado plo5-suit-v1. Duas mãos têm o mesmo identificador se e somente se existe uma permutação global dos quatro naipes que transforma uma na outra, sem mudar ranks ou multiplicidade. Não usar isoladamente como identidade de contexto pós-flop ou de range com blockers. Retorna cartas canônicas, partição de naipes, descritor agregado e tamanho da órbita 4! dividido pelo produto dos fatoriais das multiplicidades de máscaras iguais.

enumerate_orbits() enumera máscaras por partição de cinco cartas entre até quatro naipes, combinações sem repetição dentro de cada naipe e combinações com repetição entre naipes de mesma cardinalidade. Cada órbita uma vez; 134459 classes, 2598960 mãos físicas, 83655 classes de tamanho 24, 48503 de tamanho 12, 2301 de tamanho 4. Classes por partição: ds 40053, ss 35490, 3-suit (3+1+1) 26026, 3+2 22308, 4-suit (4+1) 9295, mono 1287. Percentuais de classes não são probabilidades físicas.

audit_source(db) compara multiconjuntos de (rank_descriptor,suit_descriptor,combos) com as contagens da tabela equity. Snapshot SQLite do bloco 11 conferido pelo SHA-256 bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a antes e depois do teste. 36790 grupos em ambos, 28496 descritores, 20449 ambíguos, zero classes faltantes ou inesperadas nas contagens. A auditoria não atribui linhas individuais a classes exatas, não valida estimativas Monte Carlo da fonte e não autentica uma licença além da declaração existente. Não inventa ranking/equity exatos.

plo5_decision_analysis.py passa a reutilizar classify na consulta pré-flop e retorna hand_class separadamente das linhas agregadas. Preserva exact_suit_match=False, frequência e EV null, exclusão de estratégia sintética e verificações anteriores. Não altera a base nem a identidade dos contextos estratégicos. Exemplo As Ks Qh Jh Tc e As Qs Kh Jh Tc: ambos A-K-Q-J-T/ds, órbitas 24, IDs distintos, mesmas linhas agregadas. Troca global de naipes mantém ID; troca de naipes relativa a outros ranks pode mudar ID.

## Testes

226 testes distintos selecionados aprovados em cinco execuções: 8 novos + 11 regressões de integração (3,241 s), 78 estratégicos (0,387 s), 40 matemáticos/financeiros (5,533 s), 47 ingestão/equity (18,094 s), 42 reconhecedores (16,325 s). Nenhuma falha ou skip nesses grupos. Não é a suíte integral do repositório; mantém dois classificadores parcialmente reproduzidos no ambiente do bloco 13. Oito testes novos verificam todas as partições, invariância a 24 permutações globais e ordem, classes distintas com descritor igual, tamanho de órbita por permutações explícitas, enumeração sem duplicatas e contagem independente por Burnside, entradas inválidas, detecção de divergências e snapshot completo. PLO5_REVIEWED_EQUITY_DB aponta ao snapshot local no teste de integração. Sem ele o teste específico é ignorado. Não foram publicados o CSV nem o SQLite.

## Estado

Bloco 25 concluído para classificação matemática pré-flop PLO5 e distinção explícita de descritores agregados. Mapeamento exato da equity por classe não disponível no CSV; permanece bloqueado até obter fonte com identidade completa e autorização. Nenhuma mudança em main, deploy, automação ou dados privados. Preservar pendências 11B, 13–19 e 24; próximo bloco 26: pares, conectividade, suits, blockers e potencial de nuts com explicação descritiva sem inventar frequências.
