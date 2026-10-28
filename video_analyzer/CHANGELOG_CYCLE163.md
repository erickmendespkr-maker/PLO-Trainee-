# Ciclo 163 — pacote de revisão offline (HTML + JSON)

## Escopo
Conforme docs/VIDEO_ANALYZER_SCOPE.md, o módulo offline_session_review_dashboard.py transforma a fila de EV hipotético do Ciclo 162 em relatório local somente leitura. Não seleciona clipes automaticamente, não recomenda jogadas, não valida OCR ou ranges, não captura mesas e não integra plataformas de pôquer.

## Implementação
- Recebe gravação local, diretório de clipes MP4 previamente exportados, JSON de prioridade e dois novos arquivos de saída: JSON e HTML.
- Confere hashes SHA-256 da gravação, prioridade e clipes; valida mídia com FFprobe (vídeo, resolução, duração), timestamps, identidade da mão/mesa e flags conservadoras.
- Rejeita JSON com chaves duplicadas/NaN, symlinks, caminhos inseguros, MP4 adulterados, inconsistências de duração, identidades duplicadas e promoção de decisões a erros comprovados.
- Gera HTML estático com player de vídeo local, timestamps, intervalos condicionais de EV, hipóteses de ranges e avisos. Sem scripts, bibliotecas externas, autoplay ou acesso à rede. Escapa HTML fornecido pelos relatórios.
- Saídas novas e sem sobrescrita. Mantém os MP4 e relatórios originais intactos.

## Uso
    python video_analyzer/offline_session_review_dashboard.py recording.mp4 exported_batch/ manual_review_priority.json session_review.json session_review.html

Abra session_review.html no navegador local, mantendo exported_batch/ como pasta irmã. A página é somente leitura; não persiste decisões humanas.

## Testes locais executados
- 32 testes novos de segurança, integridade, campos, HTML e FFprobe.
- 1 teste de integração real FFmpeg: vídeo sintético 640×360, quatro cortes 320×180, priorização do Ciclo 162 e geração de HTML/JSON.
- 34 testes de regressão do Ciclo 162 e 39 do Ciclo 161.
- Total: 106 testes selecionados aprovados. Sem GitHub Actions. A suíte completa do repositório não foi executada.

## Limitações
A demonstração usa vídeo de padrão de teste, sem cartas ou jogadas reais. A integridade dos arquivos não prova a correção das observações, dos ranges nem do EV. Não foi medido OCR nem validado processamento real de 40–60 minutos. Falta vídeo autorizado e anotado de 3–5 minutos para calibrar a visão. A revisão humana e as correções ainda não são persistidas pela interface.
