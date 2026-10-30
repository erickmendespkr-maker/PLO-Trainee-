# Ciclo 222 — editor visual offline de regiões OCR

## Entrega
- `offline_table_roi_editor.py` gera uma página HTML autocontida a partir de um quadro PNG e do template humano do Ciclo 221.
- Canvas com seleção de até quatro mesas e campos, movimentação, redimensionamento, desfazer, restauração e download de JSON normalizado.
- O template exportado preserva o esquema `human_declared_table_geometry_unverified` e pode ser reutilizado por `offline_table_roi_sampler.py`.
- Validação de geometrias, limites de imagem, dimensões mínimas de OCR, não sobreposição de mesas, ausência de sobrescrita e hashes de entrada.
- Página com política CSP restritiva, imagem embutida e sem acesso à rede. Não habilita cálculos a partir de OCR.

## Como usar

```bash
ffmpeg -ss 15 -i sessao_autorizada.mp4 -frames:v 1 frame.png
python video_analyzer/offline_table_roi_editor.py frame.png template.json editor.html
```

Abra `editor.html` em navegador local, ajuste mesa/campo e baixe `plo_roi_template_revisado.json`. Utilize o JSON como template de entrada do amostrador do Ciclo 221. A revisão visual das cartas e ações continua obrigatória.

## Testes verificados
- 104 testes locais selecionados, incluindo 9 novos testes para o editor e regressão dos módulos ROI/OCR/fila.
- Playwright/Chromium: movimentação real de campo por mouse, download de JSON, validação da geometria exportada, sem erros de JavaScript.
- HTML carregado em memória (`page.set_content`) porque o Chromium deste ambiente bloqueia navegação `file://` por política administrativa. Abrir diretamente o HTML no Windows não foi testado.
- Entrada e imagem são sintéticas; nenhum vídeo real ou precisão de OCR foi validado.

## Bloqueios e limites
- Ainda depende de uma imagem de quadro e de um template inicial humano; não detecta mesas automaticamente nem acompanha deslocamentos ao longo do tempo.
- Não existe evidência real anotada para medir OCR e reconstrução de mãos.
- Não foram executados testes de 40–60 minutos, Windows, ou suíte integral do repositório.
- Nenhuma alteração em `main`, produção, credenciais, gastos ou GitHub Actions.
