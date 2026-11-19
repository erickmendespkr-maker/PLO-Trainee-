# PLO Trainee: iniciador Windows para cortes offline

Os arquivos Python do pipeline sao modulos, nao executaveis GUI; clique duplo pode abrir e fechar um console. O pacote de demonstracao inclui `iniciar_clipes.py`, `INICIAR_PLO_TRAINEE.bat`, `TESTAR_PLO_TRAINEE.bat`, exportador e testes.

Para usar, extraia o ZIP completo, instale Python 3 e FFmpeg/FFprobe no PATH e abra `INICIAR_PLO_TRAINEE.bat`. Selecione MP4 gravado, JSON com intervalos confirmados por humano e pasta de destino. Para diagnostico, use `TESTAR_PLO_TRAINEE.bat`.

A interface **nao** reconstrói maos automaticamente e **nao** produz recomendacoes de jogo ao vivo ou GTO. Os cortes permanecem `INSUFFICIENT_DATA`. Testes locais do exportador: 7/7 com video sintetico, nao em Windows. O launcher GUI e disponibilizado no pacote ZIP, nao integrado ao instalador principal.
