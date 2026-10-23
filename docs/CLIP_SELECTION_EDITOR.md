# Seleção offline de cortes (PLO5/PLO6)

O editor de seleção usa **somente arquivos locais**. Ele não reconhece cartas, não classifica erros e não autoriza equity/EV. Os dados são sintéticos até serem revisados contra a gravação original.

## Fluxo

Execute os comandos a partir da pasta `video_analyzer`:

```bash
python activity_review_clip_template.py gravacao.mp4 fila.json revisao_validada.json selecao_modelo.json
python activity_clip_selection_editor.py selecao_modelo.json selecionar_cortes.html --video gravacao.mp4 --timestamp 30
```

Abra `selecionar_cortes.html` em um navegador local. A imagem de referência é um quadro aproximado extraído com FFmpeg; retângulos são desenhados sobre ela e acompanham as mudanças de coordenadas. Confira e ajuste os retângulos das mesas, confirme as regiões, marque **apenas** as decisões revisadas, preencha prioridade subjetiva (0–1) e explicação humana. Exporte o JSON. A interface não transmite dados, não marca opções por padrão e não realiza cálculos matemáticos.

Para gerar cortes após a revisão:

```bash
python activity_review_clip_export.py gravacao.mp4 fila.json revisao_validada.json selecao_exportada.json pasta_de_clipes_nova
```

O exportador existente valida o vínculo SHA-256 da gravação, da fila e da revisão, a identidade das decisões, os timestamps, as ações confirmadas e as regiões, antes de executar FFmpeg. O diretório de saída deve ser novo. **Não trate a confirmação manual como autenticação do vídeo nem como prova de erro estratégico.**

## Limitações

- O editor desenha regiões sobre **um único quadro aproximado**, não sobre o vídeo inteiro; confira se permanecem corretas ao longo da gravação. O HTML incorpora uma imagem que pode conter informações privadas. Sem `--video`, a interface permanece utilizável sem imagem.
- A confirmação das regiões é desmarcada ao alterar coordenadas; sobreposição e limites da imagem são verificados novamente no exportador Python.
- A seleção é manual, sem ordenação por EV. Explicações ficam no manifesto JSON, não sobrepostas ao MP4.
- O pipeline ainda precisa de gravação autorizada real para aferir OCR e reconstrução de mãos.
- Em navegadores que bloqueiam páginas locais, abra o HTML por um servidor HTTP **local**; nenhum serviço remoto é necessário.

## Verificação

```bash
python -m unittest -v test_activity_clip_selection_editor
python -m unittest discover -p 'test_*.py'
```

Documentação detalhada: `docs/CLIP_REGION_PREVIEW_CYCLE53.md`.
