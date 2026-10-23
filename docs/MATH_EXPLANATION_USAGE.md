# PLO Trainee — explicações matemáticas estruturadas (offline)

O módulo `video_analyzer/activity_math_explanation.py` gera um **JSON lateral** que separa: (1) campos revisados manualmente, **não auditados de modo independente no vídeo**; (2) hipóteses explícitas de range e modelo; (3) resultados condicionais Monte Carlo com IC amostral; (4) avisos sobre limites do modelo. Nenhuma saída autoriza classificação de erro ou ranking automático de clipes.

## Execução

No diretório `video_analyzer/`:

```bash
python activity_math_explanation.py CLIP_MANIFEST.json CLIPS_DIR WORKSHEET.json REQUEST.json HYPOTHETICAL_REPORT.json EXPLANATIONS.json
```

O comando só cria um arquivo novo e valida os MP4 originais contra tamanho, metadados e SHA-256; verifica identidade do vídeo, mesa/mão/evento, timestamp e ação; e **reexecuta o cálculo hipotético com a semente informada**. Não modifica os MP4.

## Interpretação

`observed_review` contém entradas humanas, não fatos extraídos independentemente do vídeo. `hypotheses` registra range fornecido, semente, simulações e exclusão de rake/apostas futuras. `conditional_result` apresenta equity e EV de **call vs fold** no modelo heads-up all-in simplificado. O IC95% é apenas amostral; não mede a incerteza sobre o range, o reconhecimento das cartas, rake ou jogo futuro. Clipes sem hipótese recebem `hypotheses: null` e `conditional_result: null`. `display_card_lines` prepara texto curto para uma futura apresentação, mas **não altera os MP4 neste ciclo**.

## Testes

```bash
python -m unittest -v test_activity_math_explanation.MathExplanationTests
```

O teste usa quatro mesas sintéticas, PLO5 e PLO6, e rejeita mudanças em MP4, resultado matemático, ação, identidade e tentativas de sobrescrever o JSON. Falta vídeo autorizado de 3–5 minutos para aferir OCR/reconstrução real.
