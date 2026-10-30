# Ciclo 224 — Revisão humana offline de evidências OCR

## Escopo
Módulo `video_analyzer/offline_ocr_frame_review_page.py`:
- Lê um diretório produzido por `offline_roi_frame_review.py` e um worksheet gerado por `offline_ocr_review_bridge.py`.
- Valida vínculos de SHA-256 de plano e vídeo, imagens PNG, mesa, mão e timestamps.
- Exibe quadros originais embutidos numa página HTML independente, sem rede.
- Permite marcar observações como não verificadas, rejeitadas ou aceitas após inspeção humana. A opção de aceitar só aparece quando há quadro da mesma mão/mesa a no máximo 0,25 s do timestamp OCR.
- Exporta `plo_ocr_review_draft.json`, explicitamente **não confirmado para matemática**; não produz `human_confirmed`, `card_evidence` nem fila de Monte Carlo.

## Uso
```bash
python video_analyzer/offline_ocr_frame_review_page.py \
  DIRETORIO_DE_QUADROS WORKSHEET.json NOVA_REVISAO.html
```
Abrir a página localmente no navegador, conferir os quadros e exportar o rascunho. A revisão de cartas/ações não é automaticamente transferida ao motor de equity/EV.

## Verificações realizadas
- 21 testes locais `unittest` com imagens PNG sintéticas: **21 aprovados**.
- Chromium headless: HTML carregado em memória, quatro mesas e quatro imagens, seleção bloqueada para timestamp distante, download de rascunho JSON com `eligible_for_equity=0`, sem erros JavaScript.
- A navegação `file://` foi bloqueada por política do ambiente de testes; não há comprovação de abertura direta do arquivo em Windows.
- Git blob SHA-1 do módulo e dos testes comparado com os arquivos locais testados.

## Limitações e bloqueios
- Não foi usado vídeo real de pôquer; nenhuma medição de precisão OCR.
- Sem reconhecimento automático de mãos, cartas, ações ou posições de mesa.
- O rascunho é apenas evidência de revisão, não autorização para equity/EV; um validador posterior deve revalidar cada confirmação e construir anotações compatíveis com a fila matemática.
- Os 21 testes cobrem o módulo novo, não a suíte integral.
- Falta vídeo autorizado e anotado de 3–5 minutos para validação visual real.

## Próximo passo
Criar um importador de rascunhos com validação de proveniência, confirmação humana por carta, tratamento de conflitos entre timestamps e geração fail-closed de anotações para `offline_reviewed_hand_math_queue.py`. Nenhuma hipótese de range deve ser inferida por OCR.
