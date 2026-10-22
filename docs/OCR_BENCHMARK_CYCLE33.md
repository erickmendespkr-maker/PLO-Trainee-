# PLO Trainee — protocolo de avaliação OCR offline (ciclo 33)

Escopo: somente vídeos gravados PLO5/PLO6, sem captura ao vivo, sem mesas jogáveis, sem apostas.

1. Extrair quadros e timestamps de apresentação decodificados usando FFmpeg. Guardar SHA-256 por PNG e manifesto de evidências.
2. Escolher amostras distribuídas temporalmente **por mesa e por campo** (`pot`, `bet`, `board`, `hero_cards`) a partir das ROIs, independentemente de o OCR ter conseguido ler o campo. Isso evita medir apenas as previsões bem-sucedidas.
3. Criar gabarito **sem respostas preenchidas**. Uma pessoa rotula diretamente as imagens; OCR não pode gerar a verdade de referência.
4. Comparar cada previsão por imagem exata, mesa, campo e PTS; não aproximar quadros vizinhos. Rejeitar PNG adulterado e gabarito desatualizado.
5. Reportar separadamente cobertura, acurácia entre respostas e acurácia global; incluir contagens, abstenções, amostras pendentes e intervalos Wilson 95% por campo e mesa.
6. Não declarar precisão real antes de receber gravação autorizada de 3–5 minutos com rótulos independentes. Testes sintéticos validam apenas o software de avaliação.

**Limitação:** hash confirma consistência do arquivo, não autenticidade da gravação. Timestamps são PTS de apresentação decodificados, não horários de captura autenticados. Confiança do Tesseract não é probabilidade calibrada.

Este documento é protocolo, não evidência de implantação do avaliador no repositório remoto.
