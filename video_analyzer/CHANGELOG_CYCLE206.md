# Ciclo 206 — galeria offline de cortes revisados

Escopo: somente gravações PLO5/PLO6. Sem mesas jogáveis, bots, login, captura ao vivo ou interação com poker real.

## Entrega
- `offline_reviewed_clip_gallery.py`: cria `index.html` dentro da pasta de clipes produzida por `offline_review_plan_clip_bridge.py`.
- Confere SHA-256 de cada MP4 contra `manifest.json` e `H001.mp4.json`, identidade da mão, vídeo de origem declarado, timestamps e explicação humana.
- Escapa o texto da explicação no HTML, não inclui JavaScript nem URLs externas e rejeita caminhos relativos fora da pasta, symlinks e saídas preexistentes.
- Se não houver análise matemática vinculada, mostra explicitamente **sem análise**.
- Opcionalmente associa relatório de cartas confirmadas por pessoa e JSON de sensibilidade EV **somente** quando hashes, IDs, cartas, variante e flags de incerteza forem compatíveis. Não estima EV nem identifica cartas.
- A galeria exibe apenas equity condicional e quantidade de hipóteses; EV detalhado permanece no JSON vinculado, não recebe nota de acerto/erro.

## Uso offline

Após exportar a pasta `clips/`:

```bash
python video_analyzer/offline_reviewed_clip_gallery.py clips clips/index.html
```

Opcionalmente, copie para a pasta `clips/` um relatório de confirmação humana e o respectivo JSON de sensibilidade, mantendo seus hashes e nomes. Crie `clips/attachments.json`:

```json
{
  "schema_version": 1,
  "analyses": {
    "H001": {
      "acknowledged_report": "H001.ack.json",
      "sensitivity": "H001.ev.json"
    }
  }
}
```

Então execute:

```bash
python video_analyzer/offline_reviewed_clip_gallery.py clips clips/index.html attachments.json
```

O comando recusa sobrescrever `index.html`. Escolha um nome novo para repetir. O anexo só é aceito se sua origem declarada corresponder ao SHA-256 do vídeo e do MP4 da galeria. Isso **não** confirma que as cartas estavam realmente visíveis; o revisor continua responsável pela confirmação.

## Testes e limitações

- 18 testes unitários sintéticos locais passaram após correção de um caso de fixture cujo hash incorreto coincidia com o hash de origem.
- Integração demonstrativa com o MP4 sintético real do ciclo 205: FFprobe identificou 2,2 segundos; a galeria foi gerada e verificou o hash.
- Chromium validou DOM e estrutura da página via `set_content`; carregamento por `file://` e `localhost` foi bloqueado no ambiente, portanto **reprodução visual do MP4 no navegador não foi verificada**.
- Sem gravação autorizada e anotada de 3–5 minutos, OCR/segmentação de mãos reais não têm métrica de precisão.
- Não foi executada a suíte integral do repositório nem testes no Windows, 1080p/30 FPS ou sessões reais de 40–60 minutos.
- Os testes sintéticos de anexo não reexecutam o cálculo Monte Carlo nem comprovam a validade dos ranges; apenas verificam vínculos e alegações de proveniência.
- O índice não reexecuta as auditorias originais de frames, não mede confiança de OCR e não classifica jogadas.

## Próximo passo

Integrar a navegação da interface de revisão com a galeria e criar um adaptador de evidência para que os cortes de quatro mesas possam receber relatórios de cartas manualmente confirmadas, sem reutilizar automaticamente bindings incompatíveis da trilha antiga. Depois validar com vídeo real autorizado.
