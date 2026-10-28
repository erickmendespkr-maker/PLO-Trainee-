# Ciclo 165 — editor de revisão offline

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Um editor local importa `session_review.json`, permite confirmar/corrigir/marcar inconclusivas as observações e exporta `manual_annotations.json` com hash SHA-256 dos bytes de origem. Nenhuma decisão de pôquer é recomendada, nenhuma integração ao vivo é usada, e EV não é recalculado automaticamente.

O editor é independente, funciona sem servidor e não modifica os dados originais. A validação Python de `offline_human_observation_review.py` continua obrigatória. A identidade do revisor não é autenticada.

Testes locais da implementação: 7 novos (incluindo Chromium headless e integração com o validador Python usando 4 MP4 sintéticos) e 72 de regressão = 79 aprovados. O navegador do ambiente bloqueia navegação direta para `file://`, portanto o teste de interface foi feito com `page.set_content` e SHA-256 fornecido pelo harness; a abertura direta do HTML em um navegador do usuário não foi verificada.

Bloqueios: falta vídeo autorizado e anotado de 3–5 minutos para medir precisão OCR. Não foram testadas sessões reais de 40–60 minutos. Sem GitHub Actions, produção, credenciais ou gastos.
