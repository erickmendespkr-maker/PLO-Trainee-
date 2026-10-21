# PLO Trainee — ciclo 29 (auditoria temporal offline)

Escopo mantido: análise assíncrona de gravações PLO5/PLO6; não inclui mesas jogáveis, oponentes de IA ou integração com plataformas de pôquer.

## Alteração preparada localmente

O auditor de observações passou a usar uma varredura temporal por mesa para detectar intervalos de mãos sobrepostos. A implementação local reduz o custo assintótico da detecção de O(H²) para O(H log H), mantendo a regra de que intervalos que apenas se tocam não são sobrepostos. Intervalos de duração zero e mãos encadeadas recebem tratamento explícito.

A alteração não inventa cartas, ações, limites ou classificações estratégicas. Sobreposições continuam exigindo revisão humana antes da análise matemática.

## Verificação local

Foram aprovados 44 testes focados com encerramento normal, incluindo 9 novos testes para intervalos adjacentes, aninhados, encadeados, mesas isoladas, duração zero, comparação aleatória com a referência quadrática e 12.000 mãos sintéticas em quatro mesas. O teste de escala exercitou 24.000 observações sintéticas; isso NÃO mede OCR ou processamento de vídeo real.

## Sincronização

A publicação do arquivo Python na branch feature/plo5-plo6-training foi bloqueada pela ferramenta. O código e os testes estão no pacote local do ciclo 29 e **não devem ser considerados implantados neste repositório**. Nenhuma alteração foi feita em main.

## Bloqueios

Falta uma gravação autorizada de 3–5 minutos de PLO5/PLO6 para validar OCR, segmentação e reconstrução de mãos reais. Não houve gastos nem uso de credenciais.
