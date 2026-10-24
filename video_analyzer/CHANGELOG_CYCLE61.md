# PLO Trainee — Ciclo 61 — Revisão offline com clipes MP4 verificáveis

## Escopo preservado

Somente análise **offline e assíncrona** de vídeos PLO5/PLO6 gravados. Nenhuma mesa jogável, bot adversário, integração ao vivo, seleção automática de cortes ou classificação de erros estratégicos.

## Alterações

- `activity_triage_clip_browser.py`: gera um pacote local com `index.html`, `manifest.json` e `clips/*.mp4`, partindo de um JSON de triagem previamente construído e dos MP4 exportados. O usuário abre manualmente cada clipe na decisão correspondente.
- Recalcula o SHA-256 **durante a cópia** e exige correspondência com o hash informado na triagem. Valida metadados básicos de vídeo MP4 com `ffprobe` (não equivale a decodificar todo o vídeo).
- Recusa arquivos ausentes, links simbólicos, nomes inválidos, conflitos de hash para o mesmo nome, arquivos acima de 1 GiB, pacotes acima de 10 GiB, mais de 1.000 clipes e destino já existente. Monta em diretório temporário e publica ao final; falhas não deixam pacote incompleto.
- A nova camada reutiliza o HTML validado por `activity_triage_dashboard.py` sem alterar o módulo existente; insere o reprodutor HTML5 `<video controls preload="none">` em cada decisão, sem autoplay. Ajusta apenas a diretiva CSP de mídia para `self` no pacote; nenhum recurso externo é necessário.
- `test_activity_triage_clip_browser.py`: testes com MP4 sintético real, hashes, proteção de saída, entradas inválidas, segurança de HTML, notas sem autorização, integração CLI e quatro mesas.

## Execução

No diretório `video_analyzer`, após gerar `review_triage.json` e `review_manifest.json`/MP4 por fluxos anteriores:

```bash
python activity_triage_clip_browser.py review_triage.json /caminho/para/clips /caminho/para/novo_pacote
```

O diretório `novo_pacote` **não pode existir** antes da execução. Os MP4 precisam corresponder aos nomes e hashes do JSON de triagem. O pacote não altera os vídeos de origem.

Para visualizar, abra `novo_pacote/index.html` em um navegador com suporte a MP4. Dependendo das restrições do navegador, a abertura via `file://` pode não funcionar; um servidor HTTP **somente local**, sem exposição externa, pode ser usado. Nunca publique a pasta com gravações privadas em um servidor acessível pela internet.

## Garantias e limites

- SHA-256 é conferido no momento da criação; se alguém modificar os clipes depois, a página HTML **não recalcula** os hashes.
- `ffprobe` valida apenas metadados e presença de stream de vídeo; não garante reprodução em todos os navegadores, nem integridade de todos os quadros.
- O JSON de triagem é uma declaração de origem; o pacote não comprova que o conteúdo do vídeo corresponde a cartas ou ações descritas. OCR, ranges, EV e vereditos permanecem não verificados.
- A interface não usa internet, não envia dados, não executa apostas e não toma decisões de pôquer.
- Falta gravação real autorizada para medir a precisão de OCR, reconstrução das mãos e o desempenho com 40–60 minutos.

## Verificação

- `python -m unittest -v test_activity_triage_clip_browser test_activity_triage_dashboard`
- `python -m unittest discover -s video_analyzer -p 'test_*.py' -v` (na raiz do pacote)
- Prova de conceito sintética: quatro MP4 com identificação textual de mesa, sem jogadas reais.
