# Ciclo 227 — revisão offline por mão e street

## Entrega
- Novo `offline_hand_street_review.py`: converte a reconstrução diagnóstica do ciclo 226 em worksheet JSON e página HTML local para revisão humana por mão, mesa e street.
- Exibe candidatos OCR sem promovê-los a fatos. Campos de cartas privadas, flop, turn e river são organizados por slot. Ações, pote e stack permanecem em **street desconhecida**, pois o ledger não comprova a street dessas observações.
- O navegador permite declarar, rejeitar ou manter desconhecido cada campo e exportar um rascunho JSON. Esse rascunho é **não autenticado**, não é importado automaticamente para matemática e preserva `eligible_for_equity=0`.
- Limites de 100 mãos e quatro mesas; validação de identificadores, hashes, cartas e origem do relatório; recusa sobrescrita, symlink de entrada e chaves JSON duplicadas. O HTML usa `textContent` e escapa sequências perigosas no JSON embutido.

## Uso
```bash
python video_analyzer/offline_hand_street_review.py RECONSTRUCTION.json NOVA_REVISAO.html NOVA_WORKSHEET.json
```
Abrir a página HTML em navegador local, preencher somente campos observáveis e exportar o rascunho. Não há comunicação com servidores nem cálculo de equity/EV.

## Testes locais verificados
- 25 testes novos de geração, validação e segurança; 70 testes de regressão dos ciclos 224–226: **95/95 aprovados**.
- Demonstração com o relatório sintético do ciclo 226: quatro mãos, quatro mesas, 60 campos para revisão, zero mãos elegíveis.
- Chromium headless validado via HTML carregado em memória: quatro mãos renderizadas, seleção manual, exportação JSON e nenhum erro JavaScript. A abertura direta `file://` foi bloqueada pela política do ambiente, portanto não está validada.
- SHA Git dos dois arquivos Python publicados conferido com os arquivos locais testados.

## Limitações e próximo ciclo
- Ainda faltam vídeo real autorizado/anotado, teste no Windows, precisão OCR real e sessão de 40–60 minutos.
- O editor não prova visibilidade nem autentica declarações humanas; **não** é uma fila matemática.
- Próximo: importador independente do rascunho, vinculação de revisão a evidências por timestamp, detecção de conflitos e geração controlada de anotações explícitas. Nunca promover OCR diretamente a equity/EV.
