# Integração real de revisão monetária — bloco 1 (R2/R3)

## Entregas
- plo5_mixed_review.py integra a leitura de potes e stacks do perfil 1504×696 (PPPoker/Suprema) a janelas MP4 offline de 2–120 segundos; extrai um frame disponível por segundo e confere PTS e cobertura contra FFprobe. Registra segundos ausentes, sem interpolar valores. Limita a decodificação ao trecho.
- Cache SingleFlight por bytes exatos da ROI em tons de cinza, tamanho, plataforma e campo. Três workers por padrão; capacidade configurável 0–2048. O leitor não substitui a calibração de cartas.
- Produz index.html, prints/ e manifest.json. Prioriza somente quedas exibidas estritamente superiores a 30 BB entre amostras consecutivas, da mesma plataforma e slot, sem atravessar lacunas. Não certifica perdas nem identidade de mão ou mesa.
- plo5_review_pipeline.py oferece a rota `mixed-video`, sem alterar a rota antiga:
  `python video_analyzer/plo5_review_pipeline.py mixed-video VIDEO.mp4 PASTA_NOVA --start 125 --seconds 20`
- SHA256 do vídeo e dos prints conferido antes da publicação local; associação PTS conferida, sem auditoria independente por segunda decodificação. Nenhuma imagem privada publicada.

## Testes reais
Parte 01, 125–145 s: 20 frames, 160 campos, 158 valores candidatos, 2 ausências, 4,396 s. Parte 01, 900–930 s: 29 frames (segundo 918 sem frame no arquivo), 232 campos, 227 valores candidatos e 5 ausências, 5,630 s. Parte 06, 125–186 s: 61 frames, 488 campos, 457 valores candidatos e 31 ausências, 12,175 s.
Total: 110 frames reais únicos na rodada, 880 campos, 842 leituras numéricas candidatas e 38 nulos, 673 hits e 207 misses. Tempo somado 22,201 s. Nenhuma queda adjacente acima de 30 BB nos trechos. Esses números são cobertura de reconhecimento, não acurácia medida.

Comparação com cache desabilitado no mesmo trecho de 20 s: 8,731 s total e 6,601 s de reconhecimento contra 4,396 s total e 2,292 s de reconhecimento; 1,986x total e 2,880x reconhecimento. Todas as observações, PTS e hashes de prints idênticos. Uma medição por configuração, não benchmark integral de sessão. 
142 testes selecionados no Linux (8 novos + 134 regressões) aprovados, 3,574 s na repetição final. Testes unitários incluem mocks e dados sintéticos; execução MP4 acima foi real. Código, integração e teste conferidos por Git blob SHA local/remoto. 

## Pendências
Quatro outras gravações no Drive ainda não recuperadas nesta execução. Perfil monetário integrado como rota de entrada específica, não ao fluxo antigo de reconstrução por cartas. Faltam calibração de cartas e board, Hero e posições, ações, limites de mão, liquidação, rebuys, pagamentos, análise estratégica vinculada, sessão integral, Windows e demais pendências R1–R4/F1–F5. Meta de 5–10 minutos por hora de vídeo não comprovada. Nenhum novo bloco, custo ou modificação em main.