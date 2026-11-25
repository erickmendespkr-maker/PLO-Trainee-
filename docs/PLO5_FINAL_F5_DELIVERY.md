# Finalização F5 — candidato de revisão PLO5 offline (25/11/2026)

## Entrega
- video_analyzer/plo5_launcher.py: interface Tkinter para auditoria de MP4 local e execução do pacote de revisão F4. Seleção de vídeo/job, layout/janelas, saída e estudo opcional; modos quick/deep; estado da operação, log exibido ao terminar e abertura do relatório. Não é análise automática de vídeo em um clique: a revisão ainda requer job e calibração válidos.
- abrir_plo5.cmd: inicia a interface e mantém o console aberto se houver erro.
- instalar_revisao_windows.cmd: prepara ambiente virtual e Pillow 12.3.0, confere Tkinter e dependências iniciais sem exigir o snapshot de equity para a etapa visual. Não substitui instalar_windows.cmd nem a verificação estratégica original.
- Sem envio de gravações, compras, RTA, PLO6, alteração de main ou deploy.

## Uso
1. Baixe o checkout completo da branch feature/plo5-plo6-training (não apenas o ZIP incremental).
2. Instale Python 3.11+ (3.13 recomendado), FFmpeg/FFprobe e Tesseract no PATH. Execute instalar_revisao_windows.cmd; depois abrir_plo5.cmd.
3. Em audit, selecione MP4, layout JSON apropriado e pasta nova; a auditoria gera jobs.db, evidências e modelo de anotações. Use as instruções de LEIA-ME_PLO5.md e F2/F4 para preparar calibração e janelas; review requer JOB_JSON e WINDOWS_JSON conforme documentação F4. Quick/deep afeta estudo opcional, não precisão do OCR.
4. A interface não altera arquivos de entrada nem resolve automaticamente dados ausentes. Relatório HTML local. A base original de equity deve ser obtida separadamente para o motor estratégico; consultar documentação F1.

## Validação deste ciclo
- 76 testes distintos em 0,473 s no Linux, 7 novos e 69 regressões recuperadas de incrementos (inclui fixtures e mocks; não é suíte integral do repositório).
- Compilação dos arquivos Python recuperados; FFmpeg/FFprobe 7.1.5, Tesseract 5.5.0, Pillow 12.3.0, Tkinter 8.6, Python 3.13.5.
- Interface criada e visível em display virtual Xvfb, 820x570, encerrada por smoke test. Não executou uma sessão pela interface. Hashes dos dois novos arquivos Python publicados iguais aos arquivos locais.
- Clone GitHub pelo Linux falhou por DNS; preflight local detectou quatro módulos de entrada ausentes e snapshot não fornecido. Scripts CMD não executados em Windows. Pacote incremental não é checkout completo nem release certificada.

## Gate de conclusão
F1: parcial — snapshot e fontes GTO autorizadas, dependências externas e testes integrais pendentes.
F2: parcial — reconhecimento real dos assentos, cartas, ações, posições, fronteiras e liquidação/rebuy/side pots sem validação independente.
F3: parcial — solver restrito e cache implementados; falta validar integração completa, cobertura pré/pós-flop e estratégia real.
F4: parcial — fluxo candidato implementado; associação automática entre decisões e mãos reais, benchmark integral (meta 5–10 min por 1h de vídeo de quatro mesas) pendentes.
F5: parcial — interface e instaladores preparados; faltam checkout completo, sessão real de três/quatro mesas, suíte integral, Windows e teste no hardware alvo. Não certificar MVP ou publicar pacote final de produção.

Preservar as pendências históricas 11B, 13–19, 24, 27, 28, 32–35, 37–48 e F1–F5. Os cinco disparos foram executados parcialmente; os próximos trabalhos devem resolver pendências dentro desses mesmos blocos, sem novos blocos.
