# R4 — Validação e entrega incremental PLO5 (26/11/2026)

## Entregas e verificação
- Consolidado local a partir dos pacotes F5, R1, R2 e R3, com recuperação de offline_omaha_showdown.py, plo5_rank_cache.py, plo5_evaluator.py e plo5_equity_store.py a partir de blobs já publicados. Conferidos os hashes dos quatro módulos recuperados.
- plo5_release_check.py: diagnóstico de imports em subprocessos isolados, verifica origem do módulo, falta de arquivo, dependências transitivas, erros de sintaxe e timeout. Teste de importação não equivale a execução funcional.
- instalar_revisao_windows.cmd: agora exige esse diagnóstico antes de declarar as dependências iniciais conferidas. Mantém instalação visual separada da database de equity. Scripts Windows não executados neste ciclo.
- 126 testes selecionados aprovados no Linux Python 3.13.5 (118 regressões recuperadas + 8 novos), 4,281 s; compilação dos arquivos locais aprovada. Inicialmente o pacote consolidado apresentava oito erros de importação de testes; corrigidos pela recuperação dos quatro módulos matemáticos. Os testes de interface e fluxo visual incluem fixtures/mocks.
- Auditoria matemática repetida: 7.462 assinaturas, 1.024 showdowns, 12.282 verificações de street, zero divergências.
- Diagnóstico real: 10/17 imports de entrada aprovados; 6 fontes ausentes localmente e 1 import transitivo falhou (plo5_decision_analysis). FFmpeg, FFprobe, Tesseract, Pillow e Tkinter disponíveis. Snapshot de equity não fornecido. Resultado do gate visual e estratégico: reprovado. Não declarar MVP.
- O pacote incremental consolidado não é checkout completo. O acesso ao GitHub via conector funciona para arquivos, mas DNS direto do Linux continua indisponível. O índice da pasta video_analyzer via API retorna limite de 1000 entradas; não representa inventário integral.

## Acesso e próximos passos estritamente necessários
Checkout completo: https://github.com/erickmendespkr-maker/PLO-Trainee-/archive/refs/heads/feature/plo5-plo6-training.zip (conta autorizada, repositório privado). Extraia o ZIP e execute instalar_revisao_windows.cmd, depois abrir_plo5.cmd somente se a verificação passar. Para diagnóstico estratégico com snapshot original: python video_analyzer/plo5_release_check.py --equity data/plo5_equity.sqlite --require-strategy. Não instalar pacotes externos sem revisão de origem.

A gravação real localizada em R2 (791.630.253 bytes) não foi recuperada: limite de download 268.435.456 bytes. Para testes de vídeo real, disponibilizar um trecho original de cada layout (3 e 4 mesas), com mãos completas e abaixo de 250 MB cada. Manter a resolução. Para teste integral de instalação Windows é necessário acesso ao Windows alvo. Nenhuma certificação de precisão de OCR, ganhos/perdas, mãos, estratégia GTO, desempenho de sessão de 1h ou Windows.

R1–R4 e F1–F5 permanecem parciais. Não criar outros blocos. Priorizar a execução das pendências críticas dentro do escopo PLO5 original. Sem alterações em main, deploy ou automação.
