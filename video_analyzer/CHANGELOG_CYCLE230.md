# Ciclo 230 — revisão visual de evidências (offline)

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente vídeos gravados; nenhuma mesa jogável, captura ao vivo, integração com pôquer real, equity ou EV automático a partir de OCR.

## Implementado

- `offline_visual_evidence_review_ui.py`: usa a cadeia auditada OCR → reconstrução → revisão por street → auditoria de hashes/timestamps do Ciclo 229 para montar uma página HTML local e autossuficiente.
- Imagens PNG incorporadas como `data:image/png;base64`; nenhuma dependência de rede, API, servidor ou JavaScript externo.
- Revisão por mão, mesa, campo e posição; cada imagem mostra timestamp e SHA-256.
- Três avaliações: incerto, não visível, ou visível segundo o revisor. A terceira só aparece quando existe quadro vinculado.
- Exporta JSON de rascunho com hashes de proveniência, observações e comentários. O rascunho é **não autenticado** e mantém `math_ready=false`, `eligible_for_equity=0`, `equity_or_ev_calculated=false`.
- Escape de dados JSON contra quebra de `<script>`; política CSP sem conexões externas; não sobrescreve arquivo de saída; revalida o hash do PNG antes de incorporá-lo.

## Testes locais (sem GitHub Actions)

- 7 testes novos para o módulo publicado e 164 testes anteriores selecionados: **171/171** para esse conjunto.
- Foi testado adicionalmente um protótipo mais estrito, não publicado no GitHub neste ciclo, com 20 testes, totalizando **191/191** testes locais do diretório de trabalho.
- Chromium em memória: página renderizada, imagem carregada, opção selecionada, JSON baixado e validado; zero erros JavaScript.
- `file://` foi bloqueado pela política do Chromium no ambiente de testes. Isso não prova funcionamento direto no Windows.

## Bloqueios e limites

- Não existe comprovação semântica de que o valor declarado realmente aparece no vídeo: SHA-256 confirma bytes, não conteúdo visual.
- A interface de revisão não é um verificador independente; o próximo importador deverá validar seu JSON sem promover automaticamente mãos para Monte Carlo.
- Ainda faltam vídeo real autorizado/anotado de 3–5 minutos, validação OCR, processamento de 40–60 minutos, Windows e suíte integral do repositório.
