# Ciclo 226 — reconstrução diagnóstica de mãos OCR (sem cálculo)

## Entrega
- Novo `offline_ocr_hand_reconstruction.py`: lê o ledger produzido pelo importador do ciclo 225 e agrupa candidatos por mão, mesa, slot, campo e timestamp.
- Preserva evidência alegada por quadro (SHA-256, PTS e confiança OCR bruta) sem autenticar a origem nem promover cartas a fatos.
- Detecta candidatos divergentes no mesmo slot, cartas repetidas em slots diferentes, variantes PLO5/PLO6 conflitantes, cartas privadas incompletas, flop incompleto, lacunas de street e ausência de ações/pote.
- Correções textuais permanecem separadas das sugestões aceitas. O resultado é **sempre** `math_ready=false`, `eligible_for_equity=0` e `equity_or_ev_calculated=false`, mesmo com cartas aparentemente completas.
- Entrada e saída são arquivos JSON locais; não há captura de mesa, API de poker, simulador ou execução de Monte Carlo.

## Uso
```bash
python video_analyzer/offline_ocr_hand_reconstruction.py \
  LEDGER_DO_CICLO225.json NOVO_RELATORIO.json
```

## Testes verificados localmente
- 27 testes novos sintéticos e 43 testes de regressão dos ciclos 224/225: **70/70 aprovados**.
- Teste separado com 100 mãos, quatro mesas e 6.000 observações sintéticas: geração em aproximadamente 0,026 segundo no ambiente local; não mede OCR nem vídeo.
- Demonstração: quatro mãos, quatro mesas, quatro candidatos aceitos, zero mãos liberadas para matemática.
- Não foram executados GitHub Actions, suíte integral, Windows nem gravações reais de 40–60 minutos.

## Bloqueio e próximo passo
- Falta vídeo autorizado e anotado de PLO5/PLO6 de 3–5 minutos para medir precisão visual.
- Próximo passo: interface de reconstrução com revisão humana independente por mão e street, e preparação de anotações explícitas para o motor matemático já existente. O ledger OCR sozinho nunca deve habilitar equity/EV.
