# PLO Trainee — Ciclo 251 (2026-10-31)

## Entrega publicada (somente branch `feature/plo5-plo6-training`)

- `offline_street_review_form.py`: gera `street_review_form.html` autônomo a partir de observações e relatório por street, recomputando e conferindo a origem e os hashes SHA-256 antes de publicar o arquivo.
- O formulário exige decisão explícita por evento (`confirm`, `correct`, `reject`), justificativa para alterações/rejeições e exporta `manual_review.json` com vínculo ao hash do relatório. Valores de OCR são propostas, não fatos.
- CSP desabilita conexões externas, imagens, objetos e formulários remotos. Dados textuais são inseridos no DOM via `textContent`, e JSON embutido escapa delimitadores HTML. O validador Python `offline_street_human_review.py` continua obrigatório.
- `test_offline_street_review_form.py`: 14 testes de segurança, PLO5/PLO6, JSON, integridade e fluxos de Chromium/Playwright.
- `test_offline_street_review_form_four_tables.py`: 1 teste adicional de oito eventos em quatro mesas sintéticas, download do JSON pelo Chromium e validação posterior pelo Python.

## Testes executados

54/54 testes selecionados passaram em diretório independente: 15 de formulário e integração e 39 de regressão dos módulos de evidência/revisão. FFmpeg gerou os vídeos sintéticos. O teste de quatro mesas confirmou que nenhum dado revisado autoriza automaticamente cálculos de equity/EV.

Abertura direta via `file://` **não foi validada**: o Chromium deste ambiente retorna `ERR_BLOCKED_BY_ADMINISTRATOR`. Os testes de navegador carregaram o HTML com `page.set_content` e validaram o download de JSON. Também não foram executados testes Windows, suíte integral ou vídeos reais de 40–60 minutos.

## Uso

```bash
python video_analyzer/offline_street_review_form.py VIDEO.mp4 OBSERVATIONS.json STREET_DIR EMPTY_OUTPUT_DIR
```

Abra o HTML produzido em um navegador local compatível, revise todos os eventos e exporte `manual_review.json`. Em seguida:

```bash
python video_analyzer/offline_street_human_review.py VIDEO.mp4 OBSERVATIONS.json STREET_DIR manual_review.json EMPTY_REVIEW_OUTPUT_DIR
```

## Bloqueios e próximo ciclo

Falta uma gravação autorizada e anotada de PLO5/PLO6 de 3–5 minutos para medir a precisão visual. Continuar com a ligação do histórico revisado aos clipes e um contrato explícito, sem autorização automática, para dados matemáticos condicionais a ranges. Sem mesas jogáveis, poker ao vivo, adversários de IA ou gastos.
