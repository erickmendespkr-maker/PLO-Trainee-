# Ciclo 200 — formulário offline para hipóteses de EV

## Implementação

Novo `offline_ev_assumptions_form.py` oferece uma interface HTML estática, local e sem dependências de rede para configurar as hipóteses matemáticas do bundle do Ciclo 199. A página exporta `ASSUMPTIONS.json` compatível com `offline_acknowledged_sensitivity_bundle.py`:

- Pote atual incluindo a aposta adversária, custo do call e raise adicional.
- Grade crescente de 2 a 21 probabilidades hipotéticas de fold.
- Até cinco hipóteses nomeadas, com ranges independentes de **call** e de **raise pago** (uniforme ou combinações ponderadas), sementes e iterações independentes e probabilidade-base de fold.
- Validação local das entradas, limites e estrutura de combos, sem permitir cartas do herói, ações observadas ou alegações de reconhecimento automático no JSON.
- Confirmação explícita de que ranges/fold equity são hipóteses do revisor.

```bash
python video_analyzer/offline_ev_assumptions_form.py create NOVO_FORMULARIO.html
# Abra o HTML em navegador local, exporte ASSUMPTIONS.json
python video_analyzer/offline_ev_assumptions_form.py verify ASSUMPTIONS.json
python video_analyzer/offline_acknowledged_sensitivity_bundle.py \
  ACKNOWLEDGED_REPORT.json ASSUMPTIONS.json clip.mp4 \
  NOVO_SENSITIVITY.json NOVA_EXPLANATION.html
```

O `verify` confere esquema, limites, geometria do pote, probabilidades, duplicações, sintaxe das cartas de combos e ausência de campos de ação/cartas verificadas. **Não** verifica a validade empírica de um range nem se seus combos conflitam com as cartas revisadas; isso é avaliado pelo motor Monte Carlo ao executar o bundle.

## Testes locais executados (29/10/2026)

- 18 testes novos de validação, segurança de entradas, CLI, não sobrescrita e sintaxe JS via Node.
- 1 teste novo com Chromium/Playwright: formulário HTML carregado em memória, exportação JSON real com duas hipóteses, range ponderado, validação e rejeição de grade inválida.
- 264 testes selecionados dos módulos locais do pacote do Ciclo 199 + novos módulos, todos aprovados. Não corresponde à suíte integral do repositório.
- Integração manual adicional: JSON exportado pelo Chromium validado via CLI e utilizado no bundle com MP4 **sintético** e relatório de cartas **artificial** do Ciclo 199; foram gerados JSON de EV e HTML explicativo.
- O navegador do ambiente bloqueia navegação direta por `file://`; a execução visual com Chromium ocorreu por `page.set_content`, sem afirmar funcionamento direto em Windows.

## Limitações e bloqueios

Ranges e probabilidades não são inferidos de vídeo. Os resultados continuam condicionados às hipóteses e à confirmação humana das cartas; o modelo EV é heads-up terminal sem rake, side pots, all-in ou apostas futuras. Não há análise de ação observada, assistência em tempo real, integração com poker real, simulador jogável ou adversários de IA. A prova de conceito ainda precisa de vídeo autorizado e anotado de 3–5 minutos para medir OCR, reconstrução de mãos e confiança por campo. Sem validação com sessões reais de 40–60 minutos, Windows ou suíte integral.

Próximo: adicionar validação cruzada opcional de combos com as cartas do relatório revisado, integrar o formulário à navegação da interface offline e executar benchmark sintético de quatro mesas com timestamps de origem.
