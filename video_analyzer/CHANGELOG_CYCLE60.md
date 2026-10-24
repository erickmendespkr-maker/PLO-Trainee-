# PLO Trainee — Ciclo 60 — Painel offline de triagem

Escopo: análise **assíncrona de gravações** PLO5/PLO6; não oferece mesas jogáveis, adversários de IA, integração ao vivo ou aconselhamento de apostas.

## Entregue

- `activity_triage_dashboard.py`: transforma a saída JSON de `activity_review_triage_math.py` em uma página HTML independente, sem recursos externos, com filtros por mesa, categoria e texto.
- Exibe decisões em ordem cronológica e separa **campos ausentes**, **heurística call/pote** e **intervalo amostral de equity hipotética**. Nunca converte isso em classificação de erro ou ranking por EV.
- Permite marcar itens como **examinados na fila** e exportar notas locais JSON. Essa marcação **não atesta evidência visual**, **não aprova cálculos** e **não seleciona cortes**.
- Valida schema, SHA-256 esperado opcional, identidades, cronologia, integridade sintática de hashes, filenames seguros, consistência de categorias, valores finitos e proibição explícita de autorizações automáticas.
- HTML com Content-Security-Policy restritiva, hash SHA-256 do JavaScript inline, sem rede, mídia, scripts remotos ou links automáticos para MP4. Valores dinâmicos são escapados.
- `test_activity_triage_dashboard.py`: testes de schema, segurança, determinismo, integridade, CLI e rejeição de resultados inconsistentes.

## Exemplo

```bash
python video_analyzer/activity_triage_dashboard.py triage.json triage_dashboard.html
```

O JSON de triagem deve ser previamente gerado e verificado contra os arquivos de origem pelo módulo de triagem. O painel valida a estrutura, **não** reabre vídeos nem reexecuta Monte Carlo.

## Limites e próximos passos

O reconhecimento de cartas e ações de vídeos reais continua não validado; é necessária gravação autorizada de 3–5 minutos. Nenhuma métrica sintética comprova precisão visual ou qualidade estratégica. O próximo ciclo pode ligar o painel aos cortes **somente por abertura manual explícita**, com verificação de hashes no momento da seleção, e ampliar testes de duração longa.
