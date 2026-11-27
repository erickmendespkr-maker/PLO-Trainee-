# Bloco 07 — refinamento dirigido de fronteiras visuais

Adicionado plo5_boundary_refinement.py. Recalcula os intervalos candidatos a partir do manifesto mixed-video, confere SHA256 do vídeo e dos dois bancos, decodifica somente janelas locais em torno dos intervalos (amostragem 4 Hz, configurável 2–8 Hz) e lê cartas/dealer da mesa alvo. Confere PTS decodificados com o roster ffprobe. Exige pelo menos duas observações consecutivas de cada estado de referência, rejeita inversões e lacunas de amostragem entre os novos extremos, e não aceita ampliação do intervalo original. Estados desconhecidos podem conter outras mãos: os extremos são evidências visuais, não limites confirmados. Não emite resultados financeiros, ações verificadas ou estratégia.

## Teste real
Poker_Parte_01.mp4, reutilizados manifestos 435–475 e 1120–1180 s, sem baixar outro vídeo. Cinco intervalos refinados, 172 amostras dirigidas:
| Mesa | Intervalo anterior (s) | Refinado (s) |
|---|---:|---:|
| 1 PPPoker | 4 | 3,5 |
| 3 PPPoker | 10 | 9,2667 |
| 2 PPPoker | 7 | 6,2333 |
| 4 Suprema | 4 | 3,7333 |
| 3 PPPoker | 3,0333 | 1,7333 |

Execuções finais 4,49 s e 4,10 s de tempo de processo (inclui hashes, decodificação e reconhecimento). Não benchmark de sessão. Mesma gravação e bancos anteriores, sem anotação independente das fronteiras exatas. Os intervalos ainda podem ter eventos/mãos desconhecidos. Nenhuma mão certificada.

280 testes selecionados passaram no Linux em 3,587 s (7 novos e 273 regressões). Não checkout integral. Blobs locais/remotos idênticos: plo5_boundary_refinement.py 75a23b0092ae119e6986541f31e17e2ec870de7b; test_plo5_boundary_refinement.py 08295b5570308a6b9fe157cdd9dc24b15991a744. Não publicar imagens privadas, main preservada.

Uso: python video_analyzer/plo5_boundary_refinement.py VIDEO.mp4 PASTA_MIXED_VIDEO NOVO_JSON --card-bank bank_final.json --suprema-soft-bank bank_soft.json --hz 4

Próxima tarefa: bloco 08, organizar estados, ações e valores em histórico candidato por mesa, ligando somente evidências temporalmente compatíveis, mantendo lacunas e fronteiras não certificadas. Preservar pendências dos blocos 03–07 (incluindo calibração, identificação efetiva das ações e validação independente); não supor distribuição inicial ou resultado.
