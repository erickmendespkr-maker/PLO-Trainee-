# Activity-PTS OCR bridge — ciclo 43 (offline)

Escopo: somente gravações PLO5/PLO6 enviadas pelo usuário; sem mesas jogáveis, integração ao vivo ou apostas.

O pacote local do ciclo 43 contém `video_analyzer/activity_ocr_bridge.py` e 13 novos testes (cinco do indexador e oito do adaptador). O adaptador valida o manifesto de evidências de atividade (`unverified_activity_pts_evidence_only`), verifica SHA-256 dos PNGs, preserva PTS decodificados, agrupa solicitações que apontam para o mesmo quadro, aplica ROIs escolhidas manualmente e executa FFmpeg + Tesseract offline. Candidatos permanecem **não verificados** e não são encaminhados diretamente para equity/EV.

Validação local: 541 testes `unittest` aprovados no pacote do ciclo 43; a integração sintética FFmpeg/Tesseract executou sem atribuir precisão real ao OCR. **O indexador e seus cinco testes foram publicados nesta branch; o adaptador OCR permanece apenas no pacote local**; este documento não constitui publicação ou validação remota do módulo.

Bloqueio: falta vídeo autorizado de 3–5 minutos para medir precisão e reconstrução de mãos reais. A sincronização exige trazer os módulos locais de extração de atividade e seus testes sem substituir versões divergentes do repositório.
