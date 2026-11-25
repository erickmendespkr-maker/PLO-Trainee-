# PLO Trainee — candidato Windows, PLO5 offline

Revisão de desenvolvimento do bloco 39. Não é um MVP de análise automática certificado. Funciona com gravações MP4 locais; não acompanha mesas ao vivo, não usa RTA e não se conecta a salas de poker. Não precisa de API de IA. A database incluída é de equity pré-flop agregada, não de frequências GTO.

## Instalação (Windows 10/11, 64 bits)

1. Extraia o ZIP inteiro em uma pasta local NTFS, por exemplo `C:\PLO-Trainee`. Evite pastas sincronizadas ou removíveis; os jobs registram caminhos absolutos.
2. Instale Python 3.13 64 bits (https://www.python.org/downloads/windows/) com o launcher `py` ou `python` no PATH. O código exige pelo menos Python 3.11. O ambiente testado foi Python 3.13.5 no Linux.
3. Instale FFmpeg e FFprobe (https://ffmpeg.org/download.html), com encoder libx264. Instale Tesseract OCR (https://tesseract-ocr.github.io/tessdoc/Installation.html). Adicione as pastas dos executáveis ao PATH do usuário. Abra um novo Prompt de Comando para conferir `ffmpeg -version`, `ffprobe -version` e `tesseract --version`. Não é necessário executar como administrador.
4. Execute `instalar_windows.cmd`. Ele cria `.venv`, instala Pillow 12.3.0 via pip e confere os executáveis e o SHA-256 do snapshot SQLite. A instalação de Pillow precisa de internet ou cache local; o processamento posterior é offline. O script não instala Python, FFmpeg ou Tesseract por conta própria. Em caso de erro, leia a mensagem, corrija a dependência e execute novamente. A pasta `data` deve conter o snapshot incluído no ZIP; no checkout Git ela deve ser fornecida separadamente.

## Primeiro uso

Abra o Prompt de Comando na pasta extraída. Verifique o ambiente:

    plo5.cmd check data\plo5_equity.sqlite

Prepare um JSON de regiões no formato dos exemplos em `layouts`. Cada região indica a mesa em pixels do quadro original (x, y, largura e altura, todos pares), sem sobreposição. Confirme visualmente se as mesas ocupam essas regiões durante a gravação. Os exemplos são exclusivos das geometrias indicadas; não são detector de layout.

Exemplo para vídeo horizontal de quatro mesas com 1608 x 748 pixels, ocupando colunas iguais:

    plo5.cmd audit "C:\Videos\sessao.mp4" layouts\horizontal4_1608x748.json sessao_001 --interval 120 --pixel-checks 8

O destino deve ser uma pasta nova. `audit` copia a gravação para armazenamento local, extrai os recortes e confere SHA, PTS e uma amostra de pixels. Intervalo permitido: 5 a 120 segundos. O padrão 120 é esparso e serve à auditoria, não à captura de todas as mãos. O limite é MP4 de até 3660 s, 4 GiB, 3840 x 2160; limites adicionais de amostras e mídia permanecem. O pré-teste de disco exige 2x o tamanho da fonte + 256 MiB livres, sem garantir espaço para todos os temporários. Um intervalo mais curto pode exceder o orçamento de recortes ou OCR. Não reduza a resolução para contornar falhas de OCR.

Saídas: `media_audit.json`, `annotations.json` (referência humana inicialmente vazia), `jobs.db`, `uploads` e `evidence`. O estado `review_required` significa evidência disponível, não análise estratégica concluída. Se a auditoria do job já terminou e faltar o relatório, recupere sem copiar/redecodificar a gravação:

    plo5.cmd recover sessao_001\jobs.db ID_DO_JOB novo_relatorio --interval 120

Use o intervalo original. Não altere/mova os arquivos de evidência. Não sobrescreva anotações existentes. Os recortes são privados e não são enviados a terceiros.

## Recursos e limites

O pacote inclui o núcleo matemático PLO5, os reconhecedores de candidatos, validação de referência, relatórios e exportação de intervalos MP4 explicitamente revisados. Para usar o reconhecimento são necessários perfis de ROIs, templates de cartas e calibração adequados à sala, além de revisão de ações e resultados; não há perfil automático certificado para a Suprema ou PPPoker. Os módulos e respectivos `--help` permitem uso avançado, mas o comando `audit` não executa toda essa cadeia sozinho. Não há interface gráfica final nem geração automática de todos os clipes perdedores. Nenhuma frequência GTO real foi validada. A perda financeira não equivale a EV loss.

O instalador CMD e o pacote foram preparados no Linux; ainda não foram executados em Windows. Testes de carga e benchmarks que importam `resource` e dependem de DejaVuSans são destinados ao Linux. Não há alegação de compatibilidade de todos os módulos, players ou desempenho no seu PC. Não inclua dados privados em commits. A regressão selecionada do bloco 36 está disponível no código (Linux, dependências e snapshot revisado necessários).

## Database

Fonte: SolvePoker, https://solvepoker.app/plo5-starting-hand-rankings . Licença declarada CC BY 4.0, https://creativecommons.org/licenses/by/4.0/ . Snapshot local de 134459 linhas, 2598960 combinações físicas representadas; CSV convertido para SQLite, sem alterar os registros. Equity agregada contra um adversário aleatório, sem correspondência exata de naipes ou solução GTO. SHA-256 SQLite: bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a.
